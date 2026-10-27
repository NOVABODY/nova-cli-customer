"""Real customer transports preserve native quality_report results and filter semantics."""
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


class Opener:
    def __init__(self, value):
        self.value, self.calls = value, []

    def open(self, request, timeout):
        self.calls.append(request)
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'application/json'
        return response


ROWS = [{'inspector_id': 7, 'inspector_name': 'Synthetic', 'inspector_email': None,
    'total_reported': 2, 'illegitimate_count': 1, 'illegitimate_pct': 50.0, 'window_days': 30,
    'invalid_reports': [{'native': {'kept': None}}]}]


@pytest.mark.parametrize('action,tool,filters', [
    ('inspector-performance', 'list_inspector_performance', {}),
    ('inspector-performance', 'list_inspector_performance', {'days': 365, 'dsp_id': ''}),
    ('inspector-performance', 'list_inspector_performance', {'dsp_id': 'native-invalid'}),
    ('driver-da-quality', 'list_driver_da_quality', {}),
    ('driver-da-quality', 'list_driver_da_quality', {'days': 1}),
])
def test_cli_and_stdio_preserve_native_quality_rows_and_omitted_defaults(monkeypatch, action, tool, filters):
    opener = Opener(ROWS)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    flags = [part for key, item in filters.items() for part in ['--' + key.replace('_', '-'), str(item)]]
    args = cli.build_parser().parse_args(['report', action, *flags])
    assert args.handler(args) == ROWS
    assert CustomerReadService(client).run(tool, filters) == {'items': ROWS}
    assert len(opener.calls) == 2
    for request in opener.calls:
        assert request.method == 'GET' and request.data is None
        assert urlsplit(request.full_url).path == '/api/dashboards/' + action
        assert parse_qs(urlsplit(request.full_url).query, keep_blank_values=True) == {key: [str(item)] for key, item in filters.items()}


@pytest.mark.parametrize('tool,args', [('list_inspector_performance', {'days': True}),
    ('list_inspector_performance', {'days': 0}), ('list_inspector_performance', {'days': 366}),
    ('list_inspector_performance', {'dsp_id': 7}), ('list_inspector_performance', {'dsp_id': 'x' * 201}),
    ('list_driver_da_quality', {'dsp_id': 'DSP-7'}), ('list_driver_da_quality', {'url': 'https://other.example'})])
def test_closed_quality_report_inputs_fail_before_transport(tool, args):
    with pytest.raises(ValidationError):
        CustomerReadService(object()).run(tool, args)


@pytest.mark.parametrize('tool', ['list_inspector_performance', 'list_driver_da_quality'])
@pytest.mark.parametrize('value', [{}, [1], [{**ROWS[0], 'total_reported': True}], [{**ROWS[0], 'extra': float('inf')}]])
def test_malformed_quality_report_is_not_success(tool, value):
    from nova_cli_public.errors import ApiError
    opener = Opener(value)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    with pytest.raises(ApiError):
        CustomerReadService(client).run(tool, {})
    assert len(opener.calls) == 1


def test_sdk_quality_tools_are_read_only_and_preserve_empty_native_rows():
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.mcp import create_server
    async def check():
        opener = Opener([])
        client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
        client.access_token = 'synthetic-access'
        async with create_connected_server_and_client_session(create_server(CustomerReadService(client))) as sdk:
            tools = {entry.name: entry for entry in (await sdk.list_tools()).tools}
            for name in ['list_inspector_performance', 'list_driver_da_quality']:
                assert tools[name].annotations.readOnlyHint
                result = await sdk.call_tool(name, {})
                assert not result.isError and result.structuredContent == {'items': []}
        assert len(opener.calls) == 2
    asyncio.run(check())
