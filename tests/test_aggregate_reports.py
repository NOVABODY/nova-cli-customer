"""Aggregate reads preserve native reports and server defaults."""
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

REPORTS = ['work_order_completion', 'repair_metrics', 'inspection_compliance']
VALUE = {'date_from': '2026-10-01', 'date_to': '2026-10-26', 'native': {'nullable': None, 'ratio': 1.25}, 'total_completed': 0, 'rows': [], 'eligible_completed_count': 0, 'daily': [], **dict.fromkeys(['active_vehicles', 'submitted_inspections', 'vehicles_inspected', 'passed', 'flagged', 'conditional', 'incomplete'], 0)}

class Opener:
    def __init__(self, value=VALUE):
        self.value, self.calls = value, []

    def open(self, request, timeout):
        self.calls.append(request)
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'application/json'
        return response

@pytest.mark.parametrize('report', REPORTS)
@pytest.mark.parametrize('filters', [{}, {'date_from': '2026-10-01', 'date_to': '2026-10-26', 'dsp_id': 'bad-filter'}, {'dsp_id': ''}])
def test_cli_and_stdio_preserve_reports_filters_and_omitted_defaults(monkeypatch, report, filters):
    opener = Opener()
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    flags = [part for key, value in filters.items() for part in ['--' + key.replace('_', '-'), value]]
    parsed = cli.build_parser().parse_args(['report', report.replace('_', '-'), *flags])
    assert parsed.handler(parsed) == VALUE
    assert CustomerReadService(client).run('get_' + report + '_report', filters) == VALUE
    assert len(opener.calls) == 2
    for request in opener.calls:
        assert request.method == 'GET' and request.data is None
        assert urlsplit(request.full_url).path == '/api/dashboards/reports/' + report.replace('_', '-')
        assert parse_qs(urlsplit(request.full_url).query, keep_blank_values=True) == {key: [value] for key, value in filters.items()}

@pytest.mark.parametrize('report,args', [('inspection_compliance', {'vendor_workshop_id': 'VW-1'}), ('repair_metrics', {'date_from': '2026-02-30'}), ('work_order_completion', {'date_to': '20261001'}), ('repair_metrics', {'dsp_id': 3}), ('repair_metrics', {'dsp_id': 'x' * 201}), ('repair_metrics', {'url': 'https://other.example'})])
def test_closed_report_inputs_fail_before_transport(report, args):
    with pytest.raises(ValidationError):
        CustomerReadService(object()).run('get_' + report + '_report', args)

def test_stdio_sdk_discovers_three_read_reports_and_retains_native_json():
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.mcp import create_server

    async def check():
        opener = Opener()
        client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
        client.access_token = 'synthetic-access'
        async with create_connected_server_and_client_session(create_server(CustomerReadService(client))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            for report in REPORTS:
                name = 'get_' + report + '_report'
                assert tools[name].annotations.readOnlyHint
                result = await sdk.call_tool(name, {})
                assert not result.isError and result.structuredContent == VALUE
            assert len(opener.calls) == 3
    asyncio.run(check())

@pytest.mark.parametrize('value', [[], {}, {'date_from': '2026-10-01', 'date_to': '2026-10-26'}, {'date_from': '2026-10-01', 'date_to': '2026-10-26', 'total_completed': 0, 'rows': []}, {**VALUE, 'extra': float('nan')}, {**VALUE, 'extra': float('inf')}])
def test_nonobject_missing_dates_and_nonfinite_reports_are_not_success(value):
    from nova_cli_public.errors import ApiError

    opener = Opener(value)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    with pytest.raises(ApiError):
        CustomerReadService(client).run('get_repair_metrics_report', {})

@pytest.mark.parametrize('report', ['work_order_completion', 'repair_metrics'])
def test_native_workshop_filter_passes_through(report):
    opener = Opener()
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    assert CustomerReadService(client).run('get_' + report + '_report', {'vendor_workshop_id': 'invalid-native-filter'}) == VALUE
    assert parse_qs(urlsplit(opener.calls[0].full_url).query) == {'vendor_workshop_id': ['invalid-native-filter']}

@pytest.mark.parametrize('status', [400, 401, 403, 404])
def test_report_errors_remain_errors_without_retry(status):
    from urllib.error import HTTPError

    from nova_cli_public.errors import ApiError, TokenStoreUnavailable

    class Denied(Opener):
        def open(self, request, timeout):
            self.calls.append(request)
            raise HTTPError(request.full_url, status, '', Message(), io.BytesIO(b'{}'))

    opener = Denied()
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    with pytest.raises(TokenStoreUnavailable if status == 401 else ApiError):
        CustomerReadService(client).run('get_repair_metrics_report', {})
    assert len(opener.calls) == 1
