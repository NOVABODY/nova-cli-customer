"""Real customer transports preserve native scorecard results and filter semantics."""
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

SCORE = {'vendor_workshop_id': 7, 'window_days': 90, 'total_feedback': 2,
         'satisfaction_pct': 50.0, 'recent': [{'native': {'kept': True}}], 'native_extra': None}
BENCH = {'primary_vendor_pct': 50.0, 'best_in_station_pct': 75.0, 'best_in_class_pct': None}


class Opener:
    def __init__(self, value):
        self.value, self.calls = value, []

    def open(self, request, timeout):
        self.calls.append(request)
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'application/json'
        return response


@pytest.mark.parametrize('action,tool,filters,value', [
    ('get', 'get_vendor_scorecard', {}, SCORE),
    ('get', 'get_vendor_scorecard', {'days': 30, 'subject_kind': 'body_repair'}, SCORE),
    ('benchmarks', 'get_vendor_scorecard_benchmarks', {}, BENCH),
    ('benchmarks', 'get_vendor_scorecard_benchmarks', {'days': 365, 'dsp_id': ''}, BENCH),
    ('benchmarks', 'get_vendor_scorecard_benchmarks', {'dsp_id': 'native-invalid'}, BENCH),
])
def test_cli_and_stdio_native_scorecards_omit_defaults_and_keep_all_fields(monkeypatch, action, tool, filters, value):
    opener = Opener(value)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    flags = [part for key, item in filters.items() for part in ['--' + key.replace('_', '-'), str(item)]]
    args = cli.build_parser().parse_args(['vendor-scorecard', action, 'VW-7', *flags])
    assert args.handler(args) == value
    assert CustomerReadService(client).run(tool, {'vendor_workshop_id': 'VW-7', **filters}) == value
    assert len(opener.calls) == 2
    for request in opener.calls:
        assert request.method == 'GET' and request.data is None
        assert urlsplit(request.full_url).path == '/api/vendor-scorecard/VW-7' + ('/benchmarks' if action == 'benchmarks' else '')
        assert parse_qs(urlsplit(request.full_url).query, keep_blank_values=True) == {key: [str(item)] for key, item in filters.items()}


@pytest.mark.parametrize('tool,args', [
    ('get_vendor_scorecard', {'vendor_workshop_id': '../7'}),
    ('get_vendor_scorecard', {'vendor_workshop_id': 'VW-0'}),
    ('get_vendor_scorecard', {'vendor_workshop_id': 'VW-2147483648'}),
    ('get_vendor_scorecard', {'vendor_workshop_id': '7', 'days': True}),
    ('get_vendor_scorecard', {'vendor_workshop_id': '7', 'days': 366}),
    ('get_vendor_scorecard', {'vendor_workshop_id': '7', 'subject_kind': ''}),
    ('get_vendor_scorecard', {'vendor_workshop_id': '7', 'dsp_id': 'DSP-1'}),
    ('get_vendor_scorecard_benchmarks', {'vendor_workshop_id': '7', 'dsp_id': 'x' * 201}),
    ('get_vendor_scorecard_benchmarks', {'vendor_workshop_id': '7', 'subject_kind': 'work_order'}),
])
def test_closed_scorecard_inputs_fail_before_transport(tool, args):
    with pytest.raises(ValidationError):
        CustomerReadService(object()).run(tool, args)


def test_stdio_sdk_discovers_both_native_scorecard_reads():
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.mcp import create_server

    async def check():
        opener = Opener(SCORE)
        client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
        client.access_token = 'synthetic-access'
        async with create_connected_server_and_client_session(create_server(CustomerReadService(client))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            for name, value in [('get_vendor_scorecard', SCORE), ('get_vendor_scorecard_benchmarks', BENCH)]:
                assert tools[name].annotations.readOnlyHint
                opener.value = value
                result = await sdk.call_tool(name, {'vendor_workshop_id': 'VW-7'})
                assert not result.isError and result.structuredContent == value
            assert len(opener.calls) == 2
    asyncio.run(check())


@pytest.mark.parametrize('tool,value', [
    ('get_vendor_scorecard', {}), ('get_vendor_scorecard', {**SCORE, 'vendor_workshop_id': 8}),
    ('get_vendor_scorecard', {**SCORE, 'total_feedback': True}),
    ('get_vendor_scorecard', {**SCORE, 'recent': [1]}),
    ('get_vendor_scorecard', {**SCORE, 'satisfaction_pct': '50'}),
    ('get_vendor_scorecard', {**SCORE, 'extra': float('nan')}),
    ('get_vendor_scorecard_benchmarks', {}),
    ('get_vendor_scorecard_benchmarks', {**BENCH, 'primary_vendor_pct': True}),
    ('get_vendor_scorecard_benchmarks', {**BENCH, 'extra': float('inf')}),
])
def test_malformed_mismatched_and_nonfinite_scorecards_are_not_success(tool, value):
    from nova_cli_public.errors import ApiError

    opener = Opener(value)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    with pytest.raises(ApiError):
        CustomerReadService(client).run(tool, {'vendor_workshop_id': '7'})
    assert len(opener.calls) == 1
