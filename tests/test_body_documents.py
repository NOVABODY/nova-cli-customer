import io
import urllib.error
from email.message import Message

import pytest

from nova_cli_public import cli, delegated
from nova_cli_public.capabilities import manifest
from nova_cli_public.client import PDF_ERROR_MAX_BYTES, PDF_MAX_BYTES, ApiClient, NoRedirects
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.reads import CustomerReadService

PDF = b'%PDF-1.4\n%\xff\xfe\n%%EOF'


class Response(io.BytesIO):
    status = 200

    def __init__(self, data=PDF, mime='application/pdf', length=None):
        super().__init__(data)
        self.headers, self.limits = Message(), []
        self.headers['Content-Type'] = mime
        if length is not None:
            self.headers['Content-Length'] = str(length)

    def read(self, size=-1):
        assert size >= 0, 'PDF reads must be bounded before decoding'
        self.limits.append(size)
        return super().read(size)


class Opener:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def open(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def client(*responses):
    result = ApiClient(Profile('test', 'https://nova.example/api', 'keyring', 'delegated'),
        None, opener=Opener(*responses))
    result.access_token = 'first-token'
    return result


@pytest.mark.parametrize('kind', ['quote', 'scope', 'invoice'])
def test_download_preserves_pdf_bytes_chosen_path_and_cli_only_discovery(tmp_path, kind):
    response = Response(length=len(PDF))
    api = client(response)
    destination = tmp_path / 'chosen.pdf'
    args = cli.build_parser().parse_args(['body-repair', kind, 'opaque_order-token', '--out', str(destination)])
    args._client = api
    assert args.handler(args) == {'ok': True, 'out': str(destination), 'content_type': 'application/pdf', 'size_bytes': len(PDF)}
    assert destination.read_bytes() == PDF and destination.stat().st_mode & 0o777 == 0o600
    request = api.opener.requests[0]
    assert request.full_url == 'https://nova.example/api/body-repair/requests/opaque_order-token/' + kind
    assert request.get_header('Authorization') == 'Bearer first-token'
    assert request.get_header('Accept') == 'application/pdf'
    assert request.get_header('Accept-encoding') == 'identity'
    assert response.limits == [PDF_MAX_BYTES + 1]
    assert not list(tmp_path.glob('.nova-document-*'))
    entry = manifest(cli.build_parser(), 'body-repair ' + kind)['commands'][0]
    assert entry['mcp_tool'] == 'download_body_repair_' + kind
    assert 'out' not in entry['tool_input_schema']['properties']
    assert entry['mcp_effects'] == ['remote_read']
    assert entry['effects'] == ['remote_read', 'local_file_write']
    assert entry['required_operation'] in delegated.OPERATIONS
    assert entry['required_operation'] not in delegated.DEFAULT_OPERATIONS
    assert 'download_body_repair_' + kind in CustomerReadService(api).tool_schemas()


@pytest.mark.parametrize('body,mime,length', [
    (PDF, 'text/html', None), (b'not-pdf', 'application/pdf', None),
    (b'%PDF-1.4\ntruncated', 'application/pdf', None),
    (PDF, 'application/pdf', len(PDF) + 1), (PDF, 'application/pdf', -1),
    (PDF, 'application/pdf', PDF_MAX_BYTES + 1),
    (b'%PDF-' + b'x' * PDF_MAX_BYTES, 'application/pdf', None),
])
def test_invalid_pdf_never_creates_a_file(tmp_path, body, mime, length):
    api = client(Response(body, mime, length))
    args = cli.build_parser().parse_args(['body-repair', 'quote', 'BRR-1', '--out', str(tmp_path / 'never.pdf')])
    args._client = api
    with pytest.raises(ApiError):
        args.handler(args)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('reference,quote', [('a/b', None), ('https://evil.example', None), ('a?x=y', None), ('BRR-1', 'opaque_quote'), ('BRR-1', '1&x=y')])
def test_invalid_reference_rejected_before_transport(tmp_path, reference, quote):
    api = client()
    words = ['body-repair', 'quote', reference, '--out', str(tmp_path / 'never')]
    args = cli.build_parser().parse_args(words + (['--quote', quote] if quote else []))
    args._client = api
    with pytest.raises(UsageError):
        args.handler(args)
    assert api.opener.requests == [] and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('code', [302, 401, 403, 404])
def test_pdf_errors_are_bounded_and_only_401_refreshes_once(monkeypatch, code):
    body = Response(b'x' * (PDF_ERROR_MAX_BYTES + 1), 'text/html')
    error = urllib.error.HTTPError('https://nova.example/api', code, 'denied', body.headers, body)
    api = client(error, Response())
    refreshed = []
    def refresh():
        refreshed.append(True)
        api.access_token = 'second-token'
    monkeypatch.setattr(api, 'refresh', refresh)
    if code == 401:
        assert api.request('GET', '/body-repair/requests/BRR-1/quote', query={'quote': 'BRQ-2'}, pdf=True) == PDF
        assert api.opener.requests[1].get_header('Authorization') == 'Bearer second-token'
        assert api.opener.requests[1].full_url.endswith('/quote?quote=BRQ-2')
    else:
        with pytest.raises(ApiError) as caught:
            api.request('GET', '/body-repair/requests/BRR-1/scope', pdf=True)
        assert caught.value.status == code and len(api.opener.requests) == 1
    assert len(refreshed) == (1 if code == 401 else 0)
    assert body.limits == [PDF_ERROR_MAX_BYTES + 1]
    assert NoRedirects().redirect_request(None, None, 302, '', {}, 'https://evil.example') is None


def test_file_publication_refuses_existing_file_and_cleans_failed_publish(tmp_path, monkeypatch):
    from nova_cli_public import body_documents

    destination = tmp_path / 'chosen.pdf'
    args = cli.build_parser().parse_args(['body-repair', 'scope', 'BRR-1', '--out', str(destination)])
    args._client = client(Response())
    destination.write_bytes(b'original')
    with pytest.raises(UsageError):
        args.handler(args)
    assert destination.read_bytes() == b'original' and args._client.opener.requests == []
    destination.unlink()
    def fail(*args):
        raise OSError('publish failed')
    monkeypatch.setattr(body_documents.os, 'link', fail)
    with pytest.raises(UsageError, match='Cannot save the document'):
        args.handler(args)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('path,query', [('/vehicles', None), ('https://evil.example/quote', None),
    ('/body-repair/requests/BRR-1/scope', {'quote': '1'}), ('/body-repair/requests/BRR-1/quote', {'unknown': '1'})])
def test_binary_mode_cannot_fetch_arbitrary_routes_or_queries(path, query):
    api = client()
    with pytest.raises(UsageError):
        api.request('GET', path, query=query, pdf=True)
    assert api.opener.requests == []


def test_exact_pdf_cap_and_repeated_401_are_bounded(monkeypatch):
    data = b'%PDF-' + b'x' * (PDF_MAX_BYTES - 10) + b'%%EOF'
    assert client(Response(data)).request('GET', '/body-repair/requests/1/scope', pdf=True) == data
    responses = []
    for _ in range(2):
        body = Response(b'{"detail":{"code":"invalid_grant"}}', 'application/json')
        responses.append(urllib.error.HTTPError('https://nova.example/api', 401, '', body.headers, body))
    api = client(*responses)
    refreshed = []
    monkeypatch.setattr(api, 'refresh', lambda: refreshed.append(True))
    with pytest.raises(ApiError) as caught:
        api.request('GET', '/body-repair/requests/1/scope', pdf=True)
    assert caught.value.status == 401 and len(refreshed) == 1 and len(api.opener.requests) == 2


def test_pdf_refuses_encoding_and_preserves_symlink_target(tmp_path):
    response = Response()
    response.headers['Content-Encoding'] = 'gzip'
    with pytest.raises(ApiError):
        client(response).request('GET', '/body-repair/requests/1/scope', pdf=True)
    target, link = tmp_path / 'original', tmp_path / 'download.pdf'
    target.write_bytes(b'keep')
    link.symlink_to(target)
    args = cli.build_parser().parse_args(['body-repair', 'scope', '1', '--out', str(link)])
    args._client = client()
    with pytest.raises(UsageError):
        args.handler(args)
    assert link.is_symlink() and target.read_bytes() == b'keep' and not args._client.opener.requests


def test_json_requests_still_return_decoded_objects():
    response = io.BytesIO(b'{"items":[]}')
    response.status, response.headers = 200, Message()
    response.headers['Content-Type'] = 'application/json'
    assert client(response).request('GET', '/vehicles') == {'items': []}


@pytest.mark.parametrize('phase', ['write', 'close'])
def test_failed_disk_write_or_close_removes_own_partial_file(tmp_path, monkeypatch, phase):
    from nova_cli_public import body_documents

    original = body_documents.os.fdopen
    class BrokenOutput:
        def __init__(self, descriptor, mode):
            self.output = original(descriptor, mode)
        def __enter__(self):
            return self
        def write(self, data):
            self.output.write(data[:3])
            if phase == 'write':
                raise OSError('disk full')
        def __exit__(self, *args):
            self.output.close()
            if phase == 'close':
                raise OSError('close failed')
    monkeypatch.setattr(body_documents.os, 'fdopen', BrokenOutput)
    args = cli.build_parser().parse_args(['body-repair', 'scope', '1', '--out', str(tmp_path / 'document.pdf')])
    args._client = client(Response())
    with pytest.raises(UsageError, match='Cannot save the document'):
        args.handler(args)
    assert list(tmp_path.iterdir()) == []


def test_permitted_pdf_trailing_whitespace_is_preserved():
    data = PDF + b' \t\r\n\f\x00'
    assert client(Response(data)).request('GET', '/body-repair/requests/1/scope', pdf=True) == data



def test_invoice_binary_transport_rejects_quote_query_before_network():
    api = client()
    with pytest.raises(UsageError):
        api.request('GET', '/body-repair/requests/BRR-1/invoice', query={'quote': 'BRQ-2'}, pdf=True)
    assert api.opener.requests == []


def test_missing_output_folder_returns_structured_cli_error(tmp_path, monkeypatch, capsys):
    import json

    from nova_cli_public import body_documents

    monkeypatch.setattr(body_documents, 'client_from_args', lambda args: client(Response()))
    destination = tmp_path / 'missing' / 'document.pdf'
    assert cli.main(['body-repair', 'scope', 'BRR-1', '--out', str(destination), '--json']) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.err)
    assert result['ok'] is False and 'Check the output folder' in result['error']
    assert 'Revisa la carpeta de salida' in result['error'] and 'Traceback' not in captured.err
    assert not captured.out and list(tmp_path.iterdir()) == []


