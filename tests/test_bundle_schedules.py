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

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method == 'GET':
            return {'rows': [{'ref': 'DFS-B-2026-0001', 'unit': 1, 'vehicle': 'Test van', 'schedule': SCHEDULE}]}
        return {'schedule': {**SCHEDULE, 'status': kwargs['json_body']['decision']}}


@pytest.mark.parametrize('decision', ['approved', 'declined'])
def test_cli_and_mcp_submit_exact_version_once(monkeypatch, decision):
    api = Api()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['bundle-schedules', 'decide', 'DFS-B-2026-0001', '1', '--version', SCHEDULE['version'], '--decision', decision])
    assert parsed.handler(parsed)['schedule']['status'] == decision

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert not tools[bundle_schedules.WRITE].annotations.readOnlyHint
            read = await sdk.call_tool(bundle_schedules.READ, {})
            assert read.structuredContent['rows'][0]['schedule']['version'] == SCHEDULE['version']
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
