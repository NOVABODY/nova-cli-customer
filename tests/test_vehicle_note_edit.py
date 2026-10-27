import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.reads import CustomerReadService


class Client:
    def __init__(self):
        self.calls = []
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return None if method == 'DELETE' else {'id': 3, 'vehicle_id': 7, 'body': 'Fixed'}

@pytest.mark.parametrize('action,tool,args,body', [
    ('update-note', 'update_vehicle_note', {'vehicle_id': 'VAN-7', 'note_id': 3, 'body': ' Fixed '}, {'body': 'Fixed'}),
    ('delete-note', 'delete_vehicle_note', {'vehicle_id': 'VAN-7', 'note_id': 3}, None),
])
def test_cli_and_mcp_use_native_note_operation(monkeypatch, action, tool, args, body):
    client = Client()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    argv = ['vehicle', action, 'VAN-7', '3'] + (['--body', args['body']] if body else [])
    parsed = cli.build_parser().parse_args(argv)
    parsed.handler(parsed)
    CustomerReadService(client).run(tool, args)
    assert client.calls == [('PATCH' if body else 'DELETE', '/vehicles/VAN-7/notes/3', {'json_body': body} if body else {})] * 2

@pytest.mark.parametrize('args', [
    {'vehicle_id': 'VAN-0', 'note_id': 3, 'body': 'Fixed'},
    {'vehicle_id': 'VAN-7', 'note_id': 0, 'body': 'Fixed'},
    {'vehicle_id': 'VAN-7', 'note_id': 3, 'body': '  '},
    {'vehicle_id': 'VAN-7', 'note_id': 3, 'body': 'x' * 2001},
    {'vehicle_id': 'VAN-7', 'note_id': 3, 'body': 'Fixed', 'author_id': 8},
])
def test_invalid_note_edit_cannot_call_business_api(args):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run('update_vehicle_note', args)
    assert not client.calls


def test_note_list_supports_native_page_limit(monkeypatch):
    client = Client()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    args = cli.build_parser().parse_args(['vehicle', 'list-notes', 'VAN-7', '--limit', '200'])
    args.handler(args)
    CustomerReadService(client).run('list_vehicle_notes', {'vehicle_id': 'VAN-7', 'limit': 200})
    assert client.calls == [('GET', '/vehicles/VAN-7/notes', {'query': {'limit': 200}})] * 2
    with pytest.raises(ValidationError):
        CustomerReadService(client).run('list_vehicle_notes', {'vehicle_id': 'VAN-7', 'limit': 201})


@pytest.mark.parametrize('tool,args,method,status,payload', [
    ('update_vehicle_note', {'vehicle_id': 'VAN-7', 'note_id': 3, 'body': 'Fixed'}, 'PATCH', 200, b'{"id":3,"vehicle_id":7,"body":"Fixed"}'),
    ('delete_vehicle_note', {'vehicle_id': 'VAN-7', 'note_id': 3}, 'DELETE', 204, b''),
])
def test_real_client_admits_native_note_write(tool, args, method, status, payload, monkeypatch):
    import io
    from email.message import Message

    from nova_cli_public.client import ApiClient
    from nova_cli_public.config import Profile
    from nova_cli_public.delegated import OPERATIONS
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            response = io.BytesIO(payload)
            response.status, response.headers = status, Message()
            response.headers['Content-Type'] = 'application/json'
            return response
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=Opener())
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(client, 'refresh', lambda: pytest.fail('Do not retry a note mutation'))
    result = CustomerReadService(client).run(tool, args)
    assert result == ({'items': None} if status == 204 else {'id': 3, 'vehicle_id': 7, 'body': 'Fixed'})
    assert len(calls) == 1 and calls[0].method == method
    assert calls[0].full_url == 'https://nova.example/api/vehicles/VAN-7/notes/3'
    assert ('vehicles.notes.update.v1' if method == 'PATCH' else 'vehicles.notes.delete.v1') in OPERATIONS
