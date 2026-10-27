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


@pytest.mark.parametrize('action,tool,filters', [
    ('pending-feedback', 'list_pending_vendor_feedback', {}),
    ('pending-feedback', 'list_pending_vendor_feedback', {'days': 3650, 'dsp_id': ''}),
    ('pending-feedback', 'list_pending_vendor_feedback', {'dsp_id': 'native-invalid'}),
    ('problem-reports', 'list_vendor_problem_reports', {}),
    ('problem-reports', 'list_vendor_problem_reports', {'vendor_workshop_id': '', 'status': ' In_REVIEW '}),
    ('problem-reports', 'list_vendor_problem_reports', {'vendor_workshop_id': 'native-invalid', 'status': ''}),
])
def test_cli_and_stdio_keep_native_queue_rows_and_filters(monkeypatch, action, tool, filters):
    value = [{'native': {'nullable': None}, 'subject_kind': 'body_repair', 'summary': 'Synthetic'}]
    opener = Opener(value)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    flags = [part for key, item in filters.items() for part in ['--' + key.replace('_', '-'), str(item)]]
    args = cli.build_parser().parse_args(['vendor-scorecard', action, *flags])
    assert args.handler(args) == value
    assert CustomerReadService(client).run(tool, filters) == {'items': value}
    assert len(opener.calls) == 2
    for request in opener.calls:
        assert request.method == 'GET' and request.data is None
        assert urlsplit(request.full_url).path == '/api/vendor-scorecard/' + action
        assert parse_qs(urlsplit(request.full_url).query, keep_blank_values=True) == {key: [str(item)] for key, item in filters.items()}


@pytest.mark.parametrize('tool,args', [
    ('list_pending_vendor_feedback', {'days': True}), ('list_pending_vendor_feedback', {'days': 3651}),
    ('list_pending_vendor_feedback', {'days': 0}), ('list_pending_vendor_feedback', {'dsp_id': 7}),
    ('list_pending_vendor_feedback', {'vendor_workshop_id': '7'}),
    ('list_vendor_problem_reports', {'status': 1}), ('list_vendor_problem_reports', {'status': 'x' * 201}),
    ('list_vendor_problem_reports', {'dsp_id': 'DSP-7'}),
])
def test_closed_queue_inputs_fail_before_transport(tool, args):
    with pytest.raises(ValidationError):
        CustomerReadService(object()).run(tool, args)


@pytest.mark.parametrize('tool', ['list_pending_vendor_feedback', 'list_vendor_problem_reports'])
@pytest.mark.parametrize('value', [{}, [1], [{'bad': float('nan')}], [{'bad': float('inf')}]])
def test_malformed_native_queue_is_not_success(tool, value):
    from nova_cli_public.errors import ApiError
    opener = Opener(value)
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    with pytest.raises(ApiError):
        CustomerReadService(client).run(tool, {})
    assert len(opener.calls) == 1


def test_sdk_queue_tools_are_read_only_and_preserve_empty_native_list():
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.mcp import create_server
    async def check():
        opener = Opener([])
        client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
        client.access_token = 'synthetic-access'
        async with create_connected_server_and_client_session(create_server(CustomerReadService(client))) as sdk:
            tools = {entry.name: entry for entry in (await sdk.list_tools()).tools}
            for name in ['list_pending_vendor_feedback', 'list_vendor_problem_reports']:
                assert tools[name].annotations.readOnlyHint
                result = await sdk.call_tool(name, {})
                assert not result.isError and result.structuredContent == {'items': []}
        assert len(opener.calls) == 2
    asyncio.run(check())
