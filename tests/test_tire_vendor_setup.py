"""The command and SDK tool preserve the same scoped tire setup request."""
import asyncio
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

SAVED = {'id': 12, 'dsp_id': 7, 'station_id': 4, 'status': 'submitted', 'vendor_name': 'Local Tires',
         'contact_name': 'Desk', 'contact_email': None, 'contact_phone': '+17035550100'}
CASES = [
    (['list', '--dsp-id', 'DSP-7'], 'list_station_tire_vendors', {'dsp_id': 'DSP-7'},
     'GET', '/onboarding/dsp/tire-vendors', {'params': {'dsp_id': 'DSP-7'}}, {'stations': []}),
    (['add', 'TEST1', '9'], 'add_station_tire_vendor', {'station_code': 'TEST1', 'vendor_workshop_id': 9},
     'POST', '/onboarding/dsp/tire-vendors', {'json_body': {'station_code': 'TEST1', 'vendor_workshop_id': 9}},
     {'dsp_id': 7, 'vendor_workshop_id': 9, 'repair_type': 'tires', 'is_active': True}),
    (['share-contact', 'TEST1', '--vendor-name', 'Local Tires', '--contact-name', 'Desk', '--contact-phone', '+17035550100'],
     'share_tire_vendor_contact', {'station_code': 'TEST1', 'vendor_name': 'Local Tires', 'contact_name': 'Desk', 'contact_phone': '+17035550100'},
     'POST', '/onboarding/dsp/tire-vendor-requests', {'json_body': {'station_code': 'TEST1', 'vendor_name': 'Local Tires', 'contact_name': 'Desk', 'contact_phone': '+17035550100'}}, SAVED),
    (['requests', '--request-id', '12'], 'list_vendor_setup_requests', {'request_id': 12},
     'GET', '/vendor-setup-requests', {'params': {'request_id': 12}}, {'items': [SAVED]}),
    (['handle', '12'], 'handle_vendor_setup_request', {'request_id': 12},
     'PATCH', '/vendor-setup-requests/12', {'json_body': {'status': 'handled'}}, {**SAVED, 'status': 'handled'}),
]


class Api:
    profile = SimpleNamespace(auth='service')
    def __init__(self, value):
        self.value, self.calls = value, []
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.value


@pytest.mark.parametrize('argv,name,arguments,method,path,kwargs,value', CASES)
def test_cli_and_local_sdk_use_canonical_tire_setup(monkeypatch, argv, name, arguments, method, path, kwargs, value):
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['tire-vendor', *argv])
    assert parsed.handler(parsed) == value
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools[name].annotations.readOnlyHint is (method == 'GET')
            result = await sdk.call_tool(name, arguments)
            assert not result.isError and result.structuredContent == value
    asyncio.run(check())
    assert api.calls == [(method, path, kwargs)] * 2


@pytest.mark.parametrize('name,arguments', [
    ('share_tire_vendor_contact', {'station_code': 'TEST1', 'vendor_name': 'Shop', 'contact_name': 'Desk'}),
    ('list_station_tire_vendors', {'dsp_id': '../7'}),
    ('add_station_tire_vendor', {'station_code': 'TEST1', 'vendor_workshop_id': 0}),
    ('handle_vendor_setup_request', {'request_id': -1}),
])
def test_invalid_input_never_transports(name, arguments):
    api = Api({})
    with pytest.raises(ValidationError):
        CustomerReadService(api).run(name, arguments)
    assert api.calls == []


def test_malformed_write_result_is_unknown_without_retry():
    api = Api({**SAVED, 'status': 'handled'})
    with pytest.raises(ApiError) as error:
        CustomerReadService(api).run('share_tire_vendor_contact',
            {'station_code': 'TEST1', 'vendor_name': 'Local Tires', 'contact_name': 'Desk', 'contact_phone': '+17035550100'})
    assert error.value.code == 'outcome_unknown' and len(api.calls) == 1
