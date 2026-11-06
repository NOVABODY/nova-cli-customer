import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import bundle_address, cli, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

VALUE = {'delivery_address': '2 New Road', 'van_count': 3}


class Api:
    profile = SimpleNamespace(auth='service')

    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {**VALUE, 'can_edit': True, 'can_save_profile': True} if method == 'GET' else VALUE


@pytest.mark.parametrize('profile', [False, True])
def test_cli_and_mcp_share_explicit_profile_choice(monkeypatch, profile):
    api = Api()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['bundle-address', 'set', 'B-TEST', '--delivery-address', '  2 New Road  ', *(['--save-profile'] if profile else [])])
    assert args.handler(args) == VALUE

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools[bundle_address.READ].annotations.readOnlyHint
            assert not tools[bundle_address.WRITE].annotations.readOnlyHint
            read = await sdk.call_tool(bundle_address.READ, {'ref': 'B-TEST'})
            assert read.structuredContent['van_count'] == 3
            result = await sdk.call_tool(bundle_address.WRITE, {'ref': 'B-TEST', 'delivery_address': '2 New Road', 'save_profile': profile})
            assert not result.isError and result.structuredContent == VALUE
    asyncio.run(check())
    assert [call for call in api.calls if call[0] == 'POST'] == [('POST', '/bundle-offers/B-TEST/dropoff-address',
        {'json_body': {'delivery_address': '2 New Road', 'save_profile': profile}, 'retry_auth': False})] * 2


@pytest.mark.parametrize('values', [{'ref': '../bad', 'delivery_address': '2 New Road'},
    {'ref': 'B-TEST', 'delivery_address': '   '}, {'ref': 'B-TEST', 'delivery_address': 'x' * 501}])
def test_invalid_inputs_never_reach_transport(values):
    api = Api()
    with pytest.raises(ValidationError):
        bundle_address.execute(api, bundle_address.WRITE, values)
    assert not api.calls


@pytest.mark.parametrize('response', [None, {'delivery_address': 'wrong', 'van_count': 3}])
def test_unconfirmed_write_is_not_retried(response):
    client = SimpleNamespace(request=Mock(return_value=response))
    with pytest.raises(ApiError) as error:
        bundle_address.execute(client, bundle_address.WRITE, {'ref': 'B-TEST', 'delivery_address': '2 New Road'})
    assert error.value.code == 'outcome_unknown'
    assert client.request.call_count == 1


def test_discovery_names_exact_grant_and_route():
    from nova_cli_public.read_routes import admitted_read
    from nova_cli_public.write_routes import admitted_write
    entry = manifest(cli.build_parser(), 'bundle-address set')['commands'][0]
    assert entry['required_operation'] == 'capacity.dropoff_address.update.v1'
    assert entry['required_scope'] == 'nova:read nova:write'
    assert admitted_read('/bundle-offers/B-TEST/dropoff-address')
    assert admitted_write('POST', '/bundle-offers/B-TEST/dropoff-address')
