import asyncio
from pathlib import Path

import pytest
from mcp import types

from nova_cli_public.mcp import create_server


class FileReader:
    def __init__(self):
        self.calls = []

    def tool_schemas(self):
        return {"review_cortex_file": {"type": "object", "properties": {"file": {"type": "string"}}, "required": ["file"]}}

    def output_schema(self, name):
        return {"type": "object"}

    def run(self, name, arguments):
        self.calls.append(name)
        return {'content': Path(arguments['file']).read_text()}


def call(server, path):
    result = asyncio.run(server.request_handlers[types.CallToolRequest](types.CallToolRequest(
        method='tools/call', params=types.CallToolRequestParams(name='review_cortex_file',
        arguments={'file': str(path)}))))
    return result.root


def test_unconfigured_mcp_cannot_read_local_files(tmp_path):
    source = tmp_path / 'private.csv'
    source.write_text('private')
    service = FileReader()
    result = call(create_server(service), source)
    assert result.isError, 'Local reads need a folder selected outside model arguments'
    assert not service.calls


def test_selected_folder_allows_a_snapshot_of_the_file(tmp_path):
    source = tmp_path / 'fleet.csv'
    source.write_text('allowed')
    service = FileReader()
    result = call(create_server(service, file_root=tmp_path), source)
    assert not result.isError, result
    assert result.structuredContent == {'content': 'allowed'}
    assert service.calls == ['review_cortex_file']



@pytest.mark.parametrize('kind', ['absolute', 'traversal', 'file_link', 'directory_link', 'directory'])
def test_mcp_cannot_read_outside_selected_folder_or_follow_links(tmp_path, kind):
    root = tmp_path / 'allowed'
    root.mkdir()
    private = tmp_path / 'private.csv'
    private.write_text('private')
    if kind == 'absolute':
        selected = private
    elif kind == 'traversal':
        selected = root / '..' / private.name
    elif kind == 'file_link':
        selected = root / 'link.csv'
        selected.symlink_to(private)
    elif kind == 'directory_link':
        (root / 'outside').symlink_to(tmp_path, target_is_directory=True)
        selected = root / 'outside' / private.name
    else:
        selected = root
    service = FileReader()
    result = call(create_server(service, file_root=root), selected)
    assert result.isError and not service.calls
    assert 'private' not in str(result)


def test_original_file_swap_cannot_change_the_bytes_a_tool_receives(tmp_path):
    source = tmp_path / 'fleet.csv'
    source.write_text('allowed')
    service = FileReader()
    run = service.run

    def swap(name, arguments):
        source.write_text('private')
        return run(name, arguments)

    service.run = swap
    result = call(create_server(service, file_root=tmp_path), source)
    assert result.structuredContent == {'content': 'allowed'}
    assert source.read_text() == 'private'


def test_relative_input_is_resolved_within_selected_folder(tmp_path):
    (tmp_path / 'fleet.csv').write_text('allowed')
    result = call(create_server(FileReader(), file_root=tmp_path), 'fleet.csv')
    assert not result.isError and result.structuredContent == {'content': 'allowed'}
