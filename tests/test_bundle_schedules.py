import asyncio
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import bundle_schedules, cli, legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

SCHEDULE = {'version': 'current-version', 'status': 'pending', 'pickup_start': '2026-06-20T00:00:00Z',
    'pickup_end': '2026-06-20T05:00:00Z', 'return_start': '2026-06-22T00:00:00Z',
    'return_end': '2026-06-22T05:00:00Z', 'timezone': 'UTC'}


class Api:
    profile = SimpleNamespace(auth='service')

    def __init__(self):
        self.calls = []

    def request(self, method, path, *, json_body=None):
        kwargs = {} if json_body is None else {"json_body": json_body}
        self.calls.append((method, path, kwargs))
        if method == 'GET':
            return {'rows': [{'ref': 'DFS-B-2026-0001', 'unit': 1, 'vehicle': 'Test van', 'visit_number': 2, 'visit_label': 'Test van · Follow-up 2', 'schedule': SCHEDULE}]}
        return {'schedule': {**SCHEDULE, 'status': kwargs['json_body']['decision']}}


@pytest.mark.parametrize('decision', ['approved', 'declined'])
def test_cli_and_mcp_submit_exact_version_once(monkeypatch, decision):
    api = Api()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['bundle-schedules', 'decide', 'DFS-B-2026-0001', '1', '--version', SCHEDULE['version'], '--decision', decision])
    assert parsed.handler(parsed)['schedule']['status'] == decision

    listed = cli.build_parser().parse_args(['bundle-schedules', 'list'])
    row = listed.handler(listed)['rows'][0]
    assert row['visit_number'] == 2
    assert row['visit_label'] == 'Test van · Follow-up 2'

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert not tools[bundle_schedules.WRITE].annotations.readOnlyHint
            assert 'For an AMR follow-up, approval confirms the dates.' in tools[bundle_schedules.WRITE].description
            assert 'The shop is charged at pickup.' in tools[bundle_schedules.WRITE].description
            assert 'El cargo al taller se realiza en la recogida.' in tools[bundle_schedules.WRITE].description
            read = await sdk.call_tool(bundle_schedules.READ, {})
            assert read.structuredContent['rows'][0]['schedule']['version'] == SCHEDULE['version']
            assert read.structuredContent['rows'][0]['visit_number'] == 2
            assert read.structuredContent['rows'][0]['visit_label'] == 'Test van · Follow-up 2'
            result = await sdk.call_tool(bundle_schedules.WRITE, {'ref': 'DFS-B-2026-0001', 'unit': 1, 'version': SCHEDULE['version'], 'decision': decision})
            assert not result.isError and result.structuredContent['schedule']['status'] == decision
    asyncio.run(check())
    writes = [call for call in api.calls if call[0] == 'POST']
    assert writes == [('POST', '/bundle-offers/DFS-B-2026-0001/vans/1/schedule-decision', {'json_body': {'version': SCHEDULE['version'], 'decision': decision}})] * 2


def test_invalid_schedule_reference_never_reaches_transport():
    api = Api()
    with pytest.raises(ValidationError):
        bundle_schedules.execute(api, bundle_schedules.WRITE, {'ref': '../schedules', 'unit': 1, 'version': 'v', 'decision': 'approved'})
    assert not api.calls


def test_unconfirmed_response_is_unknown_and_not_retried():
    class WrongVersion(Api):
        def request(self, *args, **kwargs):
            result = super().request(*args, **kwargs)
            result['schedule']['version'] = 'stale'
            return result
    api = WrongVersion()
    with pytest.raises(ApiError) as failure:
        bundle_schedules.execute(api, bundle_schedules.WRITE, {'ref': 'DFS-B-2026-0001', 'unit': 1, 'version': SCHEDULE['version'], 'decision': 'approved'})
    assert failure.value.code == 'outcome_unknown'
    assert len(api.calls) == 1


def test_cli_help_explains_follow_up_charge_timing(capsys):
    with pytest.raises(SystemExit) as result:
        cli.build_parser().parse_args(['bundle-schedules', 'decide', '--help'])
    assert result.value.code == 0
    help_text = ' '.join(capsys.readouterr().out.split())
    assert 'For an AMR follow-up, approval confirms the dates.' in help_text
    assert 'The shop is charged at pickup.' in help_text
    assert 'El cargo al taller se realiza en la recogida.' in help_text


def test_schedule_decision_reuses_existing_customer_consent(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from nova_cli_public import delegated
    from nova_cli_public.errors import AuthError, UsageError

    opened = []
    monkeypatch.setattr(delegated.webbrowser, 'open', lambda url: opened.append(url) or False)
    operation = 'capacity.schedules.decide.v1'
    with pytest.raises(UsageError, match='require --scope'):
        delegated.browser_code('https://nova.example', operations=operation)
    assert not opened
    with pytest.raises(AuthError):
        delegated.browser_code('https://nova.example', operations=operation,
                               scope='nova:read nova:write')
    query = parse_qs(urlsplit(opened[0]).query)
    assert query['scope'] == ['nova:read nova:write']
    assert query['operations'] == [operation]
