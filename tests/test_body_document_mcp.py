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


@pytest.mark.parametrize('kind', ['quote', 'scope'])
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
    assert api.opener.requests[0].full_url.endswith('/opaque_order/quote?quote=BRQ-2' if kind == 'quote' else '/opaque_order/scope')
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
