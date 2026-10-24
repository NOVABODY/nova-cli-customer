import json

import pytest

from nova_cli_public import legacy_reads
from nova_cli_public.cli import build_parser

T = '2026-06-15T12:00:00Z'


class Defects:
    def __init__(self):
        self.rows = [{'id': 'FD-1', 'reported_at': T}]
        self.queries = []

    def request(self, method, path, *, query):
        self.queries.append(query)
        rows = [r for r in self.rows if int(r['id'][3:]) > query.get('after_id', 0)]
        return {'items': rows, 'total': len(rows), 'page': 1, 'per_page': query['per_page'], 'keyset': True}


def test_new_defect_at_saved_timestamp_is_not_lost(monkeypatch, tmp_path, capsys):
    client, cursor = Defects(), tmp_path / 'cursor.json'
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda _: client)
    def pull():
        args = build_parser().parse_args(['defect', 'pull', '--new', '--cursor-file', str(cursor)])
        result = args.handler(args)
        capsys.readouterr()
        return result
    pull()
    client.rows.append({'id': 'FD-2', 'reported_at': T})
    result = pull()
    assert [r['id'] for r in result['defects']] == ['FD-2']
    assert json.loads(cursor.read_text()) == {'reported_at': T, 'id': 'FD-2'}


def test_timestamp_only_defect_cursor_replays_ties(monkeypatch, tmp_path, capsys):
    client, cursor = Defects(), tmp_path / 'cursor.json'
    cursor.write_text(json.dumps({'reported_at': T}))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda _: client)
    args = build_parser().parse_args(['defect', 'pull', '--new', '--cursor-file', str(cursor)])
    assert [r['id'] for r in args.handler(args)['defects']] == ['FD-1']
    capsys.readouterr()


@pytest.mark.parametrize('saved', [
    {'reported_at': '2026-06-15T12:00:00', 'id': 'FD-1'},
    {'reported_at': T, 'id': 'FD-2147483648'},
    {'reported_at': T, 'id': 'not-a-defect'},
])
def test_invalid_saved_defect_boundary_is_rejected_before_network(monkeypatch, tmp_path, saved):
    from nova_cli_public.errors import UsageError
    client, cursor = Defects(), tmp_path / 'cursor.json'
    cursor.write_text(json.dumps(saved))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda _: client)
    args = build_parser().parse_args(['defect', 'pull', '--new', '--cursor-file', str(cursor)])
    with pytest.raises(UsageError):
        args.handler(args)
    assert not client.queries and json.loads(cursor.read_text()) == saved