def claim_zip(*, compression=0, lang="en"):
    import zipfile
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=compression) as archive:
        for name, data in [('recibo.pdf' if lang == 'es' else 'receipt.pdf', b'original receipt'), ('archivos-no-disponibles.txt' if lang == 'es' else 'missing-files.txt', b'One scan is not available.')]:
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 2, 0, 0, 0))
            entry.compress_type = compression
            archive.writestr(entry, data)
    return output.getvalue()


def test_claim_zip_cli_preserves_original_bytes_and_remote_read_discovery(tmp_path):
    from nova_cli_public.claim_archive import MAX_BYTES
    raw = claim_zip(lang='es')
    response = Response(raw, 'application/zip', len(raw))
    api = client(response)
    destination = tmp_path / 'chosen.zip'
    args = cli.build_parser().parse_args(['body-repair', 'documentation', '--lang', 'es', '--out', str(destination), '--', '-opaque'])
    args._client = api
    value = args.handler(args)
    assert destination.read_bytes() == raw and destination.stat().st_mode & 0o777 == 0o600
    assert value['content_type'] == 'application/zip' and response.limits == [MAX_BYTES + 1]
    assert api.opener.requests[0].full_url.endswith('/-opaque/documentation?lang=es')
    assert api.opener.requests[0].get_header('Accept') == 'application/zip'
    assert not list(tmp_path.glob('.nova-document-*'))
    entry = manifest(cli.build_parser(), 'body-repair documentation')['commands'][0]
    assert entry['required_operation'] == 'body_repair.documents.documentation.read.v1'
    assert entry['required_operation'] in delegated.OPERATIONS and entry['required_operation'] not in delegated.DEFAULT_OPERATIONS
    assert entry['effects'] == ['remote_read', 'local_file_write'] and entry['mcp_effects'] == ['remote_read']
    with pytest.raises(UsageError):
        args.handler(args)
    assert len(api.opener.requests) == 1


