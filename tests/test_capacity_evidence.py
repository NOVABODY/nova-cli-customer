import asyncio
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import capacity_evidence as evidence
from nova_cli_public import cli, legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService


class Api:
    profile = SimpleNamespace(auth='service')

    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {'id': 8, 'review_state': kwargs.get('json_body', {}).get('decision', 'unreviewed')}


@pytest.mark.parametrize('decision,note', [('accepted', ''), ('rejected', 'Send a clear copy.')])
def test_cli_and_local_mcp_review_once_with_required_note(monkeypatch, decision, note):
    api = Api()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['capacity-evidence', 'review', '--evidence-id', '8', '--decision', decision, '--note', note])
    assert args.handler(args)['review_state'] == decision

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            result = await sdk.call_tool('review_capacity_evidence', {'evidence_id': 8, 'decision': decision, 'note': note})
            assert not result.isError and result.structuredContent['review_state'] == decision
    asyncio.run(check())
    assert api.calls == [('POST', evidence.BASE + '/8/review', {'json_body': {'decision': decision, 'note': note}, 'retry_auth': False})] * 2


def test_blank_rejection_never_reaches_transport():
    api = Api()
    with pytest.raises(ValidationError):
        evidence.execute(api, 'review_capacity_evidence', {'evidence_id': 8, 'decision': 'rejected'})
    assert not api.calls


def test_upload_sends_one_bounded_file_without_automatic_retry():
    api = Api()
    evidence.execute(api, 'upload_capacity_evidence', {'ref': 'B-1', 'unit': 1, 'kind': 'decline',
        'lines': [2], 'content_type': 'image/png', 'content_base64': 'cHJvb2Y='})
    assert len(api.calls) == 2
    assert api.calls[1][:2] == ('GET', '/bundle-offers/B-1/vans')
    method, path, options = api.calls[0]
    assert (method, path) == ('POST', '/bundle-offers/B-1/vans/1/evidence-content')
    assert options['json_body']['lines'] == [2] and options['json_body']['content_base64'] == 'cHJvb2Y='
    assert options['retry_auth'] is False


def test_unconfirmed_review_is_unknown_without_retry():
    class Unconfirmed(Api):
        def request(self, *args, **kwargs):
            super().request(*args, **kwargs)
            return {'id': 9, 'review_state': 'accepted'}
    api = Unconfirmed()
    with pytest.raises(ApiError) as failure:
        evidence.execute(api, 'review_capacity_evidence', {'evidence_id': 8, 'decision': 'accepted'})
    assert failure.value.code == 'outcome_unknown' and len(api.calls) == 1


def transport_client(value):
    """Exercise the real transport signature and route admission without network IO."""
    from nova_cli_public.client import ApiClient
    api = ApiClient.__new__(ApiClient)
    api.profile = SimpleNamespace(auth='service', api='https://nova.example/api')
    api.access_token = 'synthetic'
    api.access_token_expires_at = None
    calls = []

    def send(method, path, **options):
        calls.append((method, path, options))
        body = {'vans': []} if path.endswith('/vans') else value
        return SimpleNamespace(status=200, body=body)

    api._send = send
    return api, calls


def test_cli_file_selects_attachment_through_real_transport(monkeypatch):
    api, calls = transport_client({'content_base64': 'cHJvb2Y=', 'content_type': 'image/png'})
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['capacity-evidence', 'file', '--evidence-id', '8', '--file', '2'])
    assert args.handler(args)['content_type'] == 'image/png'
    assert len(calls) == 1
    assert calls[0][:2] == ('GET', evidence.BASE + '/8/content')
    assert calls[0][2]['query'] == {'file': 2}


def test_cli_upload_parses_extra_files_and_reuse_without_required_content(monkeypatch):
    import json
    api, calls = transport_client({'id': 8, 'review_state': 'unreviewed'})
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    attachment = {'content_type': 'image/png', 'content_base64': 'cHJvb2Y='}
    parser = cli.build_parser()
    args = parser.parse_args(['capacity-evidence', 'upload', '--ref', 'B-1', '--unit', '1',
        '--kind', 'decline', '--lines', '3', '--content-type', 'image/png', '--content-base64', 'cHJvb2Y=',
        '--attachments', json.dumps([attachment])])
    args.handler(args)
    assert calls[0][2]['json_body']['attachments'] == [attachment]
    args = parser.parse_args(['capacity-evidence', 'upload', '--ref', 'B-1', '--unit', '1',
        '--kind', 'decline', '--lines', '4', '--reuse-evidence-id', '8'])
    args.handler(args)
    assert len(calls) == 4, 'Each upload makes one write and one report refresh'
    assert calls[2][2]['json_body']['reuse_evidence_id'] == 8
    assert 'content_base64' not in calls[2][2]['json_body']


