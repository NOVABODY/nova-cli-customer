import io
import json
from email.message import Message

import pytest

from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.reads import CustomerReadService


@pytest.mark.parametrize('action', ['keep', 'inactive', 'update_plate', 'plate_correct'])
def test_resolve_posts_native_action_once_and_preserves_receipt(action, monkeypatch):
    calls = []
    receipt = {'id': 7, 'status': 'resolved', 'resolution': action, 'observations': [], 'native': True}
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            response = io.BytesIO(json.dumps(receipt).encode())
            response.status, response.headers = 200, Message()
            response.headers['Content-Type'] = 'application/json'
            return response
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=Opener())
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(client, 'refresh', lambda: pytest.fail('Do not retry a fleet decision'))
    assert CustomerReadService(client).run('resolve_fleet_issue', {'issue_id': 7, 'action': action, 'memo': ' Done '}) == receipt
    assert len(calls) == 1 and calls[0].method == 'POST'
    assert calls[0].full_url == 'https://nova.example/api/fleet-issues/7/resolve'
    assert json.loads(calls[0].data) == {'action': action, 'memo': 'Done'}


def test_list_retains_all_native_filters_and_summary(monkeypatch):
    from nova_cli_public import legacy_reads
    calls = []
    receipt = {'items': [], 'total': 0, 'limit': 100, 'offset': 3, 'summary': {'confirm': 2, 'decide': 1}}
    class Client:
        def request(self, *args, **kwargs):
            calls.append((args, kwargs))
            return receipt
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: Client())
    filters = {'kind': 'plate_mismatch', 'status': 'resolved', 'group': 'decide', 'limit': 100, 'offset': 3}
    assert CustomerReadService(Client()).run('list_fleet_updates', filters) == receipt
    assert calls == [(('GET', '/fleet-updates'), {'query': filters})]


@pytest.mark.parametrize('arguments', [{'issue_id': 0, 'action': 'keep'}, {'issue_id': True, 'action': 'keep'}, {'issue_id': 7, 'action': 'force'}, {'issue_id': 7, 'action': 'keep', 'memo': 'x' * 1001}, {'issue_id': 7, 'action': 'keep', 'force': True}])
def test_fleet_decision_inputs_are_closed_and_bounded(arguments):
    from pydantic import ValidationError

    from nova_cli_public.fleet_decisions import Resolve
    with pytest.raises(ValidationError):
        Resolve(**arguments)


@pytest.mark.parametrize('receipt', [{'id': 8, 'status': 'resolved', 'resolution': 'keep'}, {'id': 7, 'status': 'pending', 'resolution': 'keep'}, {'id': 7, 'status': 'resolved', 'resolution': 'inactive'}, {'id': 7, 'status': 'resolved', 'resolution': 'keep', 'bad': float('nan')}])
def test_invalid_fleet_receipt_is_unknown(monkeypatch, receipt):
    from nova_cli_public import legacy_reads
    from nova_cli_public.errors import ApiError
    class Client:
        def request(self, *args, **kwargs):
            return receipt
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: Client())
    with pytest.raises(ApiError) as error:
        CustomerReadService(Client()).run('resolve_fleet_issue', {'issue_id': 7, 'action': 'keep'})
    assert error.value.code == 'outcome_unknown'


def test_cli_and_mcp_share_fleet_schema_and_admission_routes():
    from nova_cli_public import capabilities, cli
    parser = cli.build_parser()
    args = parser.parse_args(['fleet-issue', 'resolve', '7', 'plate_correct', '--memo', 'Checked'])
    assert (args.issue_id, args.action, args.memo) == (7, 'plate_correct', 'Checked')
    entries = {entry['mcp_tool']: entry for entry in capabilities.manifest(parser)['commands'] if entry.get('mcp_tool')}
    resolve = entries['resolve_fleet_issue']
    assert resolve['required_operation'] == 'fleet_issues.resolve.v1'
    assert resolve['required_scope'] == 'nova:read nova:write'
    assert resolve['effects'] == ['remote_write']
    assert resolve['api_routes'] == [{'method': 'POST', 'path_pattern': r'/fleet-issues/[0-9]{1,14}/resolve'}]
    listing = entries['list_fleet_updates']
    assert listing['effects'] == ['remote_read']
    assert listing['api_routes'] == [{'method': 'GET', 'path_pattern': '/fleet-updates'}]
