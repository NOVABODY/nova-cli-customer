"""CLI and local MCP use the real customer transport for the same report."""
import io
import json
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.reads import CustomerReadService

VALUE = {'as_of': '2026-11-23T12:00:00Z', 'total': 0, 'amount_cents': 0, 'currency': 'USD', 'items': []}


def test_cli_and_stdio_preserve_filter_contract_with_real_transport(monkeypatch):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            response = io.BytesIO(json.dumps(VALUE).encode())
            response.status, response.headers = 200, Message()
            response.headers['Content-Type'] = 'application/json'
            return response
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=Opener())
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    parsed = cli.build_parser().parse_args(['report', 'open-quotes', '--kind', 'cmr', '--search', '%_', '--offset', '25'])
    assert parsed.handler(parsed) == VALUE
    service = CustomerReadService(client)
    assert service.run('get_open_quotes_report', {'kind': 'cmr', 'search': '%_', 'offset': 25}) == VALUE
    assert service.output_schema('get_open_quotes_report')['properties']['items']['type'] == 'array'
    for request in calls:
        assert request.method == 'GET' and request.data is None
        assert urlsplit(request.full_url).path == '/api/dashboards/reports/open-quotes'
        assert parse_qs(urlsplit(request.full_url).query) == {'kind': ['cmr'], 'search': ['%_'], 'offset': ['25'], 'limit': ['25']}


@pytest.mark.parametrize('args', [{'kind': 'all'}, {'limit': 201}, {'offset': -1}, {'url': 'https://elsewhere.example'}, {'limit': True}])
def test_invalid_filters_fail_before_transport(args):
    with pytest.raises(ValidationError):
        CustomerReadService(object()).run('get_open_quotes_report', args)
