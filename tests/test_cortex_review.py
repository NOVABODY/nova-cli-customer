import json
from types import SimpleNamespace

import pytest

from nova_cli_public.cli import build_parser
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.errors import UsageError
from nova_cli_public.reads import CustomerReadService

SOURCE = b'vin,vehicleName\nBAD,Synthetic van\n'


class Opener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = SimpleNamespace(status=200, headers={'Content-Type': 'application/json'},
                                   read=lambda: json.dumps({'records': [], 'mapped': [], 'errors': [], 'skipped': 0, 'missing_columns': []}).encode())
        class Context:
            def __enter__(self):
                return response
            def __exit__(self, *args):
                return None
        return Context()


def client():
    opener = Opener()
    api = ApiClient(Profile('synthetic', 'https://nova.example/api'), None, opener=opener)
    api.access_token = 'synthetic-token'
    return api, opener


def test_cli_resends_unchanged_file_and_cumulative_corrections(tmp_path):
    source = tmp_path / 'fleet.csv'
    source.write_bytes(SOURCE)
    api, opener = client()
    for options in ['{}', '{"corrections":{"2":{"vin":"1FTBR1C85LKA12345"}}}']:
        args = build_parser().parse_args(['fleet-import', 'review', '--file', str(source), '--options', options])
        args._client = api
        assert args.handler(args)['errors'] == []
        request = opener.requests[-1]
        assert request.get_method() == 'POST' and request.full_url == 'https://nova.example/api/vehicles/fleet-import/parse?format=csv'
        assert SOURCE in request.data and options.encode() in request.data
        assert request.get_header('Authorization') == 'Bearer synthetic-token'
        assert request.get_header('Content-type').startswith('multipart/form-data; boundary=')
    assert source.read_bytes() == SOURCE


def test_stdio_review_uses_same_file_bytes_and_typed_tool(tmp_path):
    source = tmp_path / 'fleet.xlsx'
    source.write_bytes(b'Synthetic workbook bytes')
    api, opener = client()
    service = CustomerReadService(api)
    assert service.tool_schemas()['review_cortex_file']['additionalProperties'] is False
    assert service.run('review_cortex_file', {'file': str(source)})['mapped'] == []
    assert b'Synthetic workbook bytes' in opener.requests[-1].data
    assert opener.requests[-1].full_url.endswith('?format=xlsx')


@pytest.mark.parametrize('options', ['[]', '{"x":', '"' + 'x' * 65536 + '"'], ids=['nonobject', 'malformed', 'oversized'])
def test_invalid_or_oversized_options_fail_before_network(tmp_path, options):
    source = tmp_path / 'fleet.csv'
    source.write_bytes(SOURCE)
    api, opener = client()
    args = build_parser().parse_args(['fleet-import', 'review', '--file', str(source), '--options', options])
    args._client = api
    with pytest.raises(UsageError):
        args.handler(args)
    assert not opener.requests


def test_review_refresh_preserves_identical_read_only_post_body(monkeypatch, tmp_path):
    from io import BytesIO
    from urllib.error import HTTPError
    source = tmp_path / 'fleet.csv'
    source.write_bytes(SOURCE)
    api, opener = client()
    original = opener.open
    def open_once(request, timeout):
        if not opener.requests:
            opener.requests.append(request)
            raise HTTPError(request.full_url, 401, 'Expired', {'Content-Type': 'application/json'}, BytesIO(b'{}'))
        return original(request, timeout)
    monkeypatch.setattr(opener, 'open', open_once)
    monkeypatch.setattr(api, 'refresh', lambda: setattr(api, 'access_token', 'fresh-synthetic'))
    args = build_parser().parse_args(['fleet-import', 'review', '--file', str(source)])
    args._client = api
    assert args.handler(args)['errors'] == []
    assert len(opener.requests) == 2 and opener.requests[0].data == opener.requests[1].data
    assert opener.requests[1].get_header('Authorization') == 'Bearer fresh-synthetic'


def test_oversized_file_fails_before_network(tmp_path):
    source = tmp_path / 'fleet.csv'
    with source.open('wb') as file:
        file.truncate(20 * 1024 * 1024 + 1)
    api, opener = client()
    args = build_parser().parse_args(['fleet-import', 'review', '--file', str(source)])
    args._client = api
    with pytest.raises(UsageError, match='20 MiB'):
        args.handler(args)
    assert not opener.requests


def test_cortex_discovery_discloses_file_read_and_exact_post_route():
    from nova_cli_public.capabilities import manifest
    entry, = manifest(build_parser(), selected='fleet-import review')['commands']
    assert entry['effects'] == ['remote_read', 'local_file_read']
    assert entry['required_operation'] == 'vehicles.fleet_import.review.v1' and entry['required_scope'] == 'nova:read'
    assert entry['api_routes'] == [{'method': 'POST', 'path_pattern': '/vehicles/fleet-import/parse'}]
