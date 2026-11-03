import asyncio
import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from nova_cli_public import cli, legacy_reads, legacy_writes, output
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import UsageError
from nova_cli_public.local_inputs import local_inputs
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService


@pytest.mark.parametrize('value', ['\x1b]52;c;secret\x07', {'title': 'bad\r\x1b[2K'}, ['\x9b31m']])
def test_terminal_output_escapes_record_controls(value, capsys):
    output.emit(value)
    output.warn(str(value))
    captured = capsys.readouterr()
    assert not any(c in captured.out + captured.err for c in ('\x1b', '\r', '\x07', '\x9b'))


@pytest.mark.parametrize('photo_id', ['C:\\Users\\x', '\\\\host\\share\\x', 'x\\..\\x', 'x:stream', 'CON', 'NUL'])
def test_download_rejects_nonportable_photo_names(photo_id, tmp_path):
    api = SimpleNamespace(request=lambda *a: {'items': [{'id': photo_id, 'url': 'https://example.test/p'}]})
    fetched = []
    result = legacy_reads.download_defect_photos(api, ['FD-1'], tmp_path, fetch=lambda url: fetched.append(url) or b'x')
    assert result['count'] == 0 and not fetched


def test_download_does_not_follow_existing_photo_symlink(tmp_path):
    outside = tmp_path / 'private'
    outside.write_bytes(b'private')
    folder = tmp_path / 'out' / 'FD-1'
    folder.mkdir(parents=True)
    (folder / 'P1.bin').symlink_to(outside)
    api = SimpleNamespace(request=lambda *a: {'items': [{'id': 'P1', 'url': 'https://example.test/p'}]})
    with pytest.raises(UsageError):
        legacy_reads.download_defect_photos(api, ['FD-1'], tmp_path / 'out', fetch=lambda url: b'changed')
    assert outside.read_bytes() == b'private'


@pytest.mark.parametrize('reader', [lambda p: legacy_writes.read_json_object_file(p, 'details'),
                                    lambda p: legacy_writes.build_body(None, p, [])])
def test_json_file_size_is_bounded(tmp_path, reader):
    source = tmp_path / 'body.json'
    source.write_text('{"value":"' + 'x' * (1024 * 1024) + '"}')
    with pytest.raises(UsageError):
        reader(str(source))


def test_json_stdin_remains_supported_and_bounded(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO('{"ok":true}'))
    assert legacy_writes.read_json_object_file('-', 'details') == {'ok': True}
    monkeypatch.setattr('sys.stdin', io.StringIO('{"v":"' + 'x' * (1024 * 1024) + '"}'))
    with pytest.raises(UsageError):
        legacy_writes.build_body(None, '-', [])


@pytest.mark.parametrize('command', ['vehicle-report create', 'vehicle-report promote', 'notification update-preferences'])
def test_discovery_declares_json_local_file_reads(command):
    assert 'local_file_read' in manifest(cli.build_parser(), command)['commands'][0]['effects']


def test_mcp_file_tools_disclose_local_and_external_effects():
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(None))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            for name in ['review_cortex_file', 'preview_fleet_import', 'apply_fleet_import', 'create_vehicle_report', 'promote_vehicle_report']:
                hints = tools[name].annotations
                assert not hints.readOnlyHint and hints.openWorldHint, name
    asyncio.run(check())


@pytest.mark.parametrize('value', ['/dev/stdin', '/dev/fd/0', '/proc/self/fd/0', '/dev/zero'])
def test_mcp_device_paths_never_reach_dispatch(tmp_path, value):
    with pytest.raises(UsageError), local_inputs({'file': value}, tmp_path):
        pytest.fail('Special file reached dispatch')


def test_mcp_photo_rejects_non_image_before_network(tmp_path):
    source = tmp_path / 'secret.jpg'
    source.write_bytes(b'private credential')
    with pytest.raises(UsageError), local_inputs(
        {'file': str(source), 'content_type': 'image/jpeg'}, tmp_path, tool='upload_photo'
    ):
        pytest.fail('Non-image reached dispatch')


