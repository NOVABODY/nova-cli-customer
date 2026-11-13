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

# New offers and saved sliding offers must pass through CLI and local MCP unchanged.
for pricing in (
    {'rule': 'value_allocations_v4', 'threshold': 1000, 'high': 150, 'low': 75, 'line_base_price': 5},
    {'rule': 'sliding_allocations_v3', 'first_limit': 1000, 'second_limit': 2000,
     'first_percent': 8, 'second_percent': 6, 'tail_percent': 4},
):
    CASES.append(('report', 'get_bundle_offer_report', {'ref': 'B-1'}, '/bundle-offers/B-1/report',
        {'ref': 'B-1', 'status': 'awarded', 'report': {'pricing': pricing, 'units': []}}))
    CASES.append(('vans', 'list_bought_bundle_vans', {'ref': 'B-1'}, '/bundle-offers/B-1/vans',
        {'vans': [{'unit': 1, 'state': 'lapsed', 'workflow': WORKFLOW, 'pricing': pricing}]}))


SLIDING = {'rule': 'sliding_allocations_v3', 'first_limit': 1000, 'second_limit': 2000,
           'first_percent': 8, 'second_percent': 6, 'tail_percent': 4,
           'payment_rule': 'approved_readiness_v1'}
SLIDING_REPORT = {'ref': 'B-1', 'status': 'open', 'report': {'pricing': SLIDING,
    'units': [{'unit': 1, 'vin': '1FTBW2CM0NKA99999', 'asking_price': 80.03}]}}
CASES.append(('report', 'get_bundle_offer_report', {'ref': 'B-1'}, '/bundle-offers/B-1/report', SLIDING_REPORT))

TRANSPORT = {**SLIDING, 'rule': 'sliding_transport_v5', 'first_percent': 5,
             'second_percent': 4, 'tail_percent': 3, 'transport_fee': 50}
TRANSPORT_REPORT = {**SLIDING_REPORT, 'report': {'pricing': TRANSPORT,
    'units': [{'unit': 1, 'asking_price': 100.02, 'lines': [{'allocated_price': 50.02}]}]}}
CASES.append(('report', 'get_bundle_offer_report', {'ref': 'B-1'}, '/bundle-offers/B-1/report', TRANSPORT_REPORT))

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


def test_incomplete_sliding_terms_are_rejected():
    from nova_cli_public.bundle_workflow import Pricing

    with pytest.raises(ValidationError):
        Pricing.model_validate({key: value for key, value in SLIDING.items() if key != 'tail_percent'})


@pytest.mark.parametrize('missing', ['first_percent', 'transport_fee'])
def test_incomplete_transport_terms_are_rejected(missing):
    from pydantic import ValidationError

    from nova_cli_public.bundle_workflow import Pricing

    with pytest.raises(ValidationError):
        Pricing.model_validate({key: value for key, value in TRANSPORT.items() if key != missing})


# Frozen sliding_transport_base_v6: sliding repair fee + per-defect base + separate transport.
BASE_V6 = {**TRANSPORT, 'rule': 'sliding_transport_base_v6', 'line_base_price': 5}
V6_UNITS = [{'unit': 1, 'asking_price': 135, 'lines': [{'allocated_price': 28.33}, {'allocated_price': 28.33}, {'allocated_price': 28.34}]}]
V6_EXAMPLE = {'ref': 'B-1', 'status': 'open', 'report': {'pricing': BASE_V6, 'units': V6_UNITS}}
CASES.append(('report', 'get_bundle_offer_report', {'ref': 'B-1'}, '/bundle-offers/B-1/report', V6_EXAMPLE))
CASES.append(('vans', 'list_bought_bundle_vans', {'ref': 'B-1'}, '/bundle-offers/B-1/vans',
    {'vans': [{'unit': 1, 'state': 'lapsed', 'workflow': WORKFLOW, 'accepted_price_cents': 13500, 'pricing': BASE_V6}]}))
# Custom, zero-base and waived terms, and fractional-cent allocations, pass through exactly.
for extra, units in (
    ({'line_base_price': 0}, [{'unit': 1, 'asking_price': 120, 'lines': [{'allocated_price': 70}]}]),
    ({'line_base_price': 12.5, 'transport_fee': 0, 'first_percent': 6}, [{'unit': 1, 'asking_price': 37.55, 'lines': [{'allocated_price': 12.52}, {'allocated_price': 25.03}]}]),
    ({'fee_waived': True}, [{'unit': 1, 'asking_price': 0, 'lines': [{'allocated_price': 0}]}]),
):
    CASES.append(('report', 'get_bundle_offer_report', {'ref': 'B-1'}, '/bundle-offers/B-1/report',
        {'ref': 'B-1', 'status': 'open', 'report': {'pricing': {**BASE_V6, **extra}, 'units': units}}))
# Older rules without the new fields keep validating.
for old in (SLIDING, TRANSPORT, {'rule': 'legacy_tiers', 'threshold': 1000, 'high': 150, 'low': 75}):
    CASES.append(('report', 'get_bundle_offer_report', {'ref': 'B-1'}, '/bundle-offers/B-1/report',
        {'ref': 'B-1', 'status': 'open', 'report': {'pricing': old, 'units': []}}))


@pytest.mark.parametrize('missing', ['first_percent', 'transport_fee', 'line_base_price'])
def test_incomplete_base_terms_are_rejected(missing):
    from nova_cli_public.bundle_workflow import Pricing

    with pytest.raises(ValidationError):
        Pricing.model_validate({key: value for key, value in BASE_V6.items() if key != missing})


def test_base_terms_keep_cents_and_extra_fields():
    from nova_cli_public.bundle_workflow import Pricing

    terms = Pricing.model_validate({**BASE_V6, 'line_base_price': 7.25, 'fee_waived': False})
    assert terms.line_base_price == 7.25 and terms.model_dump()['payment_rule'] == 'approved_readiness_v1'
    with pytest.raises(ValidationError):
        Pricing.model_validate({**BASE_V6, 'line_base_price': -1})


def test_unknown_rule_is_rejected():
    from nova_cli_public.bundle_workflow import Pricing

    with pytest.raises(ValidationError):
        Pricing.model_validate({**BASE_V6, 'rule': 'sliding_transport_base_v7'})
