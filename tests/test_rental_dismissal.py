import asyncio
import io
import json
import urllib.error
from email.message import Message

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService


class Opener:
    def __init__(self, value=None, status=200):
        self.value = value if value is not None else {'id': 'RR-7', 'status': 'open', 'native': True}
        self.status, self.calls = status, []

    def open(self, request, timeout):
        self.calls.append(request)
        headers = Message()
        headers['Content-Type'] = 'application/json'
        if self.status != 200:
            raise urllib.error.HTTPError(request.full_url, self.status, 'rejected', headers, io.BytesIO(b'{}'))
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, headers
        return response


def client(opener):
    api = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    api.access_token = 'synthetic-access'
    return api


def test_cli_and_local_sdk_dismiss_with_no_body_and_native_receipt(monkeypatch):
    opener = Opener()
    api = client(opener)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['repair-request', 'dismiss-rental-routing', 'RR-7'])
    assert args.handler(args) == opener.value

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tool = next(tool for tool in (await sdk.list_tools()).tools if tool.name == 'dismiss_rental_routing')
            assert not tool.annotations.readOnlyHint
            result = await sdk.call_tool('dismiss_rental_routing', {'rr_id': 'RR-7'})
            assert not result.isError and result.structuredContent == opener.value
    asyncio.run(check())
    assert len(opener.calls) == 2
    assert all(call.method == 'POST' and call.full_url.endswith('/repair-requests/RR-7/dismiss-rental-routing') and call.data is None for call in opener.calls)


@pytest.mark.parametrize('value', [{'id': 'RR-8', 'status': 'open'}, {'id': 'RR-7', 'status': 'cancelled'}, {'id': 'RR-7', 'status': 'open', 'bad': float('nan')}])
def test_unconfirmed_dismissal_receipt_is_unknown(value):
    opener = Opener(value)
    with pytest.raises(ApiError) as error:
        CustomerReadService(client(opener)).run('dismiss_rental_routing', {'rr_id': 'RR-7'})
    assert error.value.code == 'outcome_unknown' and len(opener.calls) == 1


@pytest.mark.parametrize('status', [401, 403, 409, 302, 503])
def test_dismissal_rejection_never_refreshes_or_retries(monkeypatch, status):
    opener = Opener(status=status)
    api = client(opener)
    monkeypatch.setattr(api, 'refresh', lambda: pytest.fail('Do not repeat dismissal'))
    with pytest.raises(ApiError) as error:
        CustomerReadService(api).run('dismiss_rental_routing', {'rr_id': 'RR-7'})
    assert len(opener.calls) == 1
    assert (error.value.code == 'outcome_unknown') == (status in (302, 503))


@pytest.mark.parametrize('arguments', [{'rr_id': 'RR-0'}, {'rr_id': False}, {'rr_id': 'RR-7', 'force': True}])
def test_dismissal_closed_input_fails_before_transport(arguments):
    opener = Opener()
    with pytest.raises(ValidationError):
        CustomerReadService(client(opener)).run('dismiss_rental_routing', arguments)
    assert not opener.calls