def test_cli_and_mcp_confirm_one_line_while_other_lines_wait(monkeypatch):
    receipt = {'id': 8, 'review_state': 'unreviewed', 'reviewed_line': 3, 'decision': 'accepted'}
    api, calls = transport_client(receipt)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['capacity-evidence', 'review', '--evidence-id', '8',
        '--decision', 'accepted', '--line', '3'])
    assert args.handler(args) == receipt

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            schemas = {tool.name: tool.inputSchema for tool in (await sdk.list_tools()).tools}
            assert 'line' in schemas['review_capacity_evidence']['properties']
            assert 'attachments' in schemas['upload_capacity_evidence']['properties']
            assert 'reuse_evidence_id' in schemas['upload_capacity_evidence']['properties']
            assert 'file' in schemas['read_capacity_evidence_file']['properties']
            result = await sdk.call_tool('review_capacity_evidence', {'evidence_id': 8, 'decision': 'accepted', 'line': 3})
            assert not result.isError and result.structuredContent == receipt

    asyncio.run(check())
    assert len(calls) == 2
    assert all(call[2]['json_body'] == {'decision': 'accepted', 'note': '', 'line': 3} for call in calls)


@pytest.mark.parametrize('receipt', [
    {'id': 8, 'review_state': 'accepted'},
    {'id': 8, 'review_state': 'unreviewed', 'reviewed_line': 4, 'decision': 'accepted'},
    {'id': 8, 'review_state': 'unreviewed', 'reviewed_line': 3, 'decision': 'rejected'},
])
def test_wrong_line_receipt_is_unknown_without_repeating_write(receipt):
    api, calls = transport_client(receipt)
    with pytest.raises(ApiError) as failure:
        evidence.execute(api, 'review_capacity_evidence', {'evidence_id': 8, 'decision': 'accepted', 'line': 3})
    assert failure.value.code == 'outcome_unknown' and len(calls) == 1


@pytest.mark.parametrize('extra', [
    {'reuse_evidence_id': 8, 'content_type': 'image/png', 'content_base64': 'cHJvb2Y='},
    {'reuse_evidence_id': 8, 'attachments': [{'content_type': 'image/png', 'content_base64': 'cHJvb2Y='}]},
    {'reuse_evidence_id': 8, 'kind': 'pending'},
    {'content_type': 'image/png', 'content_base64': 'cHJvb2Y=', 'attachments': [{'content_type': 'image/png', 'content_base64': '???='}]},
    {'content_type': 'image/png', 'content_base64': 'cHJvb2Y=', 'attachments': [{'content_type': 'image/png', 'content_base64': 'cHJvb2Y='}] * 10},
    {'content_type': 'image/png', 'content_base64': 'cHJvb2Y=', 'kind': 'pending', 'attachments': [{'content_type': 'image/png', 'content_base64': 'cHJvb2Y='}]},
])
def test_invalid_proof_combinations_never_reach_transport(extra):
    api = Api()
    with pytest.raises(ValidationError):
        evidence.execute(api, 'upload_capacity_evidence', {'ref': 'B-1', 'unit': 1, 'kind': 'decline', 'lines': [3], **extra})
    assert not api.calls


def test_evidence_upload_enforces_combined_decoded_budget(monkeypatch):
    import base64

    from nova_cli_public import capacity_evidence as evidence
    monkeypatch.setattr(evidence, 'MAX_FILE_BYTES', 12)
    content = base64.b64encode(b'x' * 6).decode()
    request = {'ref': 'B-1', 'unit': 1, 'kind': 'decline', 'lines': [1],
        'content_type': 'application/pdf', 'content_base64': content,
        'attachments': [{'content_type': 'application/pdf', 'content_base64': content}]}
    assert evidence.Upload.model_validate(request)
    request['attachments'][0]['content_base64'] = base64.b64encode(b'x' * 7).decode()
    with pytest.raises(ValidationError, match='combined'):
        evidence.Upload.model_validate(request)


def test_evidence_schema_allows_fifty_mib_files():
    from nova_cli_public import capacity_evidence as evidence
    assert evidence.Attachment.model_json_schema()['properties']['content_base64']['maxLength'] == 69905068
