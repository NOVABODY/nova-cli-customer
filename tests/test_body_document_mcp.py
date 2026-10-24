import asyncio
import base64
import hashlib
import io
import urllib.error
from email.message import Message

import pytest
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from nova_cli_public.body_documents import PDF_EMBED_MAX_BYTES
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

PDF = b'%PDF-1.4\n%\xff\xfe\n%%EOF'


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, declared=None):
        super().__init__(data)
        self.headers, self.sizes = Message(), []
        self.headers['Content-Type'] = 'application/pdf'
        if declared is not None:
            self.headers['Content-Length'] = str(declared)

    def read(self, size=-1):
        assert size >= 0
        self.sizes.append(size)
        return super().read(size)


class Opener:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def open(self, request, timeout):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def server(*responses):
    api = ApiClient(Profile('test', 'https://nova.example/api', 'keyring', 'delegated'), None,
        opener=Opener(*responses))
    api.access_token = 'private-token'
    return create_server(CustomerReadService(api)), api


@pytest.mark.parametrize('kind', ['quote', 'scope', 'invoice'])
def test_sdk_session_embeds_original_pdf_and_exposes_only_remote_read(tmp_path, monkeypatch, kind):
    monkeypatch.chdir(tmp_path)
    response = Response(PDF)
    app, api = server(response)
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            tool = next(t for t in (await session.list_tools()).tools if t.name == 'download_body_repair_' + kind)
            assert set(tool.inputSchema['properties']) == ({'request_ref', 'quote'} if kind == 'quote' else {'request_ref'})
            assert tool.annotations.readOnlyHint and tool.annotations.idempotentHint
            assert not tool.annotations.destructiveHint and not tool.annotations.openWorldHint
            assert tool.outputSchema['additionalProperties'] is False
            arguments = {'request_ref': 'opaque_order'}
            if kind == 'quote':
                arguments['quote'] = 'BRQ-2'
            result = await session.call_tool(tool.name, arguments)
            assert not result.isError
            result = types.CallToolResult.model_validate_json(result.model_dump_json())
            resource = result.content[0]
            assert isinstance(resource, types.EmbeddedResource)
            assert isinstance(resource.resource, types.BlobResourceContents)
            assert base64.b64decode(resource.resource.blob, validate=True) == PDF
            digest = hashlib.sha256(PDF).hexdigest()
            assert result.structuredContent == {'uri': 'urn:sha256:' + digest,
                'mime_type': 'application/pdf', 'size_bytes': len(PDF), 'sha256': digest}
            assert str(resource.resource.uri) == 'urn:sha256:' + digest
            assert resource.resource.mimeType == 'application/pdf'
            from jsonschema import validate
            validate(result.structuredContent, tool.outputSchema)
            assert 'private-token' not in result.model_dump_json() and 'file://' not in result.model_dump_json()
    asyncio.run(check())
    assert response.sizes == [PDF_EMBED_MAX_BYTES + 1]
    assert api.opener.requests[0].full_url.endswith('/opaque_order/quote?quote=BRQ-2' if kind == 'quote' else '/opaque_order/' + kind)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('declared', [None, PDF_EMBED_MAX_BYTES + 1])
def test_embedded_limit_is_enforced_during_transport_not_after_ten_megabytes(declared):
    response = Response(b'%PDF-' + b'x' * PDF_EMBED_MAX_BYTES, declared)
    app, _ = server(response)
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            result = await session.call_tool('download_body_repair_scope', {'request_ref': 'BRR-1'})
            assert result.isError and result.structuredContent['error']['code'] == 'document_too_large'
            assert '--out' in result.content[0].text
    asyncio.run(check())
    assert response.sizes == ([] if declared else [PDF_EMBED_MAX_BYTES + 1])


@pytest.mark.parametrize('code', [403, 404])
def test_document_permission_failures_keep_existing_tool_error_shape(code):
    error = urllib.error.HTTPError('https://nova.example/api', code, '', Message(), io.BytesIO(b'{}'))
    app, _ = server(error)
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            result = await session.call_tool('download_body_repair_scope', {'request_ref': '1'})
            assert result.isError
            assert result.structuredContent['error']['code'] == ('forbidden' if code == 403 else 'not_found')
    asyncio.run(check())


