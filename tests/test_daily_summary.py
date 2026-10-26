"""Summary selection and acknowledgment pass through the delegated client."""
import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

DATE = '2026-06-14'
SUMMARY = {'service_date': DATE, 'timezone': 'America/Los_Angeles', 'acknowledged': False,
    'counts': {'scheduled': 1, 'completed': 1, 'open': 0, 'canceled': 0},
    'completed': [{'native': True, 'defects': [{'label': 'Tire'}]}], 'open': [], 'canceled': []}
ACK = {'service_date': DATE, 'acknowledged': True, 'acknowledged_at': DATE + 'T12:00:00Z'}


class Api:
    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.value


@pytest.mark.parametrize('action,tool,value', [('summary', 'get_dsp_daily_work_summary', SUMMARY),
    ('acknowledge', 'acknowledge_dsp_daily_work_summary', ACK)])
def test_cli_and_sdk_use_native_receipt_and_single_request(monkeypatch, action, tool, value):
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['daily-work', action, 'DSP-7', '--service-date', DATE])
    assert args.handler(args) == value
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {t.name: t for t in (await sdk.list_tools()).tools}
            assert tools[tool].annotations.readOnlyHint is (action == 'summary')
            result = await sdk.call_tool(tool, {'dsp_id': 'DSP-7', 'service_date': DATE})
            assert not result.isError and result.structuredContent == value
    asyncio.run(check())
    suffix = '' if action == 'summary' else '/' + DATE + '/acknowledge'
    expected = ('GET' if action == 'summary' else 'POST', '/dashboards/dsp/DSP-7/daily-work-summary' + suffix,
        {'query': {'service_date': DATE}} if action == 'summary' else {})
    assert api.calls == [expected, expected]


def test_omitted_summary_date_preserves_native_yesterday():
    api = Api(SUMMARY)
    assert CustomerReadService(api).run('get_dsp_daily_work_summary', {'dsp_id': '7'}) == SUMMARY
    assert api.calls[0][2] == {'query': {}}


@pytest.mark.parametrize('tool,args', [('acknowledge_dsp_daily_work_summary', {'dsp_id': '7'}),
    ('get_dsp_daily_work_summary', {'dsp_id': '../7'}),
    ('get_dsp_daily_work_summary', {'dsp_id': '7', 'service_date': '2026-02-30'}),
    ('acknowledge_dsp_daily_work_summary', {'dsp_id': '7', 'service_date': DATE, 'extra': 1})])
def test_bad_query_never_transports(tool, args):
    api = Api(SUMMARY)
    with pytest.raises(ValidationError):
        CustomerReadService(api).run(tool, args)
    assert not api.calls


@pytest.mark.parametrize('value', [{}, {**ACK, 'service_date': '2026-06-15'},
    {**ACK, 'acknowledged': False}, {**ACK, 'acknowledged_at': '2026-06-14T12:00:00'},
    {**ACK, 'extra': float('nan')}])
def test_bad_ack_receipt_is_unknown_without_retry(value):
    api = Api(value)
    with pytest.raises(ApiError) as error:
        CustomerReadService(api).run('acknowledge_dsp_daily_work_summary', {'dsp_id': '7', 'service_date': DATE})
    assert error.value.code == 'outcome_unknown' and len(api.calls) == 1


@pytest.mark.parametrize('value', [{}, {**SUMMARY, 'counts': {'scheduled': True}},
    {**SUMMARY, 'completed': [False]}, {**SUMMARY, 'service_date': '2026-06-15'}])
def test_bad_summary_is_not_success(value):
    api = Api(value)
    with pytest.raises(ApiError):
        CustomerReadService(api).run('get_dsp_daily_work_summary', {'dsp_id': '7', 'service_date': DATE})
    assert len(api.calls) == 1
