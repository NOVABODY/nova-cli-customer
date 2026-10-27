from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from nova_cli_public.errors import UsageError

APP_NAME = "nova-cli-public"
DEFAULT_API_URL = "https://app.nova4a.com/api"
TOKEN_STORES = {"keyring"}
AUTH_MODES = {"delegated"}


@dataclass(frozen=True)
class Profile:
    name: str
    api: str
    token_store: str = "keyring"
    auth: str = "delegated"

    def __post_init__(self):
        if self.auth != "delegated" or self.token_store != "keyring":
            raise UsageError("Public profiles require browser login and OS credential storage.")
        if self.auth == "delegated":
            from nova_cli_public.delegated import issuer

            issuer(self)


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_path()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"current_profile": None, "profiles": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise UsageError(f"Invalid config JSON at {self.path}") from exc
        if not isinstance(data, dict):
            raise UsageError(f"Invalid config shape at {self.path}")
        data.setdefault("current_profile", None)
        data.setdefault("profiles", {})
        if not isinstance(data["profiles"], dict):
            raise UsageError(f"Invalid profiles section at {self.path}")
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def set_profile(
        self,
        name: str,
        api: str | None = None,
        token_store: str = "keyring",
        auth: str | None = None,
    ) -> Profile:
        normalized_name = require_profile_name(name)
        normalized_store = normalize_token_store(token_store)
        data = self.load()
        existing = data["profiles"].get(normalized_name)
        existing_auth = (
            existing.get("auth", "delegated") if isinstance(existing, dict) else "delegated"
        )
        data["profiles"][normalized_name] = {
            "api": normalize_api_url(
                api if api is not None else (existing or {}).get("api", DEFAULT_API_URL)
            ),
            "token_store": normalized_store,
            "auth": normalize_auth_mode(auth) if auth else existing_auth,
        }
        Profile(normalized_name, **data["profiles"][normalized_name])
        data["current_profile"] = normalized_name
        self.save(data)
        return self.get_profile(normalized_name)

    def set_profile_auth(self, name: str, api: str, token_store: str, auth: str) -> Profile:
        """Upsert a profile's stored settings without changing the current profile."""
        normalized_name = require_profile_name(name)
        data = self.load()
        data["profiles"][normalized_name] = {
            "api": normalize_api_url(api),
            "token_store": normalize_token_store(token_store),
            "auth": normalize_auth_mode(auth),
        }
        if data.get("current_profile") is None:
            data["current_profile"] = normalized_name
        self.save(data)
        return self.get_profile(normalized_name)

    def use_profile(self, name: str) -> Profile:
        profile = self.get_profile(name)
        data = self.load()
        data["current_profile"] = profile.name
        self.save(data)
        return profile

    def remove_profile(self, name: str) -> None:
        normalized_name = require_profile_name(name)
        data = self.load()
        if normalized_name not in data["profiles"]:
            raise UsageError(f"Profile not found: {normalized_name}")
        del data["profiles"][normalized_name]
        if data.get("current_profile") == normalized_name:
            data["current_profile"] = next(iter(data["profiles"]), None)
        self.save(data)

    def list_profiles(self) -> tuple[str | None, list[Profile]]:
        data = self.load()
        profiles = [
            Profile(
                name=name,
                api=entry["api"],
                token_store=entry.get("token_store", "keyring"),
                auth=entry.get("auth", "delegated"),
            )
            for name, entry in sorted(data["profiles"].items())
        ]
        return data.get("current_profile"), profiles

    def get_profile(self, name: str | None = None, *, api_override: str | None = None) -> Profile:
        data = self.load()
        selected = name or data.get("current_profile")
        entry = data["profiles"].get(selected) if selected else None
        if not isinstance(entry, dict):
            if selected and not api_override:
                raise UsageError(f"Profile not found: {selected}")
            # Credentials are keyed by profile name, so an unsaved profile is
            # bound to the default origin like a saved one is to its own.
            _require_same_origin(api_override, DEFAULT_API_URL)
            return Profile(
                name=selected or "default",
                api=normalize_api_url(api_override or DEFAULT_API_URL),
            )
        _require_same_origin(api_override, entry["api"])
        return Profile(
            name=selected,
            api=normalize_api_url(api_override or entry["api"]),
            token_store=entry.get("token_store", "keyring"),
            auth=entry.get("auth", "delegated"),
        )


def _require_same_origin(api_override: str | None, saved_api: str) -> None:
    if api_override and api_origin(api_override) != api_origin(saved_api):
        raise UsageError(
            "API override has a different origin from the profile's API. "
            "Configure a separate profile for that API origin with "
            "`nova profile set NAME --api URL`."
        )


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def normalize_api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url:
        raise UsageError("API URL cannot be empty")
    if not url.startswith(("http://", "https://")):
        raise UsageError("API URL must start with http:// or https://")
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        raise UsageError("Invalid API URL") from None
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise UsageError("API URL must have a host and no credentials, query, or fragment")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise UsageError("API credentials require HTTPS, except on loopback hosts")
    return url


def api_origin(value: str) -> tuple[str, str | None, int]:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        return (
            parsed.scheme,
            parsed.hostname,
            port if port is not None else (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        raise UsageError("Invalid API URL") from None


def require_profile_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise UsageError("Profile name cannot be empty")
    if any(ch.isspace() for ch in name):
        raise UsageError("Profile name cannot contain whitespace")
    return name


def normalize_token_store(value: str) -> str:
    token_store = value.strip().lower()
    if token_store not in TOKEN_STORES:
        raise UsageError(f"Unsupported token store {value!r}; choose keyring")
    return token_store


def normalize_auth_mode(value: str) -> str:
    auth = value.strip().lower()
    if auth not in AUTH_MODES:
        raise UsageError(f"Unsupported auth mode {value!r}; choose delegated")
    return auth
