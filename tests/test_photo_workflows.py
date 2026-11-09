from types import SimpleNamespace

import pytest

from nova_cli_public import cli
from nova_cli_public.errors import UsageError


class Client:
    profile = SimpleNamespace(auth='password')

    def __init__(self):
        self.calls, self.puts = [], []

    def request(self, method, path, **kwargs):
        body = kwargs.get('json_body')
        self.calls.append((method, path, body))
        if path == '/uploads/presigned':
            collection = {'work_order': 'work_orders', 'vehicle_checkout': 'vehicle_checkouts'}[body['kind']]
            return {'upload_url': 'https://storage.example/signed',
                    'storage_key': f"photos/{collection}/2/date/photo.png"}
        return {'id': 'WO-2', 'status': 'completed'}

    def put_bytes(self, url, data, **kwargs):
        self.puts.append((url, data, kwargs))


def run(words, client):
    args = cli.build_parser().parse_args(words)
    args._client = client
    return args.handler(args)


@pytest.mark.parametrize('action', ['check-out', 'check-in'])
def test_custody_uploads_local_file_with_vehicle_parent_before_commit(tmp_path, action):
    source = tmp_path / 'photo.png'
    source.write_bytes(b'\x89PNG\r\n\x1a\nphoto')
    client = Client()
    words = ['vehicle', action, 'VAN-2', '--mileage', '100', '--photo-file', str(source)]
    if action == 'check-out':
        words += ['--vendor-workshop-id', '3']
    run(words, client)
    assert client.calls[0][2]['kind'] == 'vehicle_checkout'
    assert client.calls[0][2]['parent_id'] == 'VAN-2'
    assert client.calls[-1][1] == f'/vehicles/VAN-2/{action}'
    assert client.calls[-1][2]['photos'] == [{'storage_key': 'photos/vehicle_checkouts/2/date/photo.png',
        'content_type': 'image/png', 'size_bytes': len(source.read_bytes())}]
    assert 'confirmed_mileage_floor' not in client.calls[-1][2]
    assert len(client.puts) == 1


def test_completion_uploads_local_image_and_preserves_existing_key(tmp_path):
    source = tmp_path / 'photo.png'
    source.write_bytes(b'\x89PNG\r\n\x1a\nphoto')
    client = Client()
    key = 'photos/work_orders/2/date/existing.png'
    run(['work-order', 'complete', 'WO-2', '--last-mileage', '100',
         '--odometer-photo-path', str(source), '--work-photo-path', key], client)
    assert client.calls[0][2]['kind'] == 'work_order'
    assert client.calls[-1][2] == {'last_mileage': 100,
        'odometer_photo_path': 'photos/work_orders/2/date/photo.png', 'work_photo_path': key}
    assert len(client.puts) == 1


def test_custody_rejects_more_than_twelve_photos_before_upload(tmp_path):
    source = tmp_path / 'photo.png'
    source.write_bytes(b'photo')
    client = Client()
    with pytest.raises(UsageError):
        run(['vehicle', 'check-in', 'VAN-2', '--mileage', '100'] +
            ['--photo-file=' + str(source)] * 13, client)
    assert not client.calls


def test_customer_mcp_uploads_custody_file_inside_selected_folder(tmp_path):
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService
    source = tmp_path / 'photo.png'
    source.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic')
    client = Client()
    async def check():
        server = create_server(CustomerReadService(client), file_root=tmp_path)
        async with create_connected_server_and_client_session(server) as sdk:
            result = await sdk.call_tool('check_in_vehicle', {'vehicle_id': 'VAN-2',
                'mileage': 100, 'photo_file': ['photo.png']})
            assert not result.isError, result
    asyncio.run(check())
    assert client.calls[0][2]['kind'] == 'vehicle_checkout'
    assert client.calls[-1][2]['photos'][0]['storage_key'] == 'photos/vehicle_checkouts/2/date/photo.png'


@pytest.mark.parametrize('mode', ['secret', 'mismatch', 'symlink', 'directory', 'oversize'])
@pytest.mark.parametrize('option', ['--photo-file', '--odometer-photo-path', '--work-photo-path'])
def test_unsafe_photo_is_rejected_before_presign(tmp_path, mode, option):
    source = tmp_path / 'photo.png'
    source.write_bytes(b'PRIVATE' if mode == 'secret' else b'\xff\xd8\xffjpeg')
    if mode == 'symlink':
        source.unlink()
        secret = tmp_path / 'secret'
        secret.write_bytes(b'PRIVATE')
        source.symlink_to(secret)
    elif mode == 'directory':
        source.unlink()
        source.mkdir()
    elif mode == 'oversize':
        with source.open('wb') as stream:
            stream.truncate(50 * 1024 * 1024 + 1)
    client = Client()
    words = (['vehicle', 'check-in', 'VAN-2', '--mileage', '100'] if option == '--photo-file'
             else ['work-order', 'complete', 'WO-2', '--last-mileage', '100'])
    with pytest.raises(UsageError, match=' / '):
        run(words + [option, str(source)], client)
    assert not client.calls and not client.puts


@pytest.mark.parametrize('extra', [[], ['--evidence-mode', 'full_inspection'],
    ['--field', 'evidence_mode=invalid'], ['--field', 'mileage=-1']])
def test_custody_preconditions_reject_before_upload(tmp_path, extra):
    source = tmp_path / 'photo.png'
    source.write_bytes(b'\x89PNG\r\n\x1a\nphoto')
    client = Client()
    with pytest.raises(UsageError):
        run(['vehicle', 'check-out', 'VAN-2', '--vendor-workshop-id', '3',
             '--photo-file', str(source)] + extra, client)
    assert not client.calls and not client.puts


@pytest.mark.parametrize('suffix,data', [
    ('jpg', b'\xff\xd8\xffimage'), ('png', b'\x89PNG\r\n\x1a\nimage'),
    ('webp', b'RIFF\x10\x00\x00\x00WEBPVP8 image'),
    ('heic', b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1'),
    ('heif', b'\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00mif1msf1'),
])
def test_local_photo_detects_supported_image_bytes(tmp_path, suffix, data):
    from nova_cli_public.local_inputs import read_image
    source = tmp_path / ('photo.' + suffix)
    source.write_bytes(data)
    path, actual, mime = read_image(source)
    assert path == source and actual == data
    assert mime == 'image/' + ('jpeg' if suffix == 'jpg' else suffix)
