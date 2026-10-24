import asyncio
import io
import json
from email.message import Message
from urllib.parse import urlsplit

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

PAGE = {'items': [{'id': 'PH-3', 'url': 'https://provider.example/photo', 'extension': True}],
        'total': 1, 'extension': {'preserve': True}}


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
    api = ApiClient(Profile('photos', 'https://nova.example/api', 'keyring', 'delegated'), None, opener=Opener(value))
    api.access_token = 'synthetic-private-token'
    return api


def test_cli_and_sdk_preserve_photo_reference_page_without_provider_fetch(monkeypatch, capsys):
    api = client()
    monkeypatch.setattr('nova_cli_public.legacy_reads.client_from_args', lambda args: api)
    assert cli.main(['--json', 'defect', 'list-photos', 'FD-0007']) == 0
    assert json.loads(capsys.readouterr().out) == PAGE
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as session:
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            tool = tools['list_defect_photos']
            assert tool.inputSchema['additionalProperties'] is False
            assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
            result = await session.call_tool('list_defect_photos', {'defect_id': 'FD-0007'})
            assert not result.isError and result.structuredContent == PAGE
            assert json.loads(result.content[0].text) == PAGE
    asyncio.run(check())
    assert len(api.opener.requests) == 2
    assert all(request.get_method() == 'GET' and urlsplit(request.full_url).path == '/api/defects/FD-0007/photos'
               and request.get_header('Authorization') == 'Bearer synthetic-private-token' for request in api.opener.requests)
    entry = manifest(cli.build_parser(), 'defect list-photos')['commands'][0]
    assert entry['required_operation'] == 'defects.photos.list.v1' and entry['effects'] == ['remote_read']
    assert entry['required_operation'] not in delegated.DEFAULT_OPERATIONS.split()


@pytest.mark.parametrize('reference', ['FD-0', '2147483648', '../escape', 'VAN-1', '9' * 101])
def test_photo_reference_invalid_id_stops_before_credentials(monkeypatch, reference):
    monkeypatch.setattr('nova_cli_public.legacy_reads.client_from_args', lambda args: pytest.fail('Invalid ID loaded credentials'))
    args = cli.build_parser().parse_args(['defect', 'list-photos', reference])
    with pytest.raises(ValidationError):
        args.handler(args)


@pytest.mark.parametrize('arguments', [{'defect_id': '7', 'url': 'https://evil.example'},
    {'defect_id': '7', 'out': 'file'}, {'defect_id': True}])
def test_photo_reference_tool_rejects_caller_urls_files_and_nonstring_ids(arguments):
    api = client()
    with pytest.raises(ValidationError):
        CustomerReadService(api).run('list_defect_photos', arguments)
    assert not api.opener.requests


@pytest.mark.parametrize('value', [[], {'items': ['bad'], 'total': 1}, {'items': [], 'total': True},
    {'items': [], 'total': -1}, {'items': []}])
def test_photo_reference_malformed_response_is_not_success(value):
    with pytest.raises(ApiError):
        CustomerReadService(client(value)).run('list_defect_photos', {'defect_id': '7'})
