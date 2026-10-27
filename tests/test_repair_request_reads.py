import io
import json
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.reads import CustomerReadService

FILTERS = {'status': 'open', 'dsp_id': 'DSP-3', 'limit': 500, 'offset': 2,
           'awaiting_rental_routing_confirmation': False, 'rental_queue': True,
           'rental_approval_state': 'routing_blocked'}
PAGE = {'items': [{'id': 'RR-7', 'extra': {'kept': True}}], 'total': 91, 'native': True}
OPTIONS = {'items': [], 'related_defects': [], 'contacts': [], 'default_contact_user_id': None, 'unavailable_reason': 'native'}


class Opener:
    def __init__(self, value):
        self.value, self.calls = value, []

    def open(self, request, timeout):
        self.calls.append(request)
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'application/json'
        return response


@pytest.mark.parametrize('action,tool,args,arguments,path,value', [
    ('list', 'list_repair_requests', ['--status', 'open', '--dsp-id', 'DSP-3', '--limit', '500', '--offset', '2', '--no-awaiting-rental-routing-confirmation', '--rental-queue', '--rental-approval-state', 'routing_blocked'], FILTERS, '/api/repair-requests', PAGE),
    ('get', 'get_repair_request', ['RR-7'], {'rr_id': 'RR-7'}, '/api/repair-requests/RR-7', {'id': 'RR-7', 'native': True}),
    ('external-vendor-options', 'list_repair_request_external_vendor_options', ['RR-7'], {'rr_id': 'RR-7'}, '/api/repair-requests/RR-7/external-vendor-options', OPTIONS),
])
def test_cli_and_stdio_use_real_client_native_reads(monkeypatch, action, tool, args, arguments, path, value):
    opener = Opener(value)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    parsed = cli.build_parser().parse_args(['repair-request', action, *args])
    assert parsed.handler(parsed) == value
    assert CustomerReadService(client).run(tool, arguments) == value
    assert len(opener.calls) == 2
    for request in opener.calls:
        assert request.method == 'GET' and urlsplit(request.full_url).path == path and request.data is None
        assert parse_qs(urlsplit(request.full_url).query) == ({k: [str(v)] for k, v in FILTERS.items()} if action == 'list' else {})


@pytest.mark.parametrize('tool,args', [
    ('list_repair_requests', {'limit': 501}), ('list_repair_requests', {'limit': True}),
    ('list_repair_requests', {'offset': -1}), ('list_repair_requests', {'status': 'invented'}),
    ('list_repair_requests', {'dsp_id': 'DSP-0'}), ('list_repair_requests', {'rental_queue': 'true'}),
    ('list_repair_requests', {'rental_approval_state': 'approved'}),
    ('get_repair_request', {'rr_id': '../escape'}),
    ('list_repair_request_external_vendor_options', {'rr_id': 'RR-7', 'limit': 1}),
])
def test_closed_native_read_inputs_fail_before_transport(tool, args):
    class Never:
        def request(self, *args, **kwargs):
            pytest.fail('Invalid read input reached transport')
    with pytest.raises(ValidationError):
        CustomerReadService(Never()).run(tool, args)


def test_sdk_read_discovery_defaults_and_native_fields():
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.delegated import OPERATIONS
    from nova_cli_public.mcp import create_server

    async def check():
        opener = Opener(PAGE)
        client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
        client.access_token = 'synthetic-access'
        async with create_connected_server_and_client_session(create_server(CustomerReadService(client))) as sdk:
            tools = {t.name: t for t in (await sdk.list_tools()).tools}
            assert tools['list_repair_requests'].annotations.readOnlyHint
            result = await sdk.call_tool('list_repair_requests', {})
            assert not result.isError and result.structuredContent == PAGE
            assert parse_qs(urlsplit(opener.calls[0].full_url).query) == {'limit': ['100'], 'offset': ['0']}
            assert (await sdk.call_tool('list_repair_requests', {'unknown': True})).isError
            assert len(opener.calls) == 1
        assert {'repair_requests.list.v1', 'repair_requests.get.v1', 'repair_requests.external_vendor_options.list.v1'} <= OPERATIONS
    asyncio.run(check())


@pytest.mark.parametrize('name,value', [
    ('list_repair_requests', {'items': [], 'total': True}),
    ('list_repair_requests', {'items': [1], 'total': 1}),
    ('get_repair_request', []),
    ('list_repair_request_external_vendor_options', {'items': []}),
])
def test_malformed_native_response_is_not_success(name, value):
    from nova_cli_public.errors import ApiError
    from nova_cli_public.repair_requests import validate
    with pytest.raises(ApiError):
        validate(name, value)