@pytest.mark.parametrize('fault', ['mime', 'encoding', 'status', 'length', 'oversize', 'truncated', 'compressed', 'crc'])
def test_claim_zip_invalid_transfer_or_archive_never_writes(tmp_path, fault):
    from nova_cli_public.claim_archive import MAX_BYTES
    raw = claim_zip(compression=8 if fault == 'compressed' else 0)
    if fault == 'truncated':
        raw = raw[:-4]
    if fault == 'crc':
        raw = raw.replace(b'original receipt', b'corrupt! receipt')
    response = Response(raw, 'text/html' if fault == 'mime' else 'application/zip', MAX_BYTES + 1 if fault == 'oversize' else len(raw) + 1 if fault == 'length' else None)
    if fault == 'encoding':
        response.headers['Content-Encoding'] = 'gzip'
    if fault == 'status':
        response.status = 206
    args = cli.build_parser().parse_args(['body-repair', 'documentation', 'BRR-1', '--out', str(tmp_path / 'never.zip')])
    args._client = client(response)
    with pytest.raises(ApiError):
        args.handler(args)
    assert list(tmp_path.iterdir()) == []
    if fault == 'oversize':
        assert response.limits == []


@pytest.mark.parametrize('query', [{'quote': '1'}, {'url': 'https://evil.example'}])
def test_claim_zip_no_selector_or_arbitrary_binary_route(query):
    api = client()
    with pytest.raises(UsageError):
        api.request('GET', '/body-repair/requests/BRR-1/documentation', query=query, archive=True)
    assert not api.opener.requests