def test_document_tools_reject_local_paths_and_cli_still_requires_out():
    from nova_cli_public import cli

    app, api = server()
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            result = await session.call_tool('download_body_repair_scope', {'request_ref': '1', 'out': '/tmp/forbidden.pdf'})
            assert result.isError and result.structuredContent['error']['code'] == 'invalid_arguments'
    asyncio.run(check())
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(['body-repair', 'scope', 'BRR-1'])
    assert api.opener.requests == []


def test_refresh_keeps_embedded_cap_and_existing_json_tools_keep_their_shape(monkeypatch):
    body = Response(b'{}')
    error = urllib.error.HTTPError('https://nova.example/api', 401, '', Message(), body)
    pdf = Response(PDF)
    normal = io.BytesIO(b'{"items":[],"total":0}')
    normal.status, normal.headers = 200, Message()
    normal.headers['Content-Type'] = 'application/json'
    app, api = server(error, pdf, normal)
    refreshed = []
    def refresh():
        refreshed.append(True)
        api.access_token = 'refreshed-token'
    monkeypatch.setattr(api, 'refresh', refresh)
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            embedded = await session.call_tool('download_body_repair_scope', {'request_ref': '1'})
            assert not embedded.isError
            result = await session.call_tool('list_body_repair_requests', {})
            assert result.structuredContent == {'items': [], 'total': 0}
            assert isinstance(result.content[0], types.TextContent)
    asyncio.run(check())
    assert len(refreshed) == 1 and pdf.sizes == [PDF_EMBED_MAX_BYTES + 1]
    assert api.opener.requests[1].get_header('Authorization') == 'Bearer refreshed-token'



def test_invoice_tool_has_no_quote_or_file_path_selector():
    from nova_cli_public import cli, delegated
    from nova_cli_public.capabilities import manifest

    app, api = server()
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            tool = next(t for t in (await session.list_tools()).tools if t.name == 'download_body_repair_invoice')
            assert 'invoice or receipt' in tool.description
            for extra in ({'quote': 'BRQ-2'}, {'out': '/tmp/unrequested.pdf'}):
                result = await session.call_tool(tool.name, {'request_ref': 'BRR-1', **extra})
                assert result.isError and result.structuredContent['error']['code'] == 'invalid_arguments'
    asyncio.run(check())
    for extra in ([], ['--out', 'invoice.pdf', '--quote', 'BRQ-2']):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(['body-repair', 'invoice', 'BRR-1', *extra])
    entry = manifest(cli.build_parser(), 'body-repair invoice')['commands'][0]
    assert entry['required_operation'] == 'body_repair.documents.invoice.read.v1'
    assert 'invoice or receipt' in entry['description']
    assert entry['effects'] == ['remote_read', 'local_file_write'] and entry['mcp_effects'] == ['remote_read']
    assert entry['required_operation'] in delegated.OPERATIONS
    assert delegated.DEFAULT_OPERATIONS == 'vehicles.list_full.v1 vehicles.get_full.v1'
    assert api.opener.requests == []


