"""The named stdio report tools use the real delegated transport signature."""
import io
import json
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.vendor_defect_reports import MAX_BYTES, MIMES

PARAMS = {'date_from': '2026-09-20', 'date_to': '2026-09-20', 'external_vendor_id': 7,
          'date_basis': 'sent', 'critical': False, 'max_rows': 1}
VALUE = {'summary': {'total_rows': 5, 'critical_defects': 2, 'returned_rows': 1, 'vans': {'total': 3}},
         'items': [{'critical_at_report': False}]}


def service(monkeypatch, payload=VALUE, media='application/json'):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            response = io.BytesIO(json.dumps(payload).encode() if media == 'application/json' else payload)
            response.status, response.headers = 200, Message()
            response.headers['Content-Type'] = media
            return response
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=Opener())
    client.access_token = 'synthetic-access'
    return CustomerReadService(client), calls


def test_stdio_report_keeps_full_counts_and_false_criticality(monkeypatch):
    reader, calls = service(monkeypatch)
    assert reader.run('get_vendor_defect_report', PARAMS) == VALUE
    assert reader.output_schema('get_vendor_defect_report')['properties']['summary']
    request = calls[0]
    assert request.method == 'GET' and request.data is None
    assert urlsplit(request.full_url).path == '/api/defects/report'
    assert parse_qs(urlsplit(request.full_url).query)['critical'][0].lower() == 'false'
    assert parse_qs(urlsplit(request.full_url).query)['date_basis'] == ['sent']


@pytest.mark.parametrize('format,raw', [('csv', b'Critical at report\nfalse\n'), ('xlsx', b'PK\x03\x04synthetic')])
def test_stdio_exports_embed_original_bytes_without_row_cap(monkeypatch, format, raw):
    reader, calls = service(monkeypatch, raw, MIMES[format])
    result = reader.run('export_vendor_defect_report', {**PARAMS, 'format': format})
    assert result.data == raw and result.mime_type == MIMES[format]
    assert 'max_rows' not in parse_qs(urlsplit(calls[0].full_url).query)
    assert urlsplit(calls[0].full_url).path == '/api/defects/report/export.' + format


@pytest.mark.parametrize('patch', [{'critical': 'false'}, {'external_vendor_id': True}, {'date_to': 'bad'},
                                  {'date_to': '2026-09-01'}, {'url': 'https://other.example'}, {'max_rows': 10001}])
def test_invalid_report_filters_never_reach_transport(monkeypatch, patch):
    reader, calls = service(monkeypatch)
    with pytest.raises(ValidationError):
        reader.run('get_vendor_defect_report', {**PARAMS, **patch})
    assert calls == []


def test_options_read_uses_its_fixed_route(monkeypatch):
    reader, calls = service(monkeypatch, {'vendors': [], 'external_vendors': []})
    assert reader.run('get_vendor_defect_report_options', {}) == {'vendors': [], 'external_vendors': []}
    assert urlsplit(calls[0].full_url).path == '/api/defects/report/options'


@pytest.mark.parametrize('raw,media', [(b'private html', 'text/html'), (b'x' * (MAX_BYTES + 1), 'text/csv')])
def test_export_rejects_wrong_mime_and_oversize_response(monkeypatch, raw, media):
    from nova_cli_public.errors import ApiError
    reader, _ = service(monkeypatch, raw, media)
    with pytest.raises(ApiError):
        reader.run('export_vendor_defect_report', {**PARAMS, 'format': 'csv'})


def test_cli_export_saves_original_bytes_to_requested_file(monkeypatch, tmp_path):
    from nova_cli_public import cli, legacy_reads
    raw = b'Critical at report\nfalse\n'
    reader, calls = service(monkeypatch, raw, MIMES['csv'])
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: reader.client)
    output = tmp_path / 'report.csv'
    args = cli.build_parser().parse_args(['report', 'vendor-defects-export', '--date-from', '2026-09-20',
        '--date-to', '2026-09-20', '--external-vendor-id', '7', '--date-basis', 'sent',
        '--no-critical', '--format', 'csv', '--out', str(output)])
    result = args.handler(args)
    assert result['content_type'] == MIMES['csv'] and output.read_bytes() == raw
    assert parse_qs(urlsplit(calls[0].full_url).query)['critical'][0].lower() == 'false'


def test_stdio_sdk_transmits_report_and_original_export_bytes(tmp_path):
    import asyncio
    import base64
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    host = tmp_path / 'synthetic_host.py'
    host.write_text('''import asyncio
from nova_cli_public.mcp import create_server, run_stdio
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.errors import ApiError
class Client:
    def request(self, method, path, *, query=None, report_format=None):
        assert method == 'GET'
        if query.get('search') in ('denied', 'revoked'):
            raise ApiError('Private reason', status=403 if query['search'] == 'denied' else 401)
        if report_format:
            assert 'max_rows' not in query
            return b'Critical at report\\nfalse\\n'
        return {'summary': {'total_rows': 5, 'critical_defects': 2, 'returned_rows': 1, 'vans': {'total': 3}},
                'items': [{'critical_at_report': False}]}
asyncio.run(run_stdio(create_server(CustomerReadService(Client()))))
''')

    async def journey():
        async with stdio_client(StdioServerParameters(command=sys.executable, args=[str(host)], env=dict(os.environ))) as (read, write), ClientSession(read, write) as sdk:
            await sdk.initialize()
            report = await sdk.call_tool('get_vendor_defect_report', PARAMS)
            assert not report.isError and report.structuredContent == VALUE
            exported = await sdk.call_tool('export_vendor_defect_report', {**PARAMS, 'format': 'csv'})
            assert not exported.isError
            assert base64.b64decode(exported.content[0].resource.blob) == b'Critical at report\nfalse\n'
            for search in ('denied', 'revoked'):
                denied = await sdk.call_tool('get_vendor_defect_report', {**PARAMS, 'search': search})
                assert denied.isError and 'Private reason' not in str(denied)
    asyncio.run(journey())