def test_claim_zip_refresh_preserves_format_and_limit(monkeypatch):
    body = Response(b'{}', 'application/json')
    error = urllib.error.HTTPError('https://nova.example/api', 401, '', body.headers, body)
    response = Response(claim_zip(), 'application/zip')
    api = client(error, response)
    refreshed = []
    monkeypatch.setattr(api, 'refresh', lambda: refreshed.append(True))
    assert api.request('GET', '/body-repair/requests/1/documentation', archive=True, archive_max_bytes=1024) == claim_zip()
    assert refreshed == [True] and response.limits == [1025]


def test_claim_zip_bounds_directory_bytes_before_zipfile_allocation(monkeypatch):
    import struct
    import zipfile

    from nova_cli_public import claim_archive

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for index in range(100):
            archive.writestr(f'scan-{index}.pdf', b'x')
    raw = bytearray(output.getvalue())
    end = raw.rfind(b'PK\x05\x06')
    struct.pack_into('<HH', raw, end + 8, 2, 2)
    monkeypatch.setattr(claim_archive.zipfile, 'ZipFile',
        lambda *args, **kwargs: pytest.fail('Unbounded directory reached ZipFile allocation'))
    with pytest.raises(ApiError):
        claim_archive.read(Response(bytes(raw), 'application/zip'), claim_archive.MAX_BYTES)


def test_claim_zip_language_is_closed_before_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr('nova_cli_public.body_documents.client_from_args',
        lambda args: pytest.fail('Invalid language loaded credentials'))
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(['body-repair', 'documentation', 'BRR-1', '--lang', 'fr', '--out', str(tmp_path / 'never.zip')])
    with pytest.raises(UsageError):
        client().request('GET', '/body-repair/requests/BRR-1/documentation', archive=True, query={'lang': 'fr'})