def test_sdk_claim_zip_embeds_original_bytes_with_zip_schema(tmp_path, monkeypatch):
    import zipfile
    monkeypatch.chdir(tmp_path)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('recibo.pdf', b'receipt')
        archive.writestr('recogida.pdf', b'original scan')
    raw = output.getvalue()
    response = Response(raw)
    response.headers.replace_header('Content-Type', 'application/zip')
    app, api = server(response)
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            tool = next(t for t in (await session.list_tools()).tools if t.name == 'download_body_repair_documentation')
            assert set(tool.inputSchema['properties']) == {'request_ref', 'lang'}
            assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
            assert tool.outputSchema['properties']['mime_type'] == {'const': 'application/zip'}
            for extra in ({'out': 'unrequested.zip'}, {'quote': '1'}, {'lang': 'fr'}):
                assert (await session.call_tool(tool.name, {'request_ref': 'BRR-1', **extra})).isError
            result = await session.call_tool(tool.name, {'request_ref': 'BRR-1', 'lang': 'es'})
            assert not result.isError
            result = types.CallToolResult.model_validate_json(result.model_dump_json())
            resource = result.content[0].resource
            assert isinstance(resource, types.BlobResourceContents) and resource.mimeType == 'application/zip'
            assert base64.b64decode(resource.blob, validate=True) == raw
            assert result.structuredContent == {'uri': 'urn:sha256:' + hashlib.sha256(raw).hexdigest(),
                'mime_type': 'application/zip', 'size_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            assert 'private-token' not in result.model_dump_json() and 'file://' not in result.model_dump_json()
    asyncio.run(check())
    assert api.opener.requests[0].full_url.endswith('/BRR-1/documentation?lang=es')
    assert len(api.opener.requests) == 1 and response.sizes == [PDF_EMBED_MAX_BYTES + 1]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('declared', [None, PDF_EMBED_MAX_BYTES + 1])
def test_sdk_claim_zip_too_large_has_cli_and_browser_handoff(declared):
    response = Response(b'x' * (PDF_EMBED_MAX_BYTES + 1), declared)
    response.headers.replace_header('Content-Type', 'application/zip')
    app, _ = server(response)
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            result = await session.call_tool('download_body_repair_documentation', {'request_ref': '-opaque', 'lang': 'es'})
            assert result.isError and result.structuredContent['error']['code'] == 'archive_too_large'
            assert '--lang es -- -opaque' in result.content[0].text
            assert '--profile test body-repair' in result.content[0].text
            assert 'body-repair documentation' in result.content[0].text and 'open the order' in result.content[0].text
    asyncio.run(check())
    assert response.sizes == ([] if declared else [PDF_EMBED_MAX_BYTES + 1])


def test_sdk_pave_image_schema_native_image_and_shell_safe_profile_fallback(tmp_path, monkeypatch):
    import shlex

    from nova_cli_public import cli
    monkeypatch.chdir(tmp_path)
    raw = b'\x89PNG\r\n\x1a\noriginal'
    small, large = Response(raw), Response(b'x' * (PDF_EMBED_MAX_BYTES + 1))
    for response in (small, large):
        response.headers.replace_header('Content-Type', 'image/png')
    app, api = server(small, large)
    arguments = {'storage_key': "-key with ' quote", 'category': 'vehicle', 'idx': 0}
    async def check():
        async with create_connected_server_and_client_session(app) as session:
            tool = next(t for t in (await session.list_tools()).tools if t.name == 'download_body_repair_pave_image')
            assert set(tool.inputSchema['properties']) == {'storage_key', 'category', 'idx'}
            assert tool.inputSchema['properties']['storage_key']['maxLength'] == 500
            assert tool.inputSchema['properties']['idx']['maximum'] == 999
            assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
            for extra in ({'token': 'forbidden'}, {'out': '/tmp/forbidden'}, {'idx': True}, {'storage_key': ''}):
                assert (await session.call_tool(tool.name, {**arguments, **extra})).isError
            result = await session.call_tool(tool.name, arguments)
            assert not result.isError
            result = types.CallToolResult.model_validate_json(result.model_dump_json())
            assert len(result.content) == 1
            image = result.content[0]
            assert isinstance(image, types.ImageContent) and image.mimeType == 'image/png'
            assert base64.b64decode(image.data, validate=True) == raw
            assert result.structuredContent == {'uri': 'urn:sha256:' + hashlib.sha256(raw).hexdigest(), 'mime_type': 'image/png', 'size_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            denied = await session.call_tool(tool.name, arguments)
            assert denied.isError and denied.structuredContent['error']['code'] == 'image_too_large'
            command = denied.content[0].text.split('Use ', 1)[1].split('. / Usa ', 1)[0]
            words = shlex.split(command)
            assert words[0] == "nova"
            parsed = cli.build_parser().parse_args(words[1:])
            assert parsed.profile == api.profile.name and parsed.storage_key == arguments['storage_key']
            assert parsed.category == 'vehicle' and parsed.idx == 0
            assert 'private-token' not in result.model_dump_json() + denied.model_dump_json()
    asyncio.run(check())
    assert len(api.opener.requests) == 2 and small.sizes == large.sizes == [PDF_EMBED_MAX_BYTES + 1]
    assert list(tmp_path.iterdir()) == []
