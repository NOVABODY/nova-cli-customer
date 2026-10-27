import asyncio

import pytest
from mcp import types
from pydantic import ValidationError

from nova_cli_public import cli, delegated
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.mcp import create_server
from nova_cli_public.read_routes import admitted_read
from nova_cli_public.reads import CustomerReadService

CASES = [
    ('vehicle pave-reports VAN-1', 'list_vehicle_pave_reports', {'vehicle_id': 'VAN-1'},
     '/vehicles/VAN-1/pave-reports', 'vehicles.pave_reports.list.v1',
     {'items': [{'source': 'customer_report', 'score': None}], 'can_scan': False, 'scan': None}),
    ('body-repair pave-reports BRR-1', 'list_body_repair_pave_reports', {'req_id': 'BRR-1'},
     '/body-repair/requests/BRR-1/pave', 'body_repair.pave.list.v1',
     [{'id': 2, 'phase': 'post', 'total_score': None, 'storage_key': ''}]),
    ('body-repair pave-comparison BRR-1', 'compare_body_repair_pave_reports', {'req_id': 'BRR-1'},
     '/body-repair/requests/BRR-1/pave/comparison', 'body_repair.pave.compare.v1',
     {'request_id': 'BRR-1', 'pre_report': None, 'post_report': None, 'new': []}),
]


class Client:
    def __init__(self, result):
        self.result, self.calls = result, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.result


@pytest.mark.parametrize('command,tool,arguments,path,grant,response', CASES)
def test_cli_and_local_tool_preserve_authorized_pave_projection(
    command, tool, arguments, path, grant, response,
):
    direct, local = Client(response), Client(response)
    args = cli.build_parser().parse_args(command.split())
    args._client = direct
    assert args.handler(args) == response
    result = CustomerReadService(local).run(tool, arguments)
    assert result == (response if isinstance(response, dict) else {'items': response})
    assert direct.calls == local.calls == [('GET', path, {})]
    assert admitted_read(path)
    entry = manifest(cli.build_parser(), command.rsplit(' ', 1)[0])['commands'][0]
    assert entry['required_operation'] == grant
    assert entry['required_scope'] == 'nova:read'
    assert entry['effects'] == ['remote_read']
    assert grant not in delegated.DEFAULT_OPERATIONS.split()


@pytest.mark.parametrize('command,tool,arguments,path,grant,response', CASES)
def test_pave_tool_sdk_schema_and_read_only_annotations(command, tool, arguments, path, grant, response):
    async def check():
        server = create_server(CustomerReadService(Client(response)))
        tools = await server.request_handlers[types.ListToolsRequest](types.ListToolsRequest())
        item = next(t for t in tools.root.tools if t.name == tool)
        assert item.annotations.readOnlyHint and item.annotations.idempotentHint
        assert item.annotations.destructiveHint is False
        assert item.inputSchema['additionalProperties'] is False
        result = await server.request_handlers[types.CallToolRequest](types.CallToolRequest(
            method='tools/call', params=types.CallToolRequestParams(name=tool, arguments=arguments)))
        assert not result.root.isError
        assert result.root.structuredContent == (
            response if isinstance(response, dict) else {'items': response})
    asyncio.run(check())


@pytest.mark.parametrize('tool,field', [
    ('list_vehicle_pave_reports', 'vehicle_id'),
    ('list_body_repair_pave_reports', 'req_id'),
    ('compare_body_repair_pave_reports', 'req_id'),
])
@pytest.mark.parametrize('value', ['../escape', 'BRR-1/pave/scan', 'https://example.test', '1?scan=true'])
def test_pave_ids_fail_before_any_request(tool, field, value):
    client = Client({})
    with pytest.raises((ValidationError, ValueError)):
        CustomerReadService(client).run(tool, {field: value})
    assert client.calls == []


def test_pave_adapter_does_not_admit_scan_image_or_general_body_routes():
    for path in ['/body-repair/requests/BRR-1/scope/edit', '/vehicles/VAN-1/pave-reports/scan',
                 '/body-repair/requests/BRR-1/pave/2/file', '/body-repair/requests/BRR-1/pave/image']:
        assert not admitted_read(path)
    client = Client({})
    with pytest.raises(ValidationError):
        CustomerReadService(client).run('list_body_repair_pave_reports', {'req_id': 'BRR-1', 'scan': True})
    assert client.calls == []


@pytest.mark.parametrize('status,code', [(401, 'authentication_required'), (403, 'forbidden'), (404, 'not_found')])
def test_pave_sdk_keeps_authorization_denials_private(status, code):
    class Denied(Client):
        def request(self, *args, **kwargs):
            raise ApiError('PRIVATE RESPONSE', status=status)
    server = create_server(CustomerReadService(Denied({})))
    result = asyncio.run(server.request_handlers[types.CallToolRequest](types.CallToolRequest(
        method='tools/call', params=types.CallToolRequestParams(
            name='list_body_repair_pave_reports', arguments={'req_id': 'BRR-1'}))))
    assert result.root.structuredContent == {'error': {'code': code}}
    assert 'PRIVATE RESPONSE' not in result.model_dump_json()


def test_cli_invalid_pave_id_makes_no_request():
    client = Client({})
    args = cli.build_parser().parse_args(['body-repair', 'pave-reports', '../escape'])
    args._client = client
    with pytest.raises(UsageError):
        args.handler(args)
    assert client.calls == []


def test_cli_invalid_pave_id_returns_usage_error_without_traceback(capsys):
    assert cli.main(['body-repair', 'pave-reports', '../escape']) == 2
    assert 'Traceback' not in capsys.readouterr().err