@pytest.mark.parametrize('data,mime', [(b'\xff\xd8\xffpayload', 'image/jpeg'), (b'\x89PNG\r\n\x1a\npayload', 'image/png'),
    (b'RIFF\x10\x00\x00\x00WEBPVP8 payload', 'image/webp'), (b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1', 'image/heic')])
def test_mcp_photo_uses_content_type_from_bytes(tmp_path, data, mime):
    source = tmp_path / 'photo.bin'
    source.write_bytes(data)
    with local_inputs({'file': str(source), 'content_type': 'text/plain'}, tmp_path, tool='upload_photo') as values:
        assert values['content_type'] == mime


def test_mcp_cortex_rejects_mismatched_extension(tmp_path):
    source = tmp_path / 'secret.txt'
    source.write_text('private')
    with pytest.raises(UsageError), local_inputs(
        {'file': str(source), 'format': 'csv'}, tmp_path, tool='review_cortex_file'
    ):
        pytest.fail('Mismatched file reached parser')


@pytest.mark.parametrize('device', ['/dev/zero', '/dev/stdin', '/dev/fd/0'])
def test_cli_json_rejects_devices_without_reading(device):
    with pytest.raises(UsageError):
        legacy_writes.read_json_object_file(device, 'details')


@pytest.mark.parametrize('device', ['/dev/zero', '/dev/stdin', '/dev/fd/0'])
def test_mcp_rejects_devices_even_inside_selected_root(device):
    with pytest.raises(UsageError), local_inputs({'file': device}, Path('/')):
        pytest.fail('Device reached dispatch')


def test_mcp_rejects_fifo_without_waiting_for_writer(tmp_path):
    source = tmp_path / 'pipe.json'
    os.mkfifo(source)
    with pytest.raises(UsageError), local_inputs({'data_file': str(source)}, tmp_path):
        pytest.fail('FIFO reached dispatch')


def test_mcp_json_snapshot_has_one_mib_limit(tmp_path):
    source = tmp_path / 'body.json'
    source.write_bytes(b'x' * (1024 * 1024 + 1))
    with pytest.raises(UsageError), local_inputs({'details_file': str(source)}, tmp_path):
        pytest.fail('Oversized JSON reached dispatch')


def test_mcp_photo_guard_runs_before_upload_handler(tmp_path):
    source = tmp_path / 'secret.jpg'
    source.write_text('private credential')

    class NeverCall:
        def request(self, *args, **kwargs):
            pytest.fail('Invalid photo reached API')

    async def check():
        server = create_server(CustomerReadService(NeverCall()), file_root=tmp_path)
        async with create_connected_server_and_client_session(server) as sdk:
            result = await sdk.call_tool('upload_photo', {'file': str(source), 'content_type': 'image/jpeg',
                'kind': 'defect', 'parent_id': 'FD-1'})
            assert result.isError
    asyncio.run(check())


def test_safe_photo_download_can_replace_its_previous_regular_file(tmp_path):
    api = SimpleNamespace(request=lambda *a: {'items': [{'id': 'P1', 'url': 'https://example.test/p'}]})
    for data in (b'old', b'new'):
        legacy_reads.download_defect_photos(api, ['FD-1'], tmp_path, fetch=lambda url, data=data: data)
    assert (tmp_path / 'FD-1' / 'P1.bin').read_bytes() == b'new'


def test_terminal_json_output_preserves_original_data(capsys):
    import json

    value = {'title': '\x1b[31m', 'notes': 'Español\nsecond line'}
    output.emit(value, as_json=True)
    assert json.loads(capsys.readouterr().out) == value


def test_profile_whitespace_cannot_bypass_existing_origin_binding(tmp_path, monkeypatch):
    from nova_cli_public.config import ConfigStore

    store = ConfigStore(tmp_path / 'config.json')
    store.set_profile('personal', 'https://one.example/api')
    monkeypatch.setattr(cli, 'ConfigStore', lambda: store)
    assert cli.main(['profile', 'set', ' personal ', '--api', 'https://two.example/api']) == 2
    assert store.get_profile('personal').api == 'https://one.example/api'
