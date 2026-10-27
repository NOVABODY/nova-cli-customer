"""The native scheduled-work day passes unchanged through CLI and local SDK."""
import asyncio
import io
import json
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

VALUE = {'service_date': '2026-06-14', 'timezone': 'America/New_York', 'items': [{'action_work_order_id': 5, 'native': True}]}
TOOL = 'list_dsp_scheduled_work'
ARGS = {'dsp_id': 'DSP-7', 'service_date': '2026-06-14'}


class Opener:
    def __init__(self, value=VALUE):
        self.value, self.calls = value, []

    def open(self, request, timeout):
        self.calls.append(request)
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'application/json'
        return response


def client(opener):
    api = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    api.access_token = 'synthetic-access'
    return api


def test_cli_and_sdk_keep_native_schedule_and_required_date(monkeypatch):
    opener = Opener()
    api = client(opener)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['daily-work', 'scheduled', 'DSP-7', '--service-date', ARGS['service_date']])
    assert args.handler(args) == VALUE
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools[TOOL].annotations.readOnlyHint
            assert {'get_dsp_home', 'get_vendor_home'}.isdisjoint(tools)
            result = await sdk.call_tool(TOOL, ARGS)
            assert not result.isError and result.structuredContent == VALUE
    asyncio.run(check())
    assert len(opener.calls) == 2
    for request in opener.calls:
        assert request.method == 'GET' and request.data is None
        assert urlsplit(request.full_url).path == '/api/dashboards/dsp/DSP-7/scheduled-work'
        assert parse_qs(urlsplit(request.full_url).query) == {'service_date': [ARGS['service_date']]}


@pytest.mark.parametrize('arguments', [
    {'dsp_id': '../7', 'service_date': ARGS['service_date']}, {'dsp_id': 'DSP-0', 'service_date': ARGS['service_date']},
    {'dsp_id': 'DSP-2147483648', 'service_date': ARGS['service_date']}, {'dsp_id': '7'},
    {'dsp_id': '7', 'service_date': '2026-02-30'}, {**ARGS, 'days': 2},
])
def test_invalid_schedule_query_fails_before_transport(arguments):
    with pytest.raises(ValidationError):
        CustomerReadService(object()).run(TOOL, arguments)


@pytest.mark.parametrize('value', [{}, {**VALUE, 'service_date': '2026-06-15'}, {**VALUE, 'timezone': ''},
    {**VALUE, 'items': [False]}, {**VALUE, 'extra': float('nan')}])
def test_malformed_or_other_day_schedule_is_not_success(value):
    from nova_cli_public.errors import ApiError
    opener = Opener(value)
    with pytest.raises(ApiError):
        CustomerReadService(client(opener)).run(TOOL, ARGS)
    assert len(opener.calls) == 1
