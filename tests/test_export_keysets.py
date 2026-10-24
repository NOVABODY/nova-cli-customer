"""An earlier row changing must not hide unprocessed export rows."""
import pytest

from nova_cli_public.errors import ApiError
from nova_cli_public.legacy_reads import fetch_all_vehicle_reports

T = '2026-06-15T12:00:00Z'


class MovingReports:
    def __init__(self):
        self.calls = []
        self.rows = [{'id': f'VR-{i}', 'updated_at': T} for i in [1, 2, 3]]

    def request(self, method, path, *, query):
        self.calls.append(query)
        if len(self.calls) == 2:
            self.rows[0]['updated_at'] = '2026-06-15T13:00:00Z'
        rows = sorted(self.rows, key=lambda r: (r['updated_at'], int(r['id'][3:])))
        if 'after_id' in query:
            rows = [r for r in rows if (r['updated_at'], int(r['id'][3:])) > (query['updated_since'], query['after_id'])]
        offset = query.get('offset', 0)
        return {'items': [dict(r) for r in rows[offset:offset + 1]], 'total': len(rows),
                'offset': offset, 'limit': 1, 'keyset': 'after_id' in query}


def test_moving_report_does_not_skip_the_next_report():
    client = MovingReports()
    result = fetch_all_vehicle_reports(client, {'limit': 1})
    assert {r['id'] for r in result} == {'VR-1', 'VR-2', 'VR-3'}
    assert len(result) == 3 and all(q['offset'] == 0 for q in client.calls)
    assert next(r for r in result if r['id'] == 'VR-1')['updated_at'] == '2026-06-15T13:00:00Z'


def test_unsupported_keysets_fail_without_returning_a_partial_export():
    client = MovingReports()
    client.request = lambda *a, **k: {'items': [], 'total': 0, 'offset': 0, 'limit': 1}
    with pytest.raises(ApiError, match='keyset'):
        fetch_all_vehicle_reports(client, {'limit': 1})


@pytest.mark.parametrize('response', [
    {'items': [], 'total': 1, 'offset': 0, 'limit': 1, 'keyset': True},
    {'items': [{'id': 'VR-1', 'updated_at': T}], 'total': 1, 'offset': 0, 'limit': 1, 'keyset': True},
])
def test_invalid_or_nonprogressing_page_preserves_output_and_cursor(monkeypatch, tmp_path, response):
    import json

    from nova_cli_public import legacy_reads
    from nova_cli_public.cli import build_parser
    cursor, out = tmp_path / 'cursor.json', tmp_path / 'output.json'
    original = {'updated_at': T, 'id': 'VR-1'}
    cursor.write_text(json.dumps(original))
    out.write_text('previous output')
    client = MovingReports()
    client.request = lambda *a, **k: response
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda _: client)
    args = build_parser().parse_args(['vehicle-report', 'pull', '--per-page', '1', '--cursor-file', str(cursor), '--out', str(out)])
    with pytest.raises(ApiError):
        args.handler(args)
    assert json.loads(cursor.read_text()) == original and out.read_text() == 'previous output'
