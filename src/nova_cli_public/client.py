from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any

from nova_cli_public import __version__, claim_archive, delegated, pave_images
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.read_routes import PDF_ROUTES, PUBLIC_READS, READ_POST_ROUTES, admitted_read
from nova_cli_public.tokens import KeyringTokenStore
from nova_cli_public.write_routes import admitted_write

PDF_MAX_BYTES = 10 * 1024 * 1024
PDF_ERROR_MAX_BYTES = 64 * 1024


def _pdf_target(method, path, query, json_body, raw_body, max_bytes=PDF_MAX_BYTES):
    if type(max_bytes) is not int or not 1 <= max_bytes <= PDF_MAX_BYTES:
        raise UsageError("Invalid PDF byte limit.")
    if (method != "GET" or not any(re.fullmatch(pattern, path) for pattern in PDF_ROUTES)
            or json_body is not None or raw_body is not None):
        raise UsageError("Use a named Body repair PDF read.")
    query = query or {}
    if set(query) - ({"quote"} if path.endswith('/quote') else set()):
        raise UsageError("Invalid document query.")
    quote = query.get('quote')
    if quote is not None and (not isinstance(quote, str) or not re.fullmatch(r'(?:BRQ-)?[0-9]+', quote)):
        raise UsageError("Use a numeric or BRQ quote ID.")


