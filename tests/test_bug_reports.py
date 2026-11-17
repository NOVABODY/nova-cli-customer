import inspect
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from nova_cli_public.bug_reports import Report, execute
from nova_cli_public.client import ApiClient
from nova_cli_public.errors import ApiError

REPORT_ID = '123e4567-e89b-12d3-a456-426614174000'
ARGS = {'note': 'The report button fails.', 'report_id': REPORT_ID, 'photos': ['data:image/png;base64,aGVsbG8=']}
RECEIPT = {'ok': True, 'duplicate': False}


class Api:
    profile = SimpleNamespace(auth='service')

    def __init__(self, value=RECEIPT):
        self.value, self.calls = value, []

    def request(self, method, path, **kwargs):
        inspect.signature(ApiClient.request).bind(self, method, path, **kwargs)
        self.calls.append((method, path, kwargs))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


@pytest.mark.parametrize('changes', [
    {'note': '  '}, {'report_id': 'bad-id'}, {'photos': ['x'] * 4},
    {'photos': ['x' * 3_000_001] * 2}, {'photos': ['x' * 4_000_001]}, {'reporter': 'Forged'},
])
def test_invalid_report_does_not_send(changes):
    client = Api()
    with pytest.raises(ValidationError):
        execute(client, {**ARGS, **changes})
    assert not client.calls


@pytest.mark.parametrize('value', [{}, {'ok': False, 'duplicate': False}, ApiError('timeout'), ApiError('down', status=503)])
def test_uncertain_report_is_never_replayed(value):
    client = Api(value)
    with pytest.raises(ApiError) as exc:
        execute(client, ARGS)
    assert exc.value.code == 'outcome_unknown'
    assert len(client.calls) == 1
    assert client.calls[0][2]['retry_auth'] is False


def test_report_keeps_screenshots_context_and_retry_id():
    client = Api()
    assert execute(client, {**ARGS, 'path': '/inspections'}) == RECEIPT
    assert client.calls == [('POST', '/bug-reports', {'json_body':
        Report.model_validate({**ARGS, 'path': '/inspections'}).model_dump(exclude_none=True), 'retry_auth': False})]


def test_customer_cli_mcp_and_capabilities_use_one_contract(monkeypatch):
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public import cli, legacy_reads
    from nova_cli_public.capabilities import manifest
    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService
    from nova_cli_public.write_routes import admitted_write

    api = Api()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    parsed = cli.build_parser().parse_args(['bug-report', 'submit', '--note', ARGS['note'], '--report-id', REPORT_ID, '--photo', ARGS['photos'][0]])
    assert parsed.handler(parsed) == RECEIPT
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert not tools['report_bug'].annotations.readOnlyHint
            result = await sdk.call_tool('report_bug', ARGS)
            assert not result.isError and result.structuredContent == RECEIPT
    asyncio.run(check())
    assert api.calls[0][2]['json_body']['display_mode'] == 'cli'
    assert api.calls[1][2]['json_body']['display_mode'] == 'mcp'
    assert api.calls[0][2]['json_body']['photos'] == api.calls[1][2]['json_body']['photos']
    capability = manifest(cli.build_parser(), 'bug-report submit')['commands'][0]
    assert capability['required_operation'] == 'bug_reports.create.v1'
    assert admitted_write('POST', '/bug-reports')
    assert capability['required_scope'] == 'nova:read nova:write'


def test_cli_photo_files_are_encoded_and_bounded(tmp_path):
    import base64

    from nova_cli_public.bug_reports import cli_arguments
    photo = tmp_path / 'screen.png'
    photo.write_bytes(b'synthetic screenshot')
    args = SimpleNamespace(**{**ARGS, 'photos': []}, photo_file=[str(photo)])
    values = cli_arguments(args)
    assert values['photos'] == ['data:image/png;base64,' + base64.b64encode(photo.read_bytes()).decode()]
    photo.write_bytes(b'x' * 3_000_001)
    from nova_cli_public.errors import UsageError
    with pytest.raises(UsageError):
        cli_arguments(args)


def test_cli_invalid_note_returns_a_usage_error():
    from nova_cli_public.bug_reports import cli_arguments
    from nova_cli_public.errors import UsageError
    with pytest.raises(UsageError):
        cli_arguments(SimpleNamespace(note=' ', report_id=REPORT_ID))
