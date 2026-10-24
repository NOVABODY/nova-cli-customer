import json

import pytest

from nova_cli_public.cli import build_parser
from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.reads import CustomerReadService

ROW = {'fleet_id': 'Synthetic 1', 'vin': '1FTBR1C85LKA12345', 'plate': 'ABC123',
       'year': 2020, 'make': 'Ford', 'model': 'Transit', 'ownership': 'dsp_owned'}


def reviewed(tmp_path, **changes):
    path = tmp_path / 'review.json'
    path.write_text(json.dumps({'mapped': [ROW], 'errors': [], 'missing_columns': [],
                                'skipped': 0, 'records': [{'excluded': False, 'inactive': False}], **changes}))
    return path


class Importer:
    def __init__(self):
        self.calls = []
        self.response = {'results': [{'action': 'created', 'vin': ROW['vin']}], 'summary': {'created': 1, 'error': 0}}

    def request(self, method, path, *, json_body):
        self.calls.append((method, path, json_body))
        return self.response


@pytest.mark.parametrize('action,dry_run', [('preview', True), ('apply', False)])
def test_cli_import_action_owns_dry_run_and_only_sends_existing_payload(tmp_path, action, dry_run):
    source, api = reviewed(tmp_path, dry_run=not dry_run, actor_id=999), Importer()
    args = build_parser().parse_args(['fleet-import', action, '--review-file', str(source), '--add-missing-stations'])
    args._client = api
    result = args.handler(args)
    assert result['ok'] is True and result['dry_run'] is dry_run
    assert api.calls == [('POST', '/vehicles/bulk-upsert', {'rows': [ROW], 'dry_run': dry_run,
                         'add_missing_stations': True, 'deactivate_missing': False})]


@pytest.mark.parametrize('changes', [{'errors': [{'row_index': 3}]}, {'missing_columns': ['vin']}, {'mapped': []},
                                   {'mapped': [ROW] * 2001}, {'records': []}])
def test_unresolved_or_unimportable_review_never_reaches_the_api(tmp_path, changes):
    source, api = reviewed(tmp_path, **changes), Importer()
    args = build_parser().parse_args(['fleet-import', 'apply', '--review-file', str(source)])
    args._client = api
    with pytest.raises(UsageError):
        args.handler(args)
    assert not api.calls


@pytest.mark.parametrize('changes', [{'skipped': 1}, {'records': [{'excluded': True, 'inactive': False}]}, {'records': [{'excluded': False, 'inactive': True}]}])
def test_deactivation_cannot_drop_explicitly_excluded_or_skipped_rows(tmp_path, changes):
    source, api = reviewed(tmp_path, **changes), Importer()
    args = build_parser().parse_args(['fleet-import', 'apply', '--review-file', str(source), '--deactivate-missing'])
    args._client = api
    with pytest.raises(UsageError):
        args.handler(args)
    assert not api.calls


def test_partial_row_failures_are_not_reported_as_complete_success(tmp_path):
    source, api = reviewed(tmp_path), Importer()
    api.response = {'results': [{'action': 'error', 'code': 'station_not_assigned'}], 'summary': {'error': 1}}
    result = CustomerReadService(api).run('apply_fleet_import', {'review_file': str(source)})
    assert result['ok'] is False and result['results'] == api.response['results']


def test_invalid_successful_apply_response_has_unknown_outcome(tmp_path):
    source, api = reviewed(tmp_path), Importer()
    api.response = {'unexpected': True}
    with pytest.raises(ApiError) as error:
        CustomerReadService(api).run('apply_fleet_import', {'review_file': str(source)})
    assert error.value.code == 'outcome_unknown' and len(api.calls) == 1


def test_partial_import_returns_nonzero_cli_exit_with_results(monkeypatch, tmp_path, capsys):
    from nova_cli_public import cli
    source, api = reviewed(tmp_path), Importer()
    api.response = {'results': [{'action': 'error', 'code': 'station_not_assigned'}], 'summary': {'error': 1}}
    monkeypatch.setattr(cli, 'client_from_args', lambda _: api)
    assert cli.main(['--json', 'fleet-import', 'apply', '--review-file', str(source)]) != 0
    assert json.loads(capsys.readouterr().out)['results'] == api.response['results']


def test_partial_import_is_an_mcp_error_with_actionable_rows(tmp_path):
    import asyncio

    from mcp import types

    from nova_cli_public.mcp import create_server
    source, api = reviewed(tmp_path), Importer()
    api.response = {'results': [{'action': 'error', 'code': 'station_not_assigned'}], 'summary': {'error': 1}}
    server = create_server(CustomerReadService(api))
    result = asyncio.run(server.request_handlers[types.CallToolRequest](types.CallToolRequest(
        method='tools/call', params=types.CallToolRequestParams(name='apply_fleet_import', arguments={'review_file': str(source)}))))
    assert result.root.isError and result.root.structuredContent['results'] == api.response['results']


@pytest.mark.parametrize('status,unknown', [(503, True), (403, False)])
def test_apply_error_never_retries_and_preserves_denial(tmp_path, status, unknown):
    source, api = reviewed(tmp_path), Importer()
    def fail(*args, **kwargs):
        api.calls.append((args, kwargs))
        raise ApiError('Synthetic failure', status=status)
    api.request = fail
    with pytest.raises(ApiError) as error:
        CustomerReadService(api).run('apply_fleet_import', {'review_file': str(source)})
    assert (error.value.code == 'outcome_unknown') is unknown and len(api.calls) == 1


def test_preview_is_read_only_but_requires_full_import_consent():
    import asyncio

    from mcp import types

    from nova_cli_public.capabilities import manifest
    from nova_cli_public.mcp import create_server
    server = create_server(CustomerReadService(Importer()))
    result = asyncio.run(server.request_handlers[types.ListToolsRequest](types.ListToolsRequest(method='tools/list')))
    tools = {tool.name: tool for tool in result.root.tools}
    assert tools['preview_fleet_import'].annotations.readOnlyHint and not tools['preview_fleet_import'].annotations.destructiveHint
    assert not tools['apply_fleet_import'].annotations.readOnlyHint and tools['apply_fleet_import'].annotations.destructiveHint
    entry, = manifest(build_parser(), selected='fleet-import preview')['commands']
    assert entry['effects'] == ['remote_read', 'local_file_read'] and entry['required_scope'] == 'nova:read nova:write'
