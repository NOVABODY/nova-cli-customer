"""Delegated CLI regression tests: synthetic issuer/store and real loopback callback."""

import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message

import pytest

from nova_cli_public import delegated
from nova_cli_public.client import ApiClient
from nova_cli_public.config import ConfigStore, Profile
from nova_cli_public.errors import AuthError, TokenStoreUnavailable, UsageError
from nova_cli_public.tokens import KeyringTokenStore


class Response:
    status = 200
    headers = Message()
    headers["Content-Type"] = "application/json"

    def __init__(self, body):
        self.body = body

    def read(self):
        return json.dumps(self.body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Opener:
    def __init__(self):
        self.requests, self.responses = [], []

    def open(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return Response(response)


def pair(refresh="new-refresh"):
    return {
        "access_token": "opaque-access",
        "refresh_token": refresh,
        "token_type": "Bearer",
        "scope": "nova:read",
        "expires_in": 300,
    }


@pytest.fixture
def client(monkeypatch):
    import keyring

    values = {}
    monkeypatch.setattr(
        keyring, "get_password", lambda service, account: values.get((service, account))
    )
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, account, secret: values.__setitem__((service, account), secret),
    )
    monkeypatch.setattr(
        keyring, "delete_password", lambda service, account: values.pop((service, account), None)
    )
    profile = Profile("personal", "https://nova.example/api", "keyring", "delegated")
    result = ApiClient(profile, KeyringTokenStore(), opener=Opener())
    result.test_values = values
    return result


def seed(client):
    client.token_store.set_refresh_token(
        delegated.credential_profile(client.profile), "old-refresh"
    )
    client.test_values[("nova-cli", "personal")] = "password-refresh"


def test_refresh_uses_form_bound_audience_and_rotates_only_delegated_entry(client):
    seed(client)
    client.opener.responses = [pair()]
    assert client.refresh()["access_token"] == "opaque-access"
    request = client.opener.requests[0]
    fields = urllib.parse.parse_qs(request.data.decode())
    assert request.full_url == "https://nova.example/api/oauth/token"
    assert fields == {
        "grant_type": ["refresh_token"],
        "refresh_token": ["old-refresh"],
        "client_id": ["nova-cli"],
        "resource": ["https://nova.example/api"],
    }
    assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
    assert (
        client.token_store.get_refresh_token(delegated.credential_profile(client.profile))
        == "new-refresh"
    )
    assert client.test_values[("nova-cli", "personal")] == "password-refresh"


def test_lost_refresh_response_removes_old_token_and_cannot_replay(client):
    seed(client)
    client.opener.responses = [TimeoutError("SECRET")]
    with pytest.raises(AuthError) as error:
        client.refresh()
    assert "SECRET" not in str(error.value)
    with pytest.raises(AuthError):
        client.refresh()
    assert len(client.opener.requests) == 1


def test_failed_keyring_delete_prevents_refresh_request(client, monkeypatch):
    import keyring

    seed(client)

    def fail(*args):
        raise RuntimeError("SECRET")

    monkeypatch.setattr(keyring, "delete_password", fail)
    with pytest.raises(TokenStoreUnavailable) as error:
        client.refresh()
    assert "SECRET" not in str(error.value)
    assert not client.opener.requests


def test_failed_keyring_preread_prevents_refresh_and_logout(client, monkeypatch):
    import keyring

    seed(client)

    def fail(*args):
        raise RuntimeError("SECRET")

    monkeypatch.setattr(keyring, "get_password", fail)
    for action in (client.refresh, client.logout):
        with pytest.raises(TokenStoreUnavailable) as error:
            action()
        assert "SECRET" not in str(error.value)
    assert not client.opener.requests


def test_failed_rotated_save_does_not_return_access_or_replay(client, monkeypatch):
    import keyring

    seed(client)

    def fail(*args):
        raise RuntimeError("SECRET")

    monkeypatch.setattr(keyring, "set_password", fail)
    client.opener.responses = [pair()]
    with pytest.raises(TokenStoreUnavailable):
        client.refresh()
    assert client.access_token is None
    with pytest.raises(AuthError):
        client.refresh()
    assert len(client.opener.requests) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("token_type", "Basic"),
        ("scope", "full"),
        ("expires_in", True),
        ("access_token", ""),
        ("refresh_token", "old-refresh"),
    ],
)
def test_invalid_response_never_returns_authority(client, field, value):
    seed(client)
    body = pair()
    body[field] = value
    client.opener.responses = [body]
    with pytest.raises(AuthError):
        client.refresh()
    assert client.access_token is None


