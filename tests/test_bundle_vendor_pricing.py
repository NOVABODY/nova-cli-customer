import asyncio
import json
from unittest.mock import create_autospec

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import bundle_vendor_pricing as subject
from nova_cli_public import cli, legacy_reads
from nova_cli_public.client import ApiClient
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

PRICING = {'first_percent': 20, 'second_percent': 12, 'tail_percent': 8, 'transport_fee': 123.45}
VENDOR = {'id': 'V-001', 'name': 'Synthetic shop', 'pricing': PRICING, 'effective_pricing': PRICING}
BUNDLE = {'ref': 'DFS-B-2026-0001', 'revision': 1, 'status': 'draft', 'total_price_cents': 15000}
CHOICES = {'repair_groups': ['AMR'], 'station_codes': ['CAP1'], 'van_count': 1, 'pricing_vendor_id': 'V-001'}
PROFILE = {'id': 1, 'name': 'Synthetic profile', 'pricing_vendor_id': 1}
CASES = [
    ('list_bundle_pricing_vendors', {}, 'GET', '/pricing-vendors', {'rows': [VENDOR]}),
    ('set_vendor_bundle_pricing', {'organization_id': 'V-001', 'pricing': PRICING}, 'PUT', '/pricing-vendors/V-001', VENDOR),
    ('set_vendor_bundle_pricing', {'organization_id': 'V-001', 'pricing': None}, 'PUT', '/pricing-vendors/V-001', {**VENDOR, 'pricing': None}),
    ('create_admin_bundle', {'station_code': 'CAP1', 'vehicle_ids': ['VAN-001'], 'pricing_vendor_id': 'V-001'}, 'POST', '', BUNDLE),
    ('list_bundle_profiles', {}, 'GET', '/profiles', {'rows': [PROFILE]}),
    ('save_bundle_profile', {**CHOICES, 'name': 'Synthetic profile'}, 'POST', '/profiles', PROFILE),
    ('propose_bundle_offers', CHOICES, 'POST', '/propose', {'rows': [BUNDLE]}),
    ('run_bundle_profile', {'profile_id': 1}, 'POST', '/profiles/1/run', {'rows': [BUNDLE]}),
]


@pytest.mark.parametrize('name,arguments,method,suffix,value', CASES)
def test_cli_and_local_mcp_use_the_real_transport_signature(monkeypatch, name, arguments, method, suffix, value):
    api = create_autospec(ApiClient, instance=True)
    api.request.return_value = value
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    entry = next(entry for entry in subject.COMMANDS if entry['tool'] == name)
    tokens = entry['command'].split() + (['--request', json.dumps(arguments)] if arguments else [])
    parsed = cli.build_parser().parse_args(tokens)
    assert parsed.handler(parsed) == value
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools[name].annotations.readOnlyHint is (method == 'GET')
            result = await sdk.call_tool(name, arguments)
            assert not result.isError and result.structuredContent == value
    asyncio.run(check())
    expected = subject.wire(name, subject.MODELS[name].model_validate(arguments))[2]
    assert api.request.call_count == 2
    assert api.request.call_args.args == (method, subject.BASE + suffix)
    assert api.request.call_args.kwargs == ({} if method == 'GET' else {'json_body': expected, 'retry_auth': False})


@pytest.mark.parametrize('pricing', [None, {'first_percent': 101, 'second_percent': 1, 'tail_percent': 1, 'transport_fee': 2}, {**PRICING, 'transport_fee': 1.234}])
def test_invalid_defaults_do_not_reach_transport(pricing):
    api = create_autospec(ApiClient, instance=True)
    with pytest.raises(ValidationError):
        subject.execute(api, 'set_vendor_bundle_pricing', {'organization_id': '../bad' if pricing is None else 'V-001', 'pricing': pricing})
    api.request.assert_not_called()


def test_uncertain_write_is_never_replayed():
    api = create_autospec(ApiClient, instance=True)
    api.request.side_effect = ApiError('temporary', status=503)
    with pytest.raises(ApiError) as error:
        subject.execute(api, 'set_vendor_bundle_pricing', {'organization_id': 'V-001', 'pricing': PRICING})
    assert error.value.code == 'outcome_unknown'
    assert api.request.call_count == 1
