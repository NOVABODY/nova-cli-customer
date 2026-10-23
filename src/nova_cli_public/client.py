from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any

from nova_cli_public import __version__, delegated
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.read_routes import PUBLIC_READS, admitted_read
from nova_cli_public.tokens import KeyringTokenStore


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class Response:
    status: int
    headers: Mapping[str, str]
    body: Any


class ApiClient:
    def __init__(
        self,
        profile: Profile,
        token_store: KeyringTokenStore,
        *,
        timeout: float = 30,
        opener: Any | None = None,
    ) -> None:
        self.profile = profile
        self.token_store = token_store
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(NoRedirects())
        self.access_token: str | None = None

    def _validate_authenticated_target(self, path: str) -> None:
        """Prevent bearer credentials from being sent to another origin."""
        target = urllib.parse.urlsplit(path.strip())
        if not target.scheme and not target.netloc:
            return
        if target.scheme not in {"http", "https"} or not target.netloc:
            raise UsageError("Authenticated API URLs must use http:// or https://")

        configured = urllib.parse.urlsplit(self.profile.api)
        try:
            target_origin = (target.scheme.lower(), target.hostname, target.port)
            configured_origin = (
                configured.scheme.lower(),
                configured.hostname,
                configured.port,
            )
        except ValueError as exc:
            raise UsageError(f"Invalid API URL: {exc}") from exc
        if target_origin != configured_origin:
            raise UsageError(
                "Refusing to send Nova credentials to a different origin; "
                "use a profile configured for that API host."
            )

    def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        query: Mapping[str, str | int | float | bool | None] | None = None,
        headers: Mapping[str, str] | None = None,
        raw_body: bytes | None = None,
        raw_content_type: str | None = None,
    ) -> Response:
        customer_read = method == "GET" and (admitted_read(path) or path in PUBLIC_READS)
        token_request = method == "POST" and path == "/oauth/token" and raw_body is not None
        if not (customer_read or token_request):
            raise UsageError("This route is not available in the public CLI.")
        if customer_read and (json_body is not None or raw_body is not None):
            raise UsageError("Reads cannot send a request body.")
        if json_body is not None and raw_body is not None:
            raise UsageError("Use only one of json_body or raw_body.")
        url = self._url(path, query)
        request_headers = {
            "Accept": "application/json",
            "User-Agent": f"nova-cli/{__version__}",
        }
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            data = raw_body
            if raw_content_type:
                request_headers["Content-Type"] = raw_content_type
        if headers:
            request_headers.update(headers)
        req = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return Response(
                    status=resp.status,
                    headers=dict(resp.headers.items()),
                    body=_decode_body(raw, resp.headers.get("Content-Type", "")),
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            body = _decode_body(raw, exc.headers.get("Content-Type", ""))
            code = body.get("code") if isinstance(body, dict) else None
            detail = body.get("detail") if isinstance(body, dict) else body
            if code is None and isinstance(detail, dict):
                nested_code = detail.get("code")
                if isinstance(nested_code, str):
                    code = nested_code
            request_id = exc.headers.get("X-Request-ID")
            message = f"API request failed ({exc.code})"
            if code:
                message += f": {code}"
            if isinstance(detail, str):
                message += f": {detail}"
            raise ApiError(
                message,
                status=exc.code,
                code=code,
                detail=detail,
                request_id=request_id,
            ) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"Could not reach Nova API at {self.profile.api}: {exc.reason}") from exc
        except (TimeoutError, ConnectionError, HTTPException) as exc:
            raise ApiError("Nova API connection interrupted or timed out.") from exc

    def _url(
        self,
        path: str,
        query: Mapping[str, str | int | float | bool | None] | None,
    ) -> str:
        normalized = path.strip()
        if not normalized:
            raise UsageError("API path cannot be empty")
        if normalized.startswith(("http://", "https://")):
            base = normalized
        else:
            if not normalized.startswith("/"):
                normalized = "/" + normalized
            configured_base = self.profile.api.rstrip("/")
            configured_path = urllib.parse.urlsplit(configured_base).path.rstrip("/")
            if normalized.startswith("/.well-known/"):
                parsed = urllib.parse.urlsplit(configured_base)
                base = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, normalized, "", ""))
            elif configured_path:
                # An explicit path is a reverse-proxy prefix (for example /api),
                # so do not insert the default /v1 prefix after it.
                base = configured_base + normalized
            elif normalized.startswith("/v1/") or normalized == "/v1":
                base = configured_base + normalized
            else:
                base = configured_base + "/v1" + normalized
        clean_query = {k: str(v) for k, v in (query or {}).items() if v is not None}
        if clean_query:
            sep = "&" if urllib.parse.urlsplit(base).query else "?"
            return base + sep + urllib.parse.urlencode(clean_query)
        return base

    def connection_identity(self):
        # This value partitions local cursors only. The server verifies authority
        # on every request; unverified claims never grant an operation here.
        try:
            encoded = self.access_token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            identity = tuple(claims[key] for key in ("iss", "sub", "tenant", "gid"))
            if not all(isinstance(value, str) and value for value in identity):
                raise ValueError
            return identity
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            raise UsageError(
                "Cannot bind the file cursor to this connection. Sign in again."
            ) from None

    def public_request(self, method, path):
        if method != "GET" or path not in PUBLIC_READS:
            raise UsageError("This public route is not available.")
        return self._send(method, path).body

    def whoami(self):
        return self.request("GET", "/auth/me")

    def refresh(self):
        return delegated.refresh(self)

    def logout(self):
        return delegated.logout(self)

    def request(self, method, path, *, query=None, retry_auth=True):
        if method != "GET" or not admitted_read(path):
            raise UsageError("This command is not available in the public CLI.")
        if not self.access_token:
            self.refresh()
        try:
            return self._send(
                method, path, query=query, headers={"Authorization": f"Bearer {self.access_token}"}
            ).body
        except ApiError as exc:
            if exc.status == 401 and retry_auth:
                self.refresh()
                return self.request(method, path, query=query, retry_auth=False)
            raise


def _decode_body(raw: bytes, content_type: str) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8")
    if "application/json" in content_type.lower():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