def test_issuer_bound_entry_does_not_reuse_another_origin(client):
    seed(client)
    other = ApiClient(
        Profile("personal", "https://other.example/api", "keyring", "delegated"),
        client.token_store,
        opener=Opener(),
    )
    with pytest.raises(AuthError):
        other.refresh()
    assert not other.opener.requests


@pytest.mark.parametrize(
    "api,store",
    [
        ("http://127.0.0.1/api", "keyring"),
        ("https://nova.example/v1", "keyring"),
        ("https://nova.example/api", "auto"),
        ("https://nova.example/api", "file"),
    ],
)
def test_delegated_profile_refuses_unbound_endpoint_or_fallback(api, store):
    with pytest.raises(UsageError):
        ConfigStore().set_profile("personal", api, store, auth="delegated")


def test_oauth_error_never_exposes_echoed_secret(client):
    seed(client)
    client.opener.responses = [
        urllib.error.HTTPError(
            "https://nova.example/api/oauth/token",
            400,
            "bad",
            Response.headers,
            io.BytesIO(b'{"detail":"SECRET"}'),
        )
    ]
    with pytest.raises(AuthError) as error:
        client.refresh()
    assert "SECRET" not in str(error.value)


def test_browser_callback_uses_pkce_and_verifies_state_issuer(client, monkeypatch):
    captured, responses = {}, []

    def open_browser(url):
        captured.update(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))
        callback = captured["redirect_uri"][0]

        def respond():
            query = {
                "state": captured["state"][0],
                "iss": "https://nova.example",
                "code": "one-use-code",
            }
            with urllib.request.urlopen(
                callback + "?" + urllib.parse.urlencode(query), timeout=2
            ) as reply:
                responses.append(reply.status)

        thread = threading.Thread(target=respond)
        thread.start()
        captured["thread"] = thread
        return True

    monkeypatch.setattr(delegated.webbrowser, "open", open_browser)
    client.opener.responses = [pair()]
    delegated.login(client)
    captured["thread"].join(2)
    assert responses == [200]
    assert captured["code_challenge_method"] == ["S256"]
    assert captured["client_id"] == ["nova-cli"]
    assert captured["resource"] == ["https://nova.example/api"]
    form = urllib.parse.parse_qs(client.opener.requests[0].data.decode())
    import base64
    import hashlib

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert captured["code_challenge"] == [expected]
    assert form["redirect_uri"] == captured["redirect_uri"]


@pytest.mark.parametrize("bad", ["state", "issuer", "path", "method", "duplicate", "host"])
def test_callback_rejects_unbound_request_then_accepts_valid_request(monkeypatch, bad):
    threads, statuses, callback_urls = [], [], []

    def open_browser(url):
        parameters = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        callback = parameters["redirect_uri"][0]
        callback_urls.append(callback)
        good = {
            "state": parameters["state"][0],
            "iss": "https://nova.example",
            "code": "accepted-code",
        }
        invalid = dict(good)
        if bad == "state":
            invalid["state"] = "wrong"
        if bad == "issuer":
            invalid["iss"] = "https://other.example"
        target = callback.replace("/oauth/callback", "/other") if bad == "path" else callback
        query = urllib.parse.urlencode(invalid)
        if bad == "duplicate":
            query += "&state=extra"

        def respond():
            request = urllib.request.Request(
                target + "?" + query, method="POST" if bad == "method" else "GET"
            )
            if bad == "host":
                request.add_header("Host", "other.example")
            try:
                urllib.request.urlopen(request, timeout=2)
            except urllib.error.HTTPError as exc:
                statuses.append(exc.code)
            with urllib.request.urlopen(
                callback + "?" + urllib.parse.urlencode(good), timeout=2
            ) as response:
                statuses.append(response.status)

        thread = threading.Thread(target=respond)
        threads.append(thread)
        thread.start()
        return True

    monkeypatch.setattr(delegated.webbrowser, "open", open_browser)
    code, _, _ = delegated.browser_code("https://nova.example", timeout=2)
    for thread in threads:
        thread.join(2)
    assert code == "accepted-code"
    assert statuses == [405 if bad == "method" else 400, 200]
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(callback_urls[0], timeout=0.1)


