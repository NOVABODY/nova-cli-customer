"""Native read-only browser authorization using the existing client and keyring."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import webbrowser
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlencode, urlsplit

from nova_cli_public.errors import AuthError, TokenStoreUnavailable, UsageError
from nova_cli_public.locking import profile_lock

CLIENT_ID = "nova-cli"


def issuer(profile):
    parsed = urlsplit(profile.api)
    host = parsed.hostname or ""
    authority = f"[{host}]" if ":" in host else host
    if parsed.port not in (None, 443):
        authority += f":{parsed.port}"
    origin = "https://" + authority
    if (
        profile.token_store != "keyring"
        or not host
        or parsed.scheme != "https"
        or profile.api != origin + "/api"
    ):
        raise UsageError(
            "Delegated login requires --token-store keyring and a canonical HTTPS /api URL."
        )
    return origin


def credential_profile(profile):
    # Separate from password/service entries, bound to the fixed client, issuer and API resource.
    binding = hashlib.sha256((issuer(profile) + "/api\0" + CLIENT_ID).encode()).hexdigest()
    return replace(profile, name=profile.name + "#delegated:" + binding)


def _read(client):
    try:
        return client.token_store.get_refresh_token(credential_profile(client.profile))
    except Exception:  # noqa: BLE001 - OAuth/store errors must not expose credentials
        raise TokenStoreUnavailable(
            "Could not read delegated credentials. Unlock the OS credential store."
        ) from None


def _delete(client):
    # Strict read/delete/read: legacy cleanup deliberately tolerates an unreadable keychain.
    client.token_store.delete_refresh_token_strict(credential_profile(client.profile))


def _token(client, fields, previous=None):
    fields.update(client_id=CLIENT_ID, resource=issuer(client.profile) + "/api")
    try:
        body = client._send(
            "POST",
            "/oauth/token",
            raw_body=urlencode(fields).encode(),
            raw_content_type="application/x-www-form-urlencoded",
        ).body
        if (
            not isinstance(body, dict)
            or body.get("token_type", "").lower() != "bearer"
            or body.get("scope") not in ("nova:read", "nova:read nova:write")
            or type(body.get("expires_in")) is not int
            or not 0 < body["expires_in"] <= 300
            or any(
                not isinstance(body.get(key), str) or not 1 <= len(body[key]) <= 16384
                for key in ("access_token", "refresh_token")
            )
            or body["refresh_token"] == previous
        ):
            raise ValueError()
    except Exception:  # noqa: BLE001 - OAuth/store errors must not expose credentials
        raise AuthError("Delegated sign-in failed. Run `nova auth login` again.") from None
    client.token_store.set_refresh_token(credential_profile(client.profile), body["refresh_token"])
    client.access_token = body["access_token"]
    return body


def refresh(client):
    with profile_lock(client.profile.name):
        client.access_token = None
        token = _read(client)
        if not token:
            raise AuthError("No delegated credential is stored. Run `nova auth login`.")
        _delete(
            client
        )  # A lost response must not leave an old rotating token available for replay.
        return _token(
            client, {"grant_type": "refresh_token", "refresh_token": token}, previous=token
        )


def logout(client):
    with profile_lock(client.profile.name):
        _delete(client)
        client.access_token = None


def status(client):
    with profile_lock(client.profile.name):
        return {"credential_stored": bool(_read(client)), "server_verified": False}


from nova_cli_public.read_routes import READ_ROUTES
from nova_cli_public.write_routes import WRITE_ROUTES

OPERATIONS = set(READ_ROUTES.values()) | set(WRITE_ROUTES.values())
DEFAULT_OPERATIONS = "vehicles.list_full.v1 vehicles.get_full.v1"


def browser_code(origin, timeout=180, operations=None, scope="nova:read"):
    operations = DEFAULT_OPERATIONS if operations is None else operations
    if operations is not None and (
        not operations.split() or not set(operations.split()) <= OPERATIONS
    ):
        raise UsageError("Unknown operation. Run nova capabilities --json.")
    if scope not in ("nova:read", "nova:read nova:write"):
        raise UsageError("Use nova:read or nova:read nova:write.")
    if set(operations.split()) & set(WRITE_ROUTES.values()) and scope != "nova:read nova:write":
        raise UsageError("Write operations require --scope 'nova:read nova:write'.")
    verifier, state = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    outcome = {}
    deadline = time.monotonic() + timeout

    class Server(HTTPServer):
        def handle_error(self, request, client_address):
            pass  # Never log callback requests, including interrupted response writes.

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(max(0.01, min(2, deadline - time.monotonic())))
            return connection, address

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Authorization codes must never enter HTTP request logs.

        def do_POST(self):
            self.send_error(405)

        def do_GET(self):
            parsed = urlsplit(self.path)
            try:
                pairs = parse_qsl(parsed.query, strict_parsing=True, max_num_fields=5)
                fields = dict(pairs)
                if (
                    parsed.path != "/oauth/callback"
                    or parsed.scheme
                    or parsed.netloc
                    or self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"
                    or len(fields) != len(pairs)
                    or set(fields) not in ({"state", "iss", "code"}, {"state", "iss", "error"})
                    or not secrets.compare_digest(fields.get("state", ""), state)
                    or fields.get("iss") != origin
                    or not 1 <= len(fields.get("code", fields.get("error", ""))) <= 2048
                ):
                    raise ValueError()
            except (ValueError, TypeError):
                self.send_error(400)
                return
            outcome.update(fields)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(b"You can close this window. / Puede cerrar esta ventana.")

    with Server(("127.0.0.1", 0), Callback) as server:
        redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth/callback"
        url = (
            origin
            + "/api/oauth/authorize?"
            + urlencode(
                {
                    **({"operations": operations} if operations is not None else {}),
                    "response_type": "code",
                    "client_id": CLIENT_ID,
                    "resource": origin + "/api",
                    "scope": scope,
                    "state": state,
                    "redirect_uri": redirect_uri,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )
        try:
            opened = webbrowser.open(url)
        except Exception:  # noqa: BLE001 - launcher errors may contain the authorization URL
            opened = False
        if not opened:
            raise AuthError("Could not open the browser. Run login from a desktop session.")
        while not outcome and time.monotonic() < deadline:
            server.timeout = max(0.01, deadline - time.monotonic())
            server.handle_request()
    if "code" not in outcome:
        raise AuthError("Browser sign-in was not completed. Run `nova auth login` again.")
    return outcome["code"], verifier, redirect_uri


def login(client, operations=None, scope="nova:read"):
    if scope not in ("nova:read", "nova:read nova:write"):
        raise AuthError("Use nova:read or nova:read nova:write.")
    _read(client)  # Fail before opening the browser when the configured keyring is unavailable.
    code, verifier, redirect_uri = (
        browser_code(
            issuer(client.profile),
            operations=operations,
            **({"scope": scope} if scope != "nova:read" else {}),
        )
        if operations is not None or scope != "nova:read"
        else browser_code(issuer(client.profile))
    )
    with profile_lock(client.profile.name):
        token = _token(
            client,
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
            },
        )
    return {"scope": token["scope"], "resource": issuer(client.profile) + "/api"}
