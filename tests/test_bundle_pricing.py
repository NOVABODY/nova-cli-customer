import asyncio
from unittest.mock import create_autospec

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import bundle_fee, cli, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.client import ApiClient
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

VALUES = {'first_percent': 20, 'second_percent': 12, 'tail_percent': 8, 'transport_fee': 123.45}
REQUEST = dict(ref='B-TEST', revision=2, **VALUES)
RESULT = {'ref': 'B-TEST', 'revision': 3, 'total_price_cents': 53845, 'pricing': VALUES}


def test_cli_and_local_mcp_send_one_confirmed_pricing_change(monkeypatch):
    api = create_autospec(ApiClient, instance=True)
    api.request.return_value = RESULT
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['bundle', 'pricing', 'B-TEST', '--revision', '2',
        '--first-percent', '20', '--second-percent', '12', '--tail-percent', '8', '--transport-fee', '123.45'])
    assert args.handler(args) == RESULT

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert not tools[bundle_fee.PRICING].annotations.readOnlyHint
            result = await sdk.call_tool(bundle_fee.PRICING, REQUEST)
            assert not result.isError and result.structuredContent == RESULT
    asyncio.run(check())
    assert api.request.call_args_list == [(
        ('POST', '/defect-bundle-offers/staff/B-TEST/pricing'),
        {'json_body': {**VALUES, 'revision': 2}, 'retry_auth': False})] * 2
    entry = manifest(cli.build_parser(), 'bundle pricing')['commands'][0]
    assert entry['required_operation'] == 'capacity.pricing.update.v1'
    assert entry['required_scope'] == 'nova:read nova:write'
    from nova_cli_public.write_routes import admitted_write
    assert admitted_write('POST', '/defect-bundle-offers/staff/B-TEST/pricing')


@pytest.mark.parametrize('field,value', [('first_percent', -1), ('second_percent', 101),
    ('tail_percent', 1.5), ('transport_fee', 1.234), ('transport_fee', float('nan')), ('revision', 0)])
def test_invalid_pricing_never_reaches_transport(field, value):
    api = create_autospec(ApiClient, instance=True)
    with pytest.raises(ValidationError):
        bundle_fee.execute(api, bundle_fee.PRICING, {**REQUEST, field: value})
    api.request.assert_not_called()


@pytest.mark.parametrize('value', [None, {**RESULT, 'ref': 'B-OTHER'}, {**RESULT, 'revision': 5},
    {**RESULT, 'pricing': {**VALUES, 'transport_fee': 50}}])
def test_unconfirmed_pricing_is_unknown_and_never_replayed(value):
    api = create_autospec(ApiClient, instance=True)
    api.request.return_value = value
    with pytest.raises(ApiError) as exc:
        bundle_fee.execute(api, bundle_fee.PRICING, REQUEST)
    assert exc.value.code == 'outcome_unknown'
    assert api.request.call_count == 1


def test_transport_failure_is_unknown_and_never_replayed():
    api = create_autospec(ApiClient, instance=True)
    api.request.side_effect = ApiError('Unavailable', status=503)
    with pytest.raises(ApiError) as exc:
        bundle_fee.execute(api, bundle_fee.PRICING, REQUEST)
    assert exc.value.code == 'outcome_unknown'
    assert api.request.call_count == 1