def _pdf_bytes(response, max_bytes=PDF_MAX_BYTES, *, image=False):
    media = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
    if (response.status != 200 or (media not in pave_images.MIMES if image else media != 'application/pdf')
            or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
        raise ApiError("Nova did not return an image. / Nova no devolvió una imagen." if image else "Nova did not return a PDF.", status=response.status)
    length = response.headers.get('Content-Length')
    if length is not None and (len(length) > 8 or not length.isascii() or not length.isdigit()):
        raise ApiError("Invalid image length. / Longitud de imagen no válida." if image else "Invalid PDF length.")
    if length is not None and int(length) > max_bytes:
        raise ApiError("Image exceeds the byte limit. / La imagen supera el límite de bytes." if image else "PDF exceeds the byte limit.",
                       code="image_too_large" if image else "document_too_large")
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ApiError("Image exceeds the byte limit. / La imagen supera el límite de bytes." if image else "PDF exceeds the byte limit.",
                       code="image_too_large" if image else "document_too_large")
    if length is not None and len(raw) != int(length):
        raise ApiError("Incomplete image transfer. / Transferencia de imagen incompleta." if image else "PDF transfer is too large or incomplete.")
    if image:
        if pave_images.mime(raw) != media:
            raise ApiError('Invalid image format. / Formato de imagen no válido.')
    elif not raw.startswith(b'%PDF-') or not raw.rstrip(b'\x00\t\n\f\r ').endswith(b'%%EOF'):
        raise ApiError("Nova did not return a PDF.")
    return raw


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
        self.access_token_expires_at: float | None = None

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
        pdf: bool = False,
        pdf_max_bytes: int = PDF_MAX_BYTES,
        archive: bool = False,
        archive_max_bytes: int = claim_archive.MAX_BYTES,
        image: bool = False,
        image_max_bytes: int = claim_archive.MAX_BYTES,
    ) -> Response:
        if image:
            if pdf or archive:
                raise UsageError('Use one document format. / Usa un formato de documento.')
            pave_images.target(method, path, query, json_body, raw_body, image_max_bytes)
        if archive:
            if pdf:
                raise UsageError('Use one document format. / Usa un formato de documento.')
            claim_archive.target(method, path, query, json_body, raw_body, archive_max_bytes)
        if pdf:
            _pdf_target(method, path, query, json_body, raw_body, pdf_max_bytes)
        customer_read = (method == "GET" and (admitted_read(path) or path in PUBLIC_READS)) or (method == "POST" and path in READ_POST_ROUTES)
        token_request = method == "POST" and path in ("/oauth/token", "/oauth/revoke") and raw_body is not None
        customer_write = admitted_write(method, path)
        if not (customer_read or customer_write or token_request):
            raise UsageError("This route is not available in the public CLI.")
        if customer_read and method == "GET" and (json_body is not None or raw_body is not None):
            raise UsageError("Reads cannot send a request body.")
        if json_body is not None and raw_body is not None:
            raise UsageError("Use only one of json_body or raw_body.")
        url = self._url(path, query)
        request_headers = {
            "Accept": ", ".join(pave_images.MIMES) if image else claim_archive.MIME if archive else "application/pdf" if pdf else "application/json",
            "User-Agent": f"nova-cli/{__version__}",
        }
        if pdf or archive or image:
            request_headers["Accept-Encoding"] = "identity"
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
                if image:
                    return Response(resp.status, dict(resp.headers.items()), _pdf_bytes(resp, image_max_bytes, image=True))
                if archive:
                    return Response(resp.status, dict(resp.headers.items()), claim_archive.read(resp, archive_max_bytes))
                if pdf:
                    return Response(resp.status, dict(resp.headers.items()), _pdf_bytes(resp, pdf_max_bytes))
                raw = resp.read()
                return Response(
                    status=resp.status,
                    headers=dict(resp.headers.items()),
                    body=_decode_body(raw, resp.headers.get("Content-Type", "")),
                )
        except urllib.error.HTTPError as exc:
            if pdf or archive or image:
                try:
                    raw = exc.read(PDF_ERROR_MAX_BYTES + 1)
                finally:
                    exc.close()
            else:
                raw = exc.read()
            if pdf or archive or image:
                body = {}
                if len(raw) <= PDF_ERROR_MAX_BYTES and 'application/json' in exc.headers.get('Content-Type', '').lower():
                    try:
                        decoded = _decode_body(raw, 'application/json')
                        body = decoded if isinstance(decoded, dict) else {}
                    except UnicodeError:
                        pass
            else:
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
        except (TimeoutError, ConnectionError, HTTPException, UnicodeError) as exc:
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

    def put_bytes(self, url, data, *, content_type):
        from nova_cli_public.legacy_reads import resolve_photo_url

        url = resolve_photo_url(url, self)
        request = urllib.request.Request(
            url,
            data=data,
            method="PUT",
            headers={"Content-Type": content_type, "User-Agent": f"nova-cli/{__version__}"},
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return _decode_body(response.read(), response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            raise ApiError("Photo upload was rejected.", status=exc.code) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, HTTPException, UnicodeError):
            raise ApiError(
                "The upload outcome is unknown. Check the record before trying again.",
                code="outcome_unknown",
            ) from None

    def request(self, method, path, *, json_body=None, query=None, retry_auth=True, raw_body=None, raw_content_type=None, pdf=False, pdf_max_bytes=PDF_MAX_BYTES, archive=False, archive_max_bytes=claim_archive.MAX_BYTES, image=False, image_max_bytes=claim_archive.MAX_BYTES):
        if image:
            if pdf or archive:
                raise UsageError('Use one document format. / Usa un formato de documento.')
            pave_images.target(method, path, query, json_body, raw_body, image_max_bytes)
        if archive:
            if pdf:
                raise UsageError('Use one document format. / Usa un formato de documento.')
            claim_archive.target(method, path, query, json_body, raw_body, archive_max_bytes)
        if pdf:
            _pdf_target(method, path, query, json_body, raw_body, pdf_max_bytes)
        mutation = admitted_write(method, path)
        if not (mutation or (method == "GET" and admitted_read(path)) or (method == "POST" and path in READ_POST_ROUTES)):
            raise UsageError("This command is not available in the public CLI.")
        if (not self.access_token or (self.access_token_expires_at is not None
                and time.monotonic() + 5 >= self.access_token_expires_at)):
            self.refresh()
        try:
            return self._send(
                method,
                path,
                json_body=json_body,
                raw_body=raw_body, raw_content_type=raw_content_type,
                query=query,
                headers={"Authorization": f"Bearer {self.access_token}"}, pdf=pdf, pdf_max_bytes=pdf_max_bytes, archive=archive, archive_max_bytes=archive_max_bytes, image=image, image_max_bytes=image_max_bytes,
            ).body
        except ApiError as exc:
            if mutation and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
                raise ApiError(
                    "The change outcome is unknown. Check the record before trying again.",
                    code="outcome_unknown", status=exc.status,
                ) from None
            if not mutation and exc.status == 401 and retry_auth:
                self.refresh()
                return self.request(method, path, json_body=json_body, raw_body=raw_body, raw_content_type=raw_content_type, query=query, retry_auth=False, pdf=pdf, pdf_max_bytes=pdf_max_bytes, archive=archive, archive_max_bytes=archive_max_bytes, image=image, image_max_bytes=image_max_bytes)
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
