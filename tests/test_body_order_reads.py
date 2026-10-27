import asyncio

import pytest
from mcp import types
from pydantic import ValidationError

from nova_cli_public import cli, delegated
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.read_routes import admitted_read
from nova_cli_public.reads import CustomerReadService

ROWS = [
    {'id': 'BRR-1', 'status': 'in_shop', 'vehicle_id': 'VAN-1', 'url_token': 'order_token'},
    {'access_class': 'active_audience_quote_safe', 'request_token': 'audience_token',
     'request_status': 'quoted', 'vehicle': {'make': 'Ford'}},
    {'access_class': 'losing_bidder_sanitized', 'request_token': 'losing_token',
     'outcome': 'not_selected', 'own_quote': {'status': 'declined'}},
]


class Client:
    def __init__(self, response):
        self.response, self.calls = response, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.response


def test_cli_and_registry_forward_only_safe_body_filters_and_preserve_list_object():
    value = {'items': ROWS, 'total': 3}
    direct, local = Client(value), Client(value)
    args = cli.build_parser().parse_args(['body-repair', 'list', '--status', 'quoted', '--stage', 'open', '--limit', '3', '--offset', '2', '--vehicle-id', 'VAN-1'])
    args._client = direct
    assert args.handler(args) == value
    assert CustomerReadService(local).run('list_body_repair_requests', {
        'status': 'quoted', 'stage': 'open', 'limit': 3, 'offset': 2, 'vehicle_id': 'VAN-1'}) == value
    assert direct.calls == local.calls == [('GET', '/body-repair/requests', {'query': {
        'status': 'quoted', 'stage': 'open', 'limit': 3, 'offset': 2, 'vehicle_id': 'VAN-1'}})]


@pytest.mark.parametrize('row', ROWS)
def test_list_to_detail_preserves_each_role_projection_and_token(row):
    client = Client({'items': [row], 'total': 1})
    service = CustomerReadService(client)
    listing = service.run('list_body_repair_requests', {})
    reference = listing['items'][0].get('request_token', row.get('id'))
    client.response = row
    assert service.run('get_body_repair_request', {'request_ref': reference}) == row
    args = cli.build_parser().parse_args(['body-repair', 'get', reference])
    args._client = client
    assert args.handler(args) == row
    assert client.calls[-1] == ('GET', '/body-repair/requests/' + reference, {})


@pytest.mark.parametrize('arguments', [
    {'limit': 0}, {'limit': 201}, {'limit': True}, {'offset': -1}, {'stage': 'closed'},
    {'scope': 'all'}, {'status': 'invented'}, {'vehicle_id': '../escape'},
])
def test_body_filters_fail_before_transport(arguments):
    client = Client({})
    with pytest.raises(ValidationError):
        CustomerReadService(client).run('list_body_repair_requests', arguments)
    assert client.calls == []


@pytest.mark.parametrize('reference', ['../escape', 'x?scope=all', 'x/y', 'x' * 65, 'https://evil.test'])
def test_detail_reference_fails_in_cli_and_tool_before_transport(reference):
    client = Client({})
    args = cli.build_parser().parse_args(['body-repair', 'get', reference])
    args._client = client
    with pytest.raises(ValidationError):
        args.handler(args)
    with pytest.raises(ValidationError):
        CustomerReadService(client).run('get_body_repair_request', {'request_ref': reference})
    assert client.calls == []


@pytest.mark.parametrize('value', [[], {'items': [], 'total': True}, {'items': [], 'total': -1}, {'items': ['bad'], 'total': 1}])
def test_body_list_rejects_invalid_envelope(value):
    with pytest.raises(ApiError):
        CustomerReadService(Client(value)).run('list_body_repair_requests', {})


def test_body_sdk_execution_annotations_consent_and_exact_routes():
    async def check():
        server = create_server(CustomerReadService(Client({'items': [], 'total': 0})))
        tools = await server.request_handlers[types.ListToolsRequest](types.ListToolsRequest())
        for name in ['list_body_repair_requests', 'get_body_repair_request']:
            tool = next(t for t in tools.root.tools if t.name == name)
            assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
        result = await server.request_handlers[types.CallToolRequest](types.CallToolRequest(
            method='tools/call', params=types.CallToolRequestParams(name='list_body_repair_requests', arguments={})))
        assert result.root.structuredContent == {'items': [], 'total': 0}
    asyncio.run(check())
    for command, operation in [('body-repair list', 'body_repair.requests.list.v1'),
                               ('body-repair get', 'body_repair.requests.get.v1')]:
        entry = manifest(cli.build_parser(), command)['commands'][0]
        assert entry['required_operation'] == operation
        assert operation not in delegated.DEFAULT_OPERATIONS.split()
    assert admitted_read('/body-repair/requests/audience_token')
    assert not admitted_read('/body-repair/requests/audience_token/scope/edit')


@pytest.mark.parametrize('flags', [['--limit', '201'], ['--offset', '-1'], ['--vehicle-id', '../escape']])
def test_cli_invalid_body_filters_return_usage_error_before_connection(flags, capsys):
    assert cli.main(['body-repair', 'list', *flags]) == 2
    assert 'Traceback' not in capsys.readouterr().err


def test_body_detail_does_not_expand_pave_request_reference_schema():
    with pytest.raises(ValidationError):
        CustomerReadService(Client([])).run('list_body_repair_pave_reports', {'req_id': 'audience_token'})
    with pytest.raises(ApiError):
        CustomerReadService(Client([])).run('get_body_repair_request', {'request_ref': 'audience_token'})


def test_cli_dash_leading_body_token_after_delimiter_is_one_literal_get():
    token = '-opaque_body_token'
    response = {'access_class': 'losing_bidder_sanitized', 'request_token': token}
    client = Client(response)
    args = cli.build_parser().parse_args(['body-repair', 'get', '--json', '--', token])
    args._client = client
    assert args.handler(args) == response
    assert client.calls == [('GET', '/body-repair/requests/' + token, {})]
