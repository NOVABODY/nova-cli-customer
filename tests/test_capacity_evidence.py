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
