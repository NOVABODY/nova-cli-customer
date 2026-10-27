"""Named confirmation tools preserve explicit opt-in and one-appointment decisions."""
import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.read_routes import admitted_read
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.write_routes import admitted_write

WHEN = '2026-10-28T02:00:00Z'
STATUS = {'schedule_id': 7, 'confirmation_id': 17, 'status': 'confirmed', 'responded_at': WHEN, 'responded_by_id': 8}
SETTINGS = {'enabled': False, 'recipient_roles': 'owners_and_dispatchers'}


class Api:
    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.value


@pytest.mark.parametrize('argv,tool,arguments,method,path,body,value', [
    (['settings', 'DSP-7'], 'get_inspection_confirmation_settings', {'dsp_id': 'DSP-7'},
     'GET', 'settings/DSP-7', None, SETTINGS),
    (['set-settings', 'DSP-7', '--no-enabled'], 'update_inspection_confirmation_settings',
     {'dsp_id': 'DSP-7', 'enabled': False}, 'PATCH', 'settings/DSP-7', {'enabled': False}, SETTINGS),
    (['respond', '7', '--response', 'N', '--expected-scheduled-at', WHEN, '--expected-confirmation-id', '17'],
     'respond_inspection_confirmation', {'schedule_id': '7', 'response': 'N', 'expected_scheduled_at': WHEN, 'expected_confirmation_id': 17},
     'POST', '7/respond', {'response': 'N', 'expected_scheduled_at': WHEN, 'expected_confirmation_id': 17}, {**STATUS, 'status': 'declined'}),
    (['get', 'DVIC-7'], 'get_inspection_confirmation', {'schedule_id': 'DVIC-7'},
     'GET', 'DVIC-7', None, STATUS),
    (['respond', 'DVIC-7', '--response', 'Y', '--expected-scheduled-at', WHEN, '--expected-confirmation-id', '17'],
     'respond_inspection_confirmation', {'schedule_id': 'DVIC-7', 'response': 'Y', 'expected_scheduled_at': WHEN, 'expected_confirmation_id': 17},
     'POST', 'DVIC-7/respond', {'response': 'Y', 'expected_scheduled_at': WHEN, 'expected_confirmation_id': 17}, STATUS),
])
def test_cli_and_mcp_preserve_explicit_fields(monkeypatch, argv, tool, arguments, method, path, body, value):
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['inspection-confirmation', *argv])
    assert parsed.handler(parsed) == value
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {item.name: item for item in (await sdk.list_tools()).tools}
            assert tools[tool].annotations.readOnlyHint is (method == 'GET')
            result = await sdk.call_tool(tool, arguments)
            assert not result.isError and result.structuredContent == value
    asyncio.run(check())
    assert api.calls == [(method, '/inspection-confirmations/' + path,
        {} if body is None else {'json_body': body})] * 2
    capability = manifest(cli.build_parser(), 'inspection-confirmation ' + argv[0])['commands'][0]
    assert capability['required_scope'] == ('nova:read' if method == 'GET' else 'nova:read nova:write')
    assert capability['required_operation'].startswith('inspection_confirmations.')
    assert admitted_read('/inspection-confirmations/' + path) if method == 'GET' else admitted_write(method, '/inspection-confirmations/' + path)


@pytest.mark.parametrize('tool,arguments', [
    ('update_inspection_confirmation_settings', {'dsp_id': '7'}),
    ('update_inspection_confirmation_settings', {'dsp_id': '7', 'enabled': True, 'notify_sms': True}),
    ('update_inspection_confirmation_settings', {'dsp_id': '7', 'recipient_roles': 'everyone'}),
    ('get_inspection_confirmation_settings', {'dsp_id': 'DSP-0'}),
    ('get_inspection_confirmation', {'schedule_id': '../7'}),
    ('respond_inspection_confirmation', {'schedule_id': '7', 'response': 'Y', 'expected_scheduled_at': '2026-10-28T02:00:00', 'expected_confirmation_id': 17}),
    ('respond_inspection_confirmation', {'schedule_id': '7', 'response': 'maybe', 'expected_scheduled_at': WHEN, 'expected_confirmation_id': 17}),
])
def test_invalid_or_unrelated_settings_never_transport(tool, arguments):
    api = Api(STATUS)
    with pytest.raises(ValidationError):
        CustomerReadService(api).run(tool, arguments)
    assert api.calls == []


@pytest.mark.parametrize('value', [{}, {**STATUS, 'schedule_id': 9}, {**STATUS, 'confirmation_id': 18}, {**STATUS, 'status': 'pending'}])
def test_uncertain_decision_is_not_reported_as_success_or_retried(value):
    api = Api(value)
    with pytest.raises(ApiError) as exc:
        CustomerReadService(api).run('respond_inspection_confirmation',
            {'schedule_id': '7', 'response': 'Y', 'expected_scheduled_at': WHEN, 'expected_confirmation_id': 17})
    assert exc.value.code == 'outcome_unknown' and len(api.calls) == 1
