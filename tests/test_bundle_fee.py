import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import bundle_fee, cli, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

VALUE = {'ref': 'B-TEST', 'revision': 3, 'fee_waived': True}


def test_cli_and_mcp_waive_one_bundle_with_a_reason(monkeypatch):
    api = SimpleNamespace(request=Mock(return_value=VALUE))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['bundle-fee', 'waive', 'B-TEST', '--reason', '  Approved waiver  ', '--revision', '2'])
    assert args.handler(args) == VALUE

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools[bundle_fee.READ].annotations.readOnlyHint
            assert not tools[bundle_fee.WRITE].annotations.readOnlyHint
            result = await sdk.call_tool(bundle_fee.WRITE, {'ref': 'B-TEST', 'reason': 'Approved waiver', 'revision': 2})
            assert not result.isError and result.structuredContent == VALUE
    asyncio.run(check())
    assert api.request.call_args_list == [(( 'POST', '/defect-bundle-offers/staff/B-TEST/waive-fee'),
        {'json_body': {'reason': 'Approved waiver', 'revision': 2}, 'retry_auth': False})] * 2


@pytest.mark.parametrize('values', [{'ref': '../bad', 'reason': 'Approved'}, {'ref': 'B-TEST', 'reason': ' '},
    {'ref': 'B-TEST', 'reason': 'Approved', 'revision': 0}, {'ref': 'B-TEST', 'reason': 'Approved', 'amount': 10}])
def test_invalid_waiver_does_not_reach_api(values):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        bundle_fee.execute(api, bundle_fee.WRITE, values)
    api.request.assert_not_called()


@pytest.mark.parametrize('value', [None, {**VALUE, 'fee_waived': False}, {**VALUE, 'ref': 'B-OTHER'}])
def test_unconfirmed_waiver_is_not_retried(value):
    api = SimpleNamespace(request=Mock(return_value=value))
    with pytest.raises(ApiError) as error:
        bundle_fee.execute(api, bundle_fee.WRITE, {'ref': 'B-TEST', 'reason': 'Approved'})
    assert error.value.code == 'outcome_unknown'
    assert api.request.call_count == 1


def test_discovery_and_route_admission_name_required_grant():
    from nova_cli_public.read_routes import admitted_read
    from nova_cli_public.write_routes import admitted_write
    entry = manifest(cli.build_parser(), 'bundle-fee waive')['commands'][0]
    assert entry['required_operation'] == 'capacity.fee.waive.v1'
    assert entry['required_scope'] == 'nova:read nova:write'
    assert admitted_read('/defect-bundle-offers/staff/B-TEST')
    assert admitted_write('POST', '/defect-bundle-offers/staff/B-TEST/waive-fee')


def test_remove_bundle_cli_and_mcp_use_one_fixed_write(monkeypatch):
    value = {'ref': 'B-TEST', 'status': 'discarded'}
    api = SimpleNamespace(request=Mock(return_value=value))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['bundle', 'remove', 'B-TEST'])
    assert args.handler(args) == value
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            result = await sdk.call_tool('remove_bundle', {'ref': 'B-TEST'})
            assert not result.isError and result.structuredContent == value
    asyncio.run(check())
    assert api.request.call_count == 2
    assert api.request.call_args_list[0] == api.request.call_args_list[1]
    api.request.assert_called_with('POST', '/defect-bundle-offers/staff/B-TEST/discard', json_body={}, retry_auth=False)
    entry = manifest(cli.build_parser(), 'bundle remove')['commands'][0]
    assert entry['required_operation'] == 'capacity.offers.remove.v1'
    from nova_cli_public.write_routes import admitted_write
    assert admitted_write('POST', '/defect-bundle-offers/staff/B-TEST/discard')


@pytest.mark.parametrize('value', [None, {'ref': 'B-OTHER', 'status': 'discarded'}, {'ref': 'B-TEST', 'status': 'awarded'}])
def test_unconfirmed_removal_is_unknown_and_not_retried(value):
    from nova_cli_public import bundle_fee
    from nova_cli_public.errors import ApiError
    api = SimpleNamespace(request=Mock(return_value=value))
    with pytest.raises(ApiError) as error:
        bundle_fee.execute(api, bundle_fee.REMOVE, {'ref': 'B-TEST'})
    assert error.value.code == 'outcome_unknown' and api.request.call_count == 1
