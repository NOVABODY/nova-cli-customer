import asyncio
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads, vendor_cmr_auto_accept
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.read_routes import admitted_read
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.write_routes import admitted_write


class Api:
    profile = SimpleNamespace(auth='service-account')

    def __init__(self, enabled):
        self.enabled, self.calls = enabled, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {'enabled': self.enabled, 'opted_in': self.enabled}


@pytest.mark.parametrize('enabled', [None, False, True])
def test_cli_and_mcp_use_one_shared_value_once(monkeypatch, enabled):
    api = Api(False if enabled is None else enabled)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    argv = ['vendor-cmr-auto-accept', 'get' if enabled is None else 'set', 'V-7']
    if enabled is not None:
        argv += ['--enabled' if enabled else '--no-enabled']
    parsed = cli.build_parser().parse_args(argv)
    assert parsed.handler(parsed)['enabled'] is api.enabled
    name = vendor_cmr_auto_accept.READ if enabled is None else vendor_cmr_auto_accept.WRITE
    arguments = {'vendor_id': 'V-7', **({} if enabled is None else {'enabled': enabled})}

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {item.name: item for item in (await sdk.list_tools()).tools}
            assert tools[name].annotations.readOnlyHint is (enabled is None)
            result = await sdk.call_tool(name, arguments)
            assert not result.isError and result.structuredContent['enabled'] is api.enabled
    asyncio.run(check())
    assert api.calls == [('GET' if enabled is None else 'PATCH',
        '/organizations/V-7/cmr-auto-accept', {} if enabled is None else
        {'json_body': {'enabled': enabled}})] * 2
    path = '/organizations/V-7/cmr-auto-accept'
    assert admitted_read(path) if enabled is None else admitted_write('PATCH', path)
    capability = manifest(cli.build_parser(), ' '.join(argv[:2]))['commands'][0]
    assert capability['required_operation'] == 'vendor.cmr_auto_accept.' + ('get' if enabled is None else 'update') + '.v1' 


@pytest.mark.parametrize('arguments', [{'vendor_id': '../7'}, {'vendor_id': 'V-0'},
    {'vendor_id': '7'}, {'vendor_id': '7', 'enabled': 'false'},
    {'vendor_id': '7', 'enabled': True, 'opted_in': False}])
def test_invalid_update_never_reaches_transport(arguments):
    api = Api(True)
    with pytest.raises(ValidationError):
        vendor_cmr_auto_accept.execute(api, vendor_cmr_auto_accept.WRITE, arguments)
    assert api.calls == []


def test_unconfirmed_update_is_not_reported_as_success_or_retried():
    api = Api(False)
    with pytest.raises(ApiError) as error:
        vendor_cmr_auto_accept.execute(api, vendor_cmr_auto_accept.WRITE, {'vendor_id': '7', 'enabled': True})
    assert error.value.code == 'outcome_unknown' and len(api.calls) == 1