@pytest.mark.parametrize('raw,media', [(b'\x89PNG\r\n\x1a\noriginal', 'image/png'), (b'\xff\xd8\xfforiginal', 'image/jpeg'), (b'RIFF1234WEBPoriginal', 'image/webp')])
def test_pave_image_cli_fixed_query_original_bytes_and_safe_output(tmp_path, raw, media):
    from urllib.parse import parse_qs, urlsplit
    response = Response(raw, media)
    api = client(response)
    destination = tmp_path / 'chosen.image'
    key = "photos/pave/key with ' quote"
    args = cli.build_parser().parse_args(['body-repair', 'pave-image', '--storage-key=' + key, '--category', 'panel', '--idx', '2', '--out', str(destination)])
    args._client = api
    assert args.handler(args)['content_type'] == media
    assert destination.read_bytes() == raw and destination.stat().st_mode & 0o777 == 0o600
    request = api.opener.requests[0]
    assert urlsplit(request.full_url).path == '/api/body-repair/pave/image'
    assert parse_qs(urlsplit(request.full_url).query) == {'storage_key': [key], 'category': ['panel'], 'idx': ['2']}
    assert request.get_header('Authorization') == 'Bearer first-token'
    assert response.limits == [64 * 1024 * 1024 + 1]
    with pytest.raises(UsageError):
        args.handler(args)
    assert len(api.opener.requests) == 1 and not list(tmp_path.glob('.nova-document-*'))
    entry = manifest(cli.build_parser(), 'body-repair pave-image')['commands'][0]
    assert entry['effects'] == ['remote_read', 'local_file_write'] and entry['mcp_effects'] == ['remote_read']
    assert entry['required_operation'] == 'body_repair.pave.images.read.v1'
    assert entry['required_operation'] not in delegated.DEFAULT_OPERATIONS


@pytest.mark.parametrize('fault', ['mime', 'magic', 'signature', 'encoding', 'length', 'status', 'oversize'])
def test_pave_image_transport_rejects_invalid_bytes_and_metadata(fault):
    response = Response(b'not-an-image' if fault == 'signature' else b'\x89PNG\r\n\x1a\noriginal', 'image/jpeg' if fault == 'magic' else 'application/octet-stream' if fault == 'mime' else 'image/png', 65 * 1024 * 1024 if fault == 'oversize' else 100 if fault == 'length' else None)
    if fault == 'encoding':
        response.headers['Content-Encoding'] = 'gzip'
    if fault == 'status':
        response.status = 206
    with pytest.raises(ApiError):
        client(response).request('GET', '/body-repair/pave/image', query={'storage_key': 'key', 'category': 'panel', 'idx': 0}, image=True)
    if fault == 'oversize':
        assert response.limits == []


def test_pave_image_invalid_arguments_precede_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr('nova_cli_public.legacy_reads.client_from_args', lambda args: pytest.fail('Invalid image loaded credentials'))
    args = cli.build_parser().parse_args(['body-repair', 'pave-image', '--storage-key=', '--category', 'panel', '--idx', '1000', '--out', str(tmp_path / 'never')])
    with pytest.raises(UsageError):
        args.handler(args)


def test_pave_image_refresh_preserves_binary_mode_and_cap(monkeypatch):
    body = Response(b'{}', 'application/json')
    error = urllib.error.HTTPError('https://nova.example/api', 401, '', body.headers, body)
    raw = b'\xff\xd8\xfforiginal'
    response = Response(raw, 'image/jpeg')
    api = client(error, response)
    refreshed = []
    monkeypatch.setattr(api, 'refresh', lambda: refreshed.append(True))
    assert api.request('GET', '/body-repair/pave/image', query={'storage_key': 'key', 'category': 'damage', 'idx': 0}, image=True, image_max_bytes=1024) == raw
    assert refreshed == [True] and response.limits == [1025]


def test_pave_image_streamed_oversize_is_bounded_before_signature_validation():
    response = Response(b'x' * 1025, 'image/png')
    with pytest.raises(ApiError) as caught:
        client(response).request('GET', '/body-repair/pave/image',
            query={'storage_key': 'key', 'category': 'panel', 'idx': 0}, image=True, image_max_bytes=1024)
    assert caught.value.code == 'image_too_large' and response.limits == [1025]