def test_browser_timeout_and_launcher_failure_do_not_exchange_or_replace_credentials(
    client, monkeypatch
):
    seed(client)
    monkeypatch.setattr(delegated.webbrowser, "open", lambda url: False)
    with pytest.raises(AuthError):
        delegated.login(client)
    assert (
        client.token_store.get_refresh_token(delegated.credential_profile(client.profile))
        == "old-refresh"
    )
    monkeypatch.setattr(delegated.webbrowser, "open", lambda url: True)
    with pytest.raises(AuthError):
        delegated.browser_code("https://nova.example", timeout=0)
    assert not client.opener.requests


def test_interrupted_browser_closes_listener(client, monkeypatch):
    captured = []

    def interrupt(url):
        captured.append(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["redirect_uri"][0])
        raise KeyboardInterrupt()

    monkeypatch.setattr(delegated.webbrowser, "open", interrupt)
    with pytest.raises(KeyboardInterrupt):
        delegated.login(client)
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(captured[0], timeout=0.1)
    assert not client.opener.requests


@pytest.mark.parametrize("operation", ["refresh", "logout"])
def test_delegated_lifecycle_holds_existing_profile_lock_through_store_and_transport(
    client, monkeypatch, operation
):
    from contextlib import contextmanager

    import keyring

    seed(client)
    held = []

    @contextmanager
    def lock(name):
        held.append(name)
        try:
            yield
        finally:
            held.pop()

    monkeypatch.setattr(delegated, "profile_lock", lock)
    for method in ("get_password", "set_password", "delete_password"):
        original = getattr(keyring, method)

        def checked(*args, original=original):
            assert held == ["personal"], (
                "Credential reads, deletion and replacement share the profile lock"
            )
            return original(*args)

        monkeypatch.setattr(keyring, method, checked)
    original_open = client.opener.open

    def open_request(*args, **kwargs):
        assert held == ["personal"], "Refresh transport must remain inside the profile lock"
        return original_open(*args, **kwargs)

    client.opener.open = open_request
    client.opener.responses = [pair()]
    getattr(client, operation)()
    assert not held


def test_unchanged_keyring_delete_is_not_success(client, monkeypatch):
    import keyring

    seed(client)
    monkeypatch.setattr(keyring, "delete_password", lambda *args: None)
    with pytest.raises(TokenStoreUnavailable):
        client.refresh()
    assert not client.opener.requests


@pytest.mark.parametrize(
    "path",
    [
        "/assistant/context",
        "/assistant/operations",
        "/assistant/operations/vehicles.list.v1",
        "/assistant/operations/vehicles.get.v1",
    ],
)
def test_removed_discovery_routes_fail_before_transport(client, path):
    client.access_token = "opaque-access"
    with pytest.raises(UsageError):
        client.request("GET", path)
    assert not client.opener.requests


@pytest.mark.parametrize('operations', [None, 'work_orders.list.v1', 'defects.list.v1'])
def test_browser_requests_only_explicit_operation_grants(monkeypatch, operations):
    captured = []
    monkeypatch.setattr(delegated.webbrowser, 'open', lambda url: captured.append(url) or False)
    with pytest.raises(AuthError):
        delegated.browser_code('https://nova.example', operations=operations)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(captured[0]).query)
    assert query.get('operations') == [operations or delegated.DEFAULT_OPERATIONS]
    assert query['scope'] == ['nova:read']


