import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from nova_cli_public import cli, legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.read_routes import admitted_read
from nova_cli_public.reads import CustomerReadService


class Api:
    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.value


@pytest.mark.parametrize('command,tool,args,value,path', [
    (['skills', 'list'], 'list_skills', {}, {'required_skill': 'nova-fora-basics', 'items': []}, '/agent-skills'),
    (['skills', 'get', '--name', 'nova-shop-service-writer', '--file', 'references/pricing.md'],
     'get_skill', {'name': 'nova-shop-service-writer', 'file': 'references/pricing.md'},
     {'name': 'nova-shop-service-writer', 'file': 'references/pricing.md', 'content': 'Synthetic guidance'},
     '/agent-skills/nova-shop-service-writer'),
])
def test_cli_and_stdio_discover_and_read_same_skills(monkeypatch, command, tool, args, value, path):
    api = Api(value)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda _: api)
    parsed = cli.build_parser().parse_args(command)
    assert parsed.handler(parsed) == value
    async def check():
        server = create_server(CustomerReadService(api))
        assert 'list_skills' in server.create_initialization_options().instructions
        async with create_connected_server_and_client_session(server) as sdk:
            tools = {item.name: item for item in (await sdk.list_tools()).tools}
            assert tools[tool].annotations.readOnlyHint
            response = await sdk.call_tool(tool, args)
            assert response.structuredContent == value
    asyncio.run(check())
    assert len(api.calls) == 2
    assert all(call[:2] == ('GET', path) for call in api.calls)
    assert admitted_read(path) is True


def test_skill_response_must_match_requested_file():
    with pytest.raises(ApiError):
        CustomerReadService(Api({'name': 'nova-shop-new-work', 'file': 'SKILL.md', 'content': 'Wrong skill'})).run(
            'get_skill', {'name': 'nova-fora-basics'})
