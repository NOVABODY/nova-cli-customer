import asyncio
import io
import json
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

BODY = {'vehicle_id': 'VAN-7', 'repair_type': 'mechanical', 'defect_id': 'FD-8', 'service_station_code': 'ST1'}
OPTIONS = {'items': [{'external_vendor_id': 3, 'name': 'Repair vendor'}], 'contacts': [], 'related_defects': [], 'default_contact_user_id': None, 'unavailable_reason': None, 'native': True}


class Opener:
    def __init__(self, value):
        self.value, self.calls = value, []

    def open(self, request, timeout):
        self.calls.append(request)
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'application/json'
        return response


def client(opener):
    api = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    api.access_token = 'synthetic-access'
    return api


def test_cli_and_sdk_use_native_read_post_with_same_body(monkeypatch):
    opener = Opener(OPTIONS)
    api = client(opener)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    words = ['repair-request', 'preview-external-vendor-options'] + [part for key, value in BODY.items() for part in ('--' + key.replace('_', '-'), value)]
    args = cli.build_parser().parse_args(words)
    assert args.handler(args) == OPTIONS

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tool = next(tool for tool in (await sdk.list_tools()).tools if tool.name == 'preview_repair_request_external_vendor_options')
            assert tool.annotations.readOnlyHint
            result = await sdk.call_tool(tool.name, BODY)
            assert not result.isError and result.structuredContent == OPTIONS
    asyncio.run(check())
    assert len(opener.calls) == 2
    for request in opener.calls:
        assert request.method == 'POST' and request.full_url.endswith('/repair-requests/external-vendor-options/prepare')
        assert json.loads(request.data) == BODY


@pytest.mark.parametrize('arguments', [dict(BODY, vehicle_id='VAN-0'), dict(BODY, repair_type=False), dict(BODY, service_station_code='x' * 21), dict(BODY, external_vendor_id=3)])
def test_preview_closed_input_never_reaches_transport(arguments):
    opener = Opener(OPTIONS)
    with pytest.raises(ValidationError):
        CustomerReadService(client(opener)).run('preview_repair_request_external_vendor_options', arguments)
    assert not opener.calls


@pytest.mark.parametrize('value', [{}, dict(OPTIONS, contacts=[False]), dict(OPTIONS, bad=float('nan'))])
def test_preview_rejects_an_invalid_native_options_response(value):
    opener = Opener(value)
    with pytest.raises(ApiError):
        CustomerReadService(client(opener)).run('preview_repair_request_external_vendor_options', BODY)
    assert len(opener.calls) == 1