def test_unknown_operation_is_rejected_before_browser(monkeypatch):
    monkeypatch.setattr(delegated.webbrowser, 'open', lambda url: pytest.fail('Browser opened'))
    with pytest.raises(UsageError):
        delegated.browser_code('https://nova.example', operations='admin.users.list')


@pytest.mark.parametrize('path', ['/assistant/work-orders', '/assistant/work-orders/WO-0001'])
def test_work_order_read_transport_is_allowed(client, path):
    client.access_token = 'opaque-access'
    client.opener.responses = [{'id': 'WO-0001'}]
    assert client.request('GET', path) == {'id': 'WO-0001'}
    assert client.opener.requests[0].full_url.endswith(path)


@pytest.mark.parametrize('method,path', [
    ('POST', '/assistant/work-orders'), ('DELETE', '/assistant/work-orders/WO-0001'),
    ('GET', '/assistant/work-orders/../vehicles'), ('GET', '/work-orders/WO-1/unknown'),
    ('GET', '/assistant/work-orders/WO-1?admin=true'),
])
def test_work_order_transport_denies_writes_and_path_escape(client, method, path):
    with pytest.raises(UsageError):
        client.request(method, path)
    assert not client.opener.requests


@pytest.mark.parametrize('path', ['/assistant/defects', '/assistant/defects/FD-0001'])
def test_defect_read_transport_is_allowed(client, path):
    client.access_token = 'opaque-access'
    client.opener.responses = [{'id': 'FD-0001'}]
    assert client.request('GET', path) == {'id': 'FD-0001'}
    assert client.opener.requests[0].full_url.endswith(path)


@pytest.mark.parametrize('method,path', [
    ('POST', '/assistant/defects'), ('DELETE', '/assistant/defects/FD-0001'),
    ('GET', '/assistant/defects/../vehicles'), ('GET', '/defects/FD-1/unknown'),
    ('GET', '/assistant/defects/FD-1?admin=true'),
])
def test_defect_transport_denies_writes_and_path_escape(client, method, path):
    with pytest.raises(UsageError):
        client.request(method, path)
    assert not client.opener.requests


def test_logout_revokes_bound_connection_and_clears_only_local_delegated_credentials(client):
    seed(client)
    client.access_token = 'synthetic-access'
    client.opener.responses = [{}]
    assert client.logout() is True
    request = client.opener.requests[0]
    assert request.full_url == 'https://nova.example/api/oauth/revoke'
    assert urllib.parse.parse_qs(request.data.decode()) == {
        'token': ['old-refresh'], 'token_type_hint': ['refresh_token'], 'client_id': ['nova-cli'],
        'resource': ['https://nova.example/api'],
    }
    assert request.get_header('Authorization') is None
    assert client.access_token is None
    assert delegated._read(client) is None
    assert client.test_values[('nova-cli', 'personal')] == 'password-refresh'


def test_logout_clears_local_credentials_but_does_not_claim_revocation_after_transport_failure(client):
    seed(client)
    client.access_token = 'synthetic-access'
    client.opener.responses = [TimeoutError('PRIVATE SECRET')]
    assert client.logout() is False
    assert client.access_token is None
    assert delegated._read(client) is None
    assert len(client.opener.requests) == 1


@pytest.mark.parametrize('confirmed', [True, False])
def test_logout_command_reports_server_confirmation_without_disclosing_credentials(client, monkeypatch, confirmed):
    from types import SimpleNamespace

    from nova_cli_public import cli

    seed(client)
    client.opener.responses = [{} if confirmed else TimeoutError('PRIVATE SECRET')]
    monkeypatch.setattr(cli, 'client_from_args', lambda args: client)
    result = cli.cmd_auth(SimpleNamespace(action='logout'))
    assert result['local_credentials_cleared'] is True
    assert result['server_revoked'] is confirmed
    assert 'PRIVATE SECRET' not in result['message']
    assert 'old-refresh' not in json.dumps(result)
    assert ('not confirmed' in result['message']) is (not confirmed)


def test_logout_without_a_saved_refresh_token_clears_memory_without_claiming_server_revocation(client):
    client.access_token = 'synthetic-access'
    assert client.logout() is False
    assert client.access_token is None
    assert not client.opener.requests
