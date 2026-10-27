import io
import json
import urllib.error
from email.message import Message

import pytest

from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError


class Opener:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def open(self, request, timeout):
        self.calls.append(request)
        if self.error:
            raise self.error
        response = io.BytesIO(b'{"ok":true}')
        response.status = 200
        response.headers = Message()
        response.headers["Content-Type"] = "application/json"
        return response


@pytest.mark.parametrize("status", [401, 409, 422, 302, 500, 503])
def test_write_http_error_is_sent_once_without_refresh_retry(status, monkeypatch):
    headers = Message()
    headers["Content-Type"] = "application/json"
    body = {"detail": {"code": "state_changed", "expected_version": 3}}
    error = urllib.error.HTTPError(
        "https://nova.example/api/work-orders/WO-1/complete",
        status,
        "error",
        headers,
        io.BytesIO(json.dumps(body).encode()),
    )
    opener = Opener(error)
    client = ApiClient(Profile("test", "https://nova.example/api"), object(), opener=opener)
    client.access_token = "synthetic-access"
    monkeypatch.setattr(client, "refresh", lambda: pytest.fail("Mutation was retried via refresh"))
    with pytest.raises(ApiError) as raised:
        client.request("POST", "/work-orders/WO-1/complete", json_body={"last_mileage": 100})
    assert raised.value.status == status
    if status >= 500 or 300 <= status < 400:
        assert raised.value.code == "outcome_unknown"
        assert raised.value.detail is None
    else:
        assert raised.value.detail == body["detail"]
    assert len(opener.calls) == 1


def test_write_timeout_has_unknown_outcome_and_is_not_retried():
    opener = Opener(TimeoutError("synthetic timeout"))
    client = ApiClient(Profile("test", "https://nova.example/api"), object(), opener=opener)
    client.access_token = "synthetic-access"
    with pytest.raises(ApiError) as raised:
        client.request("POST", "/vehicles/VAN-1/notes", json_body={"body": "Note"})
    assert raised.value.code == "outcome_unknown"
    assert len(opener.calls) == 1


def test_write_can_refresh_once_before_first_send(monkeypatch):
    opener = Opener()
    client = ApiClient(Profile("test", "https://nova.example/api"), object(), opener=opener)
    refreshed = []

    def refresh():
        refreshed.append(True)
        client.access_token = "synthetic-access"

    monkeypatch.setattr(client, "refresh", refresh)
    assert client.request("POST", "/vehicles/VAN-1/notes", json_body={"body": "Note"}) == {
        "ok": True
    }
    assert refreshed == [True]
    assert len(opener.calls) == 1


def test_signed_upload_has_no_bearer_credentials():
    opener = Opener()
    client = ApiClient(Profile("test", "https://nova.example/api"), object(), opener=opener)
    client.access_token = "synthetic-access"
    client.put_bytes(
        "https://storage.example/photo?signature=synthetic", b"photo", content_type="image/png"
    )
    request = opener.calls[0]
    assert request.method == "PUT"
    assert request.data == b"photo"
    assert not any(key.lower() == "authorization" for key in request.headers)


@pytest.mark.parametrize(
    "url", ["http://storage.example/photo", "https://user:pass@storage.example/photo"]
)
def test_signed_upload_rejects_unsafe_url_without_sending(url):
    from nova_cli_public.errors import UsageError

    opener = Opener()
    client = ApiClient(Profile("test", "https://nova.example/api"), object(), opener=opener)
    with pytest.raises(UsageError):
        client.put_bytes(url, b"photo", content_type="image/png")
    assert opener.calls == []


def test_signed_upload_redirect_is_not_followed():
    headers = Message()
    headers["Location"] = "https://other.example/photo"
    error = urllib.error.HTTPError(
        "https://storage.example/photo", 307, "redirect", headers, io.BytesIO()
    )
    opener = Opener(error)
    client = ApiClient(Profile("test", "https://nova.example/api"), object(), opener=opener)
    with pytest.raises(ApiError) as raised:
        client.put_bytes("https://storage.example/photo", b"photo", content_type="image/png")
    assert raised.value.status == 307
    assert len(opener.calls) == 1
