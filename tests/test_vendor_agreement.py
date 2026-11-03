import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from nova_cli_public import cli, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService


class Api:
    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.value


def test_cli_and_stdio_return_personal_signature_handoff(monkeypatch):
    value = {'required': True, 'version_label': '2026-10',
             'review_url': 'https://app.example.test/?vendor-agreement=1'}
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['vendor-agreement', 'status'])
    assert parsed.handler(parsed) == value

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {item.name: item for item in (await sdk.list_tools()).tools}
            assert tools['get_vendor_agreement_status'].annotations.readOnlyHint is True
            response = await sdk.call_tool('get_vendor_agreement_status', {})
            assert response.structuredContent == value
    asyncio.run(check())
    assert api.calls == [('GET', '/terms/contract/vendor/status', {})] * 2
    capability = manifest(cli.build_parser(), 'vendor-agreement status')['commands'][0]
    assert capability['required_operation'] == 'vendor_agreement.status.get.v1'


@pytest.mark.parametrize('value', [{}, {'required': 'false', 'version_label': None, 'review_url': None}])
def test_invalid_status_never_looks_accepted(value):
    with pytest.raises(ApiError):
        CustomerReadService(Api(value)).run('get_vendor_agreement_status', {})
