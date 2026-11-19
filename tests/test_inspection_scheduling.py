"""CLI and local MCP keep selected stations and use the real transport signature."""
import asyncio
import inspect
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public import inspection_scheduling as scheduling
from nova_cli_public.client import ApiClient
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

AT = '2027-01-04T20:00:00Z'
VISIT = {'id': 9, 'dsp_id': 7, 'vendor_workshop_id': None, 'station_codes': ['DVA1', 'DVA2'], 'scheduled_at': AT}
RECURRENCE = {'id': 10, 'dsp_id': 7, 'vendor_workshop_id': 3, 'station_codes': ['DVA1'],
              'weekday': 0, 'cadence': 'weekly', 'anchor_date': '2027-01-04', 'local_time': '20:00:00', 'is_active': True}
CASES = [
    ('stations --dsp-id 7 --workshop-id 3', 'list_inspection_stations', {'dsp_id': 7, 'workshop_id': 3},
     'GET', '/dashboards/inspection-stations', {'dsp_id': 7, 'vendor_workshop_id': 3}, [{'code': 'DVA1', 'name': 'North'}]),
    ('list', 'list_inspection_schedules', {}, 'GET', '/dashboards/platform-inspections', {'include_past': False}, [VISIT]),
    ('create --dsp-id 7 --scheduled-at ' + AT + ' --station-code DVA1 --station-code DVA2',
     'create_inspection_schedule', {'dsp_id': 7, 'scheduled_at': AT, 'station_codes': ['DVA1', 'DVA2']},
     'POST', '/dashboards/platform-inspections', {'dsp_id': 7, 'scheduled_at': AT, 'station_codes': ['DVA1', 'DVA2']}, VISIT),
    ('cancel --schedule-id 9', 'cancel_inspection_schedule', {'schedule_id': 9}, 'POST',
     '/dashboards/platform-inspections/9/cancel', {}, {**VISIT, 'cancelled_at': AT}),
    ('recurrences --workshop-id 3', 'list_inspection_recurrences', {'workshop_id': 3}, 'GET',
     '/dashboards/vendor-home/3/dvic-schedule-recurrences', {'include_inactive': False}, [RECURRENCE]),
    ('create-recurrence --workshop-id 3 --dsp-id 7 --weekday 0 --anchor-date 2027-01-04 --local-time 20:00 --station-code DVA1',
     'create_inspection_recurrence', {'workshop_id': 3, 'dsp_id': 7, 'weekday': 0, 'anchor_date': '2027-01-04', 'local_time': '20:00', 'station_codes': ['DVA1']},
     'POST', '/dashboards/vendor-home/3/dvic-schedule-recurrences', {'dsp_id': 7, 'weekday': 0, 'cadence': 'weekly', 'anchor_date': '2027-01-04', 'local_time': '20:00', 'station_codes': ['DVA1']}, RECURRENCE),
    ('update-recurrence --workshop-id 3 --recurrence-id 10 --station-code DVA1', 'update_inspection_recurrence',
     {'workshop_id': 3, 'recurrence_id': 10, 'station_codes': ['DVA1']}, 'PATCH', '/dashboards/vendor-home/3/dvic-schedule-recurrences/10',
     {'station_codes': ['DVA1']}, RECURRENCE),
]


class Api:
    profile = SimpleNamespace(auth='service')

    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, *args, **kwargs):
        inspect.signature(ApiClient.request).bind(self, *args, **kwargs)
        self.calls.append((args, kwargs))
        return self.value


@pytest.mark.parametrize('command,name,arguments,method,path,fields,value', CASES)
def test_cli_and_mcp_use_scoped_schedule_contract(monkeypatch, command, name, arguments, method, path, fields, value):
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['inspection-schedule', *command.split()])
    expected = {'items': value} if method == 'GET' else value
    assert parsed.handler(parsed) == expected

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            result = await sdk.call_tool(name, arguments)
            assert not result.isError and result.structuredContent == expected
    asyncio.run(check())
    assert api.calls == [((method, path), {'query': fields} if method == 'GET' else
                          {'json_body': fields, 'retry_auth': False})] * 2


@pytest.mark.parametrize('changes', [{'station_codes': []}, {'station_codes': ['../bad']},
                                     {'scheduled_at': '2027-01-04T20:00:00'}, {'unexpected': True}])
def test_invalid_station_schedule_is_rejected_before_transport(changes):
    api = Api(VISIT)
    with pytest.raises(ValidationError):
        scheduling.execute(api, 'create_inspection_schedule',
                           {'dsp_id': 7, 'scheduled_at': AT, 'station_codes': ['DVA1'], **changes})
    assert api.calls == []


def test_changed_station_response_is_unknown_and_never_replayed():
    api = Api(VISIT)
    with pytest.raises(ApiError, match='outcome is unknown'):
        scheduling.execute(api, 'create_inspection_schedule', {'dsp_id': 7, 'scheduled_at': AT, 'station_codes': ['DVA1']})
    assert len(api.calls) == 1
