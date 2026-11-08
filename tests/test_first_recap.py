"""Named confirmation tools preserve explicit opt-in and one-appointment decisions."""
import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from nova_cli_public import cli, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.mcp import create_server
from nova_cli_public.read_routes import admitted_read
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.write_routes import admitted_write

WHEN = '2026-10-28T02:00:00Z'
STATUS = {'schedule_id': 7, 'confirmation_id': 17, 'status': 'confirmed', 'responded_at': WHEN, 'responded_by_id': 8}
SETTINGS = {'enabled': False, 'recipient_roles': 'owners_and_dispatchers'}


class Api:
    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.value


@pytest.mark.parametrize('argv,tool,arguments,method,path,body,value', [
 (['inspection-recap', 'report', 'DSP-7'], 'get_first_inspection_recap_report', {'dsp_id': 'DSP-7'}, 'GET', '/first-inspection-recaps/7/report', None,
  {'dsp_id': 7, 'cutoff': WHEN, 'as_of': WHEN, 'findings': [], 'inspected': 1, 'incomplete': 0, 'defects': 0, 'critical': 0}),
 (['vendor-referral', 'list'], 'list_vendor_referrals', {}, 'GET', '/vendor-referrals', None, []),
 (['vendor-referral', 'submit', '--shop-name', 'Sample shop', '--contact-name', 'Sample contact', '--contact-email', 'sample@example.test', '--repair-types', 'tires', '--service-location', 'Sample station', '--reason', 'Fleet service', '--contact-consent'],
  'submit_vendor_referral', {'shop_name': 'Sample shop', 'contact_name': 'Sample contact', 'contact_email': 'sample@example.test', 'repair_types': ['tires'], 'service_location': 'Sample station', 'reason': 'Fleet service', 'contact_consent': True}, 'POST', '/vendor-referrals',
  {'shop_name': 'Sample shop', 'contact_name': 'Sample contact', 'contact_email': 'sample@example.test', 'repair_types': ['tires'], 'service_location': 'Sample station', 'reason': 'Fleet service', 'language': 'en', 'contact_consent': True},
  {'reference': 'sample-referral', 'shop_name': 'Sample shop', 'status': 'submitted'}),
])
def test_cli_and_mcp_preserve_explicit_fields(monkeypatch, argv, tool, arguments, method, path, body, value):
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(argv)
    assert parsed.handler(parsed) == value
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {item.name: item for item in (await sdk.list_tools()).tools}
            assert tools[tool].annotations.readOnlyHint is (method == 'GET')
            result = await sdk.call_tool(tool, arguments)
            assert not result.isError and result.structuredContent == ({'items': value} if isinstance(value, list) else value)
    asyncio.run(check())
    assert api.calls == [(method, path,
        {'params': {'limit': 50, 'offset': 0, 'state': ''}} if tool == 'list_vendor_referrals' else {} if body is None else {'json_body': body})] * 2
    capability = manifest(cli.build_parser(), ' '.join(argv[:2]))['commands'][0]
    assert capability['required_scope'] == ('nova:read' if method == 'GET' else 'nova:read nova:write')
    assert capability['required_operation'] == ('first_recaps.report.v1' if 'recap' in tool else 'vendor_referrals.submit.v1' if method == 'POST' else 'vendor_referrals.list.v1')
    assert admitted_read(path) if method == 'GET' else admitted_write(method, path)


def test_no_admin_commands_or_referral_without_consent():
    from pydantic import ValidationError
    api = Api({})
    with pytest.raises(ValidationError):
        CustomerReadService(api).run('submit_vendor_referral', {'contact_consent': False})
    tools = [row['tool'] for row in __import__('nova_cli_public.first_recap', fromlist=['COMMANDS']).COMMANDS]
    assert 'generate_first_inspection_recap' not in tools
    assert not admitted_write('POST', '/first-inspection-recaps/7/send')
    assert not admitted_write('PATCH', '/vendor-referrals/sample')
    assert api.calls == []
