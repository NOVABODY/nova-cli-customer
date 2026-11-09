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
