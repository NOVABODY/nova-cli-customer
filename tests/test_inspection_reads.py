import asyncio
import io
import json
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, delegated
from nova_cli_public.capabilities import manifest
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

DETAIL = {'id': 'INS-42', 'status': 'submitted', 'result': 'flagged',
    'defects': [{'id': 'FD-1', 'server_extension': {'retained': True}}],
    'photos': [{'url': '/api/inspections/42/photos/1'}], 'future_field': ['preserved']}
PAGE = {'items': [DETAIL], 'total': 51, 'page': 2, 'per_page': 20, 'server_extension': {'retained': True}}


class Opener:
    def __init__(self, value):
        self.value, self.requests = value, []

    def open(self, request, timeout):
        self.requests.append(request)
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'application/json'
        return response


def client(value=PAGE):
    api = ApiClient(Profile('public', 'https://nova.example/api', 'keyring', 'delegated'), None, opener=Opener(value))
    api.access_token = 'synthetic-private-token'
    return api


def test_cli_inspection_filters_keep_full_page_and_do_not_follow_pages():
    api = client()
    args = cli.build_parser().parse_args(['inspection', 'list', '--dsp-id', 'DSP-0001', '--vehicle-id', 'VAN-0002',
        '--date-from', '2026-01-01', '--date-to', '2026-01-31', '--result', 'flagged', '--status', 'submitted', '--page', '2', '--per-page', '20'])
    args._client = api
    assert args.handler(args) == PAGE
    assert len(api.opener.requests) == 1
    request = api.opener.requests[0]
    assert request.get_header('Authorization') == 'Bearer synthetic-private-token'
    assert urlsplit(request.full_url).path == '/api/inspections'
    assert parse_qs(urlsplit(request.full_url).query) == {'dsp_id': ['DSP-0001'], 'vehicle_id': ['VAN-0002'],
        'date_from': ['2026-01-01'], 'date_to': ['2026-01-31'], 'result': ['flagged'], 'status': ['submitted'], 'page': ['2'], 'per_page': ['20']}


@pytest.mark.parametrize('reference', ['42', 'INS-00042'])
def test_inspection_detail_preserves_entire_api_object_without_fetching_photos(reference):
    api = client(DETAIL)
    args = cli.build_parser().parse_args(['inspection', 'get', reference])
    args._client = api
    assert args.handler(args) == DETAIL
    assert [request.full_url for request in api.opener.requests] == ['https://nova.example/api/inspections/' + reference]


@pytest.mark.parametrize('arguments', [{'page': 0}, {'page': True}, {'page': 2147483648}, {'per_page': 101},
    {'dsp_id': 'DSP-0'}, {'vehicle_id': 'VAN-2147483648'}, {'status': 'unknown'}, {'result': 'unknown'},
    {'date_from': '2026-02-30'}, {'date_from': '2026-02-02', 'date_to': '2026-02-01'}, {'all': True}])
def test_inspection_list_arguments_fail_before_network(arguments):
    api = client()
    with pytest.raises(ValidationError):
        CustomerReadService(api).run('list_inspections', arguments)
    assert api.opener.requests == []


@pytest.mark.parametrize('reference', ['../escape', 'https://evil.example', 'INS-0', 'INS-2147483648', '9' * 100])
def test_inspection_reference_is_bounded_before_credentials(reference, monkeypatch):
    monkeypatch.setattr('nova_cli_public.legacy_reads.client_from_args', lambda args: pytest.fail('Invalid ID loaded credentials'))
    args = cli.build_parser().parse_args(['inspection', 'get', reference])
    with pytest.raises(ValidationError):
        args.handler(args)


@pytest.mark.parametrize('value', [[], {'items': [], 'total': True, 'page': 1, 'per_page': 20},
    {'items': ['bad'], 'total': 1, 'page': 1, 'per_page': 20}, {'items': [], 'total': 0, 'page': False, 'per_page': 20},
    {'items': [], 'total': 0, 'page': 1, 'per_page': 101}])
def test_inspection_list_validates_only_the_structural_envelope(value):
    with pytest.raises(ApiError):
        CustomerReadService(client(value)).run('list_inspections', {})


def test_sdk_inspection_discovery_calls_defaults_closed_arguments_and_consent():
    first = {**PAGE, 'page': 1}
    api = client(first)
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as session:
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            listing, detail = tools['list_inspections'], tools['get_inspection']
            assert listing.annotations.readOnlyHint and not listing.annotations.destructiveHint
            assert listing.inputSchema['additionalProperties'] is False
            assert listing.inputSchema['properties']['per_page']['maximum'] == 100
            assert listing.inputSchema['properties']['status']['default'] is None
            for name, arguments in [('list_inspections', {'scope': 'all'}), ('get_inspection', {'inspection_id': '42', 'photos': True})]:
                denied = await session.call_tool(name, arguments)
                assert denied.isError and denied.structuredContent['error']['code'] == 'invalid_arguments'
            assert api.opener.requests == []
            result = await session.call_tool(listing.name, {})
            assert not result.isError and result.structuredContent == first
            assert len(api.opener.requests) == 1
            assert parse_qs(urlsplit(api.opener.requests[0].full_url).query) == {'page': ['1'], 'per_page': ['20']}
            second = {**PAGE, 'per_page': 1}
            api.opener.value = second
            result = await session.call_tool(listing.name, {'dsp_id': 'DSP-0001', 'vehicle_id': 'VAN-0002', 'page': 2, 'per_page': 1})
            assert not result.isError and result.structuredContent == second
            assert parse_qs(urlsplit(api.opener.requests[-1].full_url).query) == {'dsp_id': ['DSP-0001'], 'vehicle_id': ['VAN-0002'], 'page': ['2'], 'per_page': ['1']}
            api.opener.value = DETAIL
            result = await session.call_tool(detail.name, {'inspection_id': 'INS-00042'})
            assert not result.isError and result.structuredContent == DETAIL
            assert 'synthetic-private-token' not in result.model_dump_json()
    asyncio.run(check())
    assert len(api.opener.requests) == 3
    for command, operation in [('inspection list', 'inspections.list.v1'), ('inspection get', 'inspections.get.v1')]:
        entry = manifest(cli.build_parser(), command)['commands'][0]
        assert entry['required_operation'] == operation and entry['effects'] == ['remote_read']
        assert operation in delegated.OPERATIONS and operation not in delegated.DEFAULT_OPERATIONS.split()
    assert delegated.DEFAULT_OPERATIONS == 'vehicles.list_full.v1 vehicles.get_full.v1'
