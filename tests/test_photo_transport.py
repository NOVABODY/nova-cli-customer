import io
import urllib.request
import urllib.response
from email.message import Message
from types import SimpleNamespace

import pytest

from nova_cli_public.client import ApiClient, NoRedirects
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError, UsageError


class HTTPS(urllib.request.HTTPSHandler):
    def __init__(self, status=204):
        super().__init__()
        self.status, self.calls = status, []

    def https_open(self, request):
        self.calls.append(request)
        headers = Message()
        headers['Location'] = 'https://foreign.example/stolen'
        response = urllib.response.addinfourl(io.BytesIO(), headers, request.full_url, self.status)
        response.msg = 'synthetic'
        return response


def client(handler):
    return ApiClient(Profile('photos', 'https://nova.example/api'), object(),
                     opener=urllib.request.build_opener(NoRedirects(), handler))


@pytest.mark.parametrize('url', ['https://foreign.example/signed', 'http://nova.example/signed',
    'https://user:secret@nova.example/signed', 'https://@nova.example/signed',
    'https://nova.example/signed#fragment'])
def test_unsafe_presign_never_sends_bytes(url):
    handler = HTTPS()
    with pytest.raises(UsageError):
        client(handler).put_bytes(url, b'PRIVATE', content_type='image/png')
    assert not handler.calls


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_signed_put_does_not_follow_redirects(status):
    handler = HTTPS(status)
    with pytest.raises(ApiError):
        client(handler).put_bytes('https://nova.example/signed', b'image', content_type='image/png')
    assert len(handler.calls) == 1


def test_configured_origin_put_has_no_credentials(monkeypatch):
    monkeypatch.setenv('NOVA_UPLOAD_ORIGINS', 'https://storage.example')
    handler = HTTPS()
    api = client(handler)
    api.access_token = 'PRIVATE'
    api.put_bytes('https://storage.example/signed', b'image', content_type='image/png')
    request, = handler.calls
    assert request.data == b'image' and request.method == 'PUT'
    assert not {'authorization', 'cookie', 'proxy-authorization'} & {k.lower() for k in request.headers}


@pytest.mark.parametrize('origin', [' https://STORAGE.Example/ ', 'HTTPS://storage.example',
    'https://unused.example, https://STORAGE.example/'])
def test_configured_origins_are_normalized(monkeypatch, origin):
    monkeypatch.setenv('NOVA_UPLOAD_ORIGINS', origin)
    handler = HTTPS()
    client(handler).put_bytes('https://storage.example/signed', b'image', content_type='image/png')
    assert len(handler.calls) == 1


@pytest.mark.parametrize('origin', ['https://storage.example/path', 'https://storage.example//',
    'https://storage.example/?query', 'https://storage.example/#fragment',
    'https://user@storage.example', 'http://localhost:8000'])
def test_invalid_configured_origin_refuses_bytes(monkeypatch, origin):
    monkeypatch.setenv('NOVA_UPLOAD_ORIGINS', origin)
    handler = HTTPS()
    with pytest.raises(UsageError, match='NOVA_UPLOAD_ORIGINS.* / .*NOVA_UPLOAD_ORIGINS'):
        client(handler).put_bytes('https://nova.example/signed', b'image', content_type='image/png')
    assert not handler.calls


class HTTP(urllib.request.HTTPHandler):
    def __init__(self):
        super().__init__()
        self.calls = []

    def http_open(self, request):
        self.calls.append(request)
        response = urllib.response.addinfourl(io.BytesIO(), Message(), request.full_url, 204)
        response.msg = 'synthetic'
        return response


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1', '[::1]'])
@pytest.mark.parametrize('target', ['same', 'other-port', 'other-host'])
def test_http_upload_requires_exact_loopback_api_origin(host, target):
    handler = HTTP()
    api = client(handler)
    # Exercise transport independently of the HTTPS-only delegated login profile.
    api.profile = SimpleNamespace(api=f'http://{host}:8000/api')
    url = {'same': f'http://{host}:8000/signed',
           'other-port': f'http://{host}:8001/signed',
           'other-host': 'http://foreign.example:8000/signed'}[target]
    if target == 'same':
        api.put_bytes(url, b'image', content_type='image/png')
        assert len(handler.calls) == 1
        assert not handler.calls[0].has_header('Authorization')
    else:
        with pytest.raises(UsageError):
            api.put_bytes(url, b'image', content_type='image/png')
        assert not handler.calls


def test_api_origin_put_is_allowed():
    handler = HTTPS()
    client(handler).put_bytes('https://nova.example/signed', b'image', content_type='image/png')
    assert len(handler.calls) == 1



def test_http_api_origin_cannot_authorize_nonloopback_upload():
    handler = HTTP()
    api = client(handler)
    api.profile = SimpleNamespace(api='http://foreign.example/api')
    with pytest.raises(UsageError):
        api.put_bytes('http://foreign.example/signed', b'image', content_type='image/png')
    assert not handler.calls
