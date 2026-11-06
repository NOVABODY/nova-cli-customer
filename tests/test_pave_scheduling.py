import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads, pave_scheduling
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

AT = '2026-11-09T02:00:00Z'
CASES = [
    ('request VAN-00007', 'request_vehicle_pave_scan', {'vehicle_id': 'VAN-00007'}, 'POST', '/vehicles/VAN-00007/pave-scan-requests', {}, {'id': 7, 'state': 'requested'}),
    ('cancel-request VAN-7 7', 'cancel_vehicle_pave_scan_request', {'vehicle_id': 'VAN-7', 'booking_id': 7}, 'POST', '/vehicles/VAN-7/pave-scan-requests/7/cancel', {}, None),
    ('upcoming DSP-7', 'list_dsp_pave_scans', {'dsp_id': 'DSP-7'}, 'GET', '/dashboards/dsp/DSP-7/upcoming-pave-scans', {}, [{'id': 7}]),
    ('request-change DSP-7 7 --preferred-at ' + AT, 'request_pave_scan_schedule_change', {'dsp_id': 'DSP-7', 'booking_id': 7, 'preferred_at': AT}, 'POST', '/dashboards/dsp/DSP-7/pave-scans/7/change-request', {'preferred_at': AT}, {'id': 7, 'change_requested_for': AT}),
    ('platform-list', 'list_platform_pave_scans', {}, 'GET', '/dashboards/platform-pave-scans', {}, {'requests': [{'id': 7}]}),
    ('workshop-list VW-7', 'list_workshop_pave_scans', {'workshop_id': 'VW-7'}, 'GET', '/dashboards/vendor-workshops/VW-7/pave-scans', {}, {'requests': [{'id': 7}]}),
    ('platform-schedule 7 --scheduled-at ' + AT, 'set_platform_pave_scan_schedule', {'booking_id': 7, 'scheduled_at': AT}, 'POST', '/dashboards/platform-pave-scans/7/schedule', {'scheduled_at': AT}, {'id': 7, 'scheduled_at': AT}),
    ('workshop-schedule 7 VW-7 --scheduled-at ' + AT, 'set_workshop_pave_scan_schedule', {'booking_id': 7, 'workshop_id': 'VW-7', 'scheduled_at': AT}, 'POST', '/dashboards/vendor-workshops/VW-7/pave-scans/7/schedule', {'scheduled_at': AT}, {'id': 7, 'scheduled_at': AT}),
    ('platform-cancel 7', 'cancel_platform_pave_scan', {'booking_id': 7}, 'POST', '/dashboards/platform-pave-scans/7/cancel', {}, {'id': 7, 'cancelled_at': AT}),
    ('workshop-cancel 7 VW-7', 'cancel_workshop_pave_scan', {'booking_id': 7, 'workshop_id': 'VW-7'}, 'POST', '/dashboards/vendor-workshops/VW-7/pave-scans/7/cancel', {}, {'id': 7, 'cancelled_at': AT}),
]


@pytest.mark.parametrize('command,name,arguments,method,path,fields,value', CASES)
def test_cli_and_sdk_use_native_scoped_route(monkeypatch, command, name, arguments, method, path, fields, value):
    api = SimpleNamespace(request=Mock(return_value=value), profile=SimpleNamespace(auth='service'))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    expected = {'items': value} if name == 'list_dsp_pave_scans' else {'scan_booking': value} if name == 'cancel_vehicle_pave_scan_request' else value
    args = cli.build_parser().parse_args(['pave-scan', *command.split()])
    assert args.handler(args) == expected
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools[name].annotations.readOnlyHint is (method == 'GET')
            result = await sdk.call_tool(name, arguments)
            assert not result.isError and result.structuredContent == expected
    asyncio.run(check())
    options = {'query': fields} if method == 'GET' else {'json_body': fields, 'retry_auth': False}
    assert api.request.call_args_list == [((method, path), options)] * 2


@pytest.mark.parametrize('name,arguments', [
    ('set_platform_pave_scan_schedule', {'booking_id': 7, 'scheduled_at': '2026-11-09T02:00:00'}),
    ('request_vehicle_pave_scan', {'vehicle_id': 'VAN-0'}),
    ('list_workshop_pave_scans', {'workshop_id': '../7'}),
    ('list_platform_pave_scans', {'start': '2026-11-09', 'end': '2026-11-08'}),
    ('request_vehicle_pave_scan', {'vehicle_id': 'VAN-7', 'scheduled_at': AT}),
])
def test_invalid_schedule_input_makes_no_request(name, arguments):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        pave_scheduling.execute(api, name, arguments)
    api.request.assert_not_called()


@pytest.mark.parametrize('failure', [ApiError('lost'), ApiError('unavailable', status=503), {'id': 'wrong'}, {'id': 7}, {'id': 7, 'scheduled_at': '2026-11-10T02:00:00Z'}])
def test_schedule_uncertain_outcome_requires_readback(failure):
    api = SimpleNamespace(request=Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure))
    with pytest.raises(ApiError) as error:
        pave_scheduling.execute(api, 'set_platform_pave_scan_schedule', {'booking_id': 7, 'scheduled_at': AT})
    assert error.value.code == 'outcome_unknown'
    assert api.request.call_count == 1
