"""Named reads preserve bounded summaries and the API's lapsed masking."""
import asyncio
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

SUMMARY = {'action_required': 1, 'awaiting_nova': 0, 'completed': 0, 'next_deadline': None, 'timezone': 'UTC'}
PRICING = {'rule': 'allocated_declines_v2', 'threshold': 1000, 'high': 150, 'low': 75}
WORKFLOW = {'step': 6, 'action': 'ended', 'owner': 'done', 'group': 'completed', 'deadline': None}
CASES = [('list', 'list_bundle_offers', {}, '/bundle-offers', {'rows': [{'ref': 'B-1', 'status': 'awarded', 'total_price_cents': 15000, 'workflow_summary': SUMMARY}]}), ('report', 'get_bundle_offer_report', {'ref': 'B-1'}, '/bundle-offers/B-1/report', {'ref': 'B-1', 'status': 'awarded', 'report': {'pricing': PRICING, 'units': []}}), ('vans', 'list_bought_bundle_vans', {'ref': 'B-1'}, '/bundle-offers/B-1/vans', {'vans': [{'unit': 1, 'state': 'lapsed', 'workflow': WORKFLOW}]})]

class Api:
    profile = SimpleNamespace(auth='service')

    def __init__(self, value):
        self.value, self.calls = (value, [])

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.value

@pytest.mark.parametrize('action,name,arguments,path,value', CASES)
def test_cli_and_mcp_discover_the_same_read_only_projection(monkeypatch, action, name, arguments, path, value):
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['bundle-workflow', action, *arguments.values()])
    assert parsed.handler(parsed) == value

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {item.name: item for item in (await sdk.list_tools()).tools}
            assert tools[name].annotations.readOnlyHint and tools[name].annotations.idempotentHint
            assert not tools[name].annotations.destructiveHint
            result = await sdk.call_tool(name, arguments)
            assert not result.isError and result.structuredContent == value
    asyncio.run(check())
    assert api.calls == [('GET', path, {})] * 2
    command = manifest(cli.build_parser(), 'bundle-workflow ' + action)['commands'][0]
    assert command['required_operation'] == {'list': 'capacity.offers.list.v1', 'report': 'capacity.offers.report.v1', 'vans': 'capacity.vans.list.v1'}[action]
    assert command['effects'] == ['remote_read']

@pytest.mark.parametrize('arguments', [{'ref': '../other'}, {'ref': 'B-1?private=1'}, {'ref': 'B-1', 'include_private': True}])
def test_invalid_references_do_not_reach_transport(arguments):
    from nova_cli_public.bundle_workflow import execute
    api = Api({})
    with pytest.raises(ValidationError):
        execute(api, 'list_bought_bundle_vans', arguments)
    assert not api.calls

@pytest.mark.parametrize('value', [None, {}, {'vans': [{'unit': 1, 'state': 'lapsed'}]}])
def test_malformed_response_is_not_presented_as_a_valid_workflow(value):
    from nova_cli_public.bundle_workflow import execute
    from nova_cli_public.errors import ApiError
    with pytest.raises(ApiError):
        execute(Api(value), 'list_bought_bundle_vans', {'ref': 'B-1'})
