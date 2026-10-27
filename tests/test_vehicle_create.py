import json

import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.reads import CustomerReadService

DATA = {'fleet_id': 'NEW1', 'vin': '1ftbr1c80mka12345', 'plate': 'NEW123', 'year': 2021,
        'make': 'Ford', 'model': 'Transit', 'dsp_id': 'DSP-1'}

class Client:
    def __init__(self):
        self.calls = []
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {'id': 'VAN-1', 'native': {'retained': True}}


def test_cli_and_mcp_create_use_same_closed_native_body(monkeypatch):
    client = Client()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    args = cli.build_parser().parse_args(['vehicle', 'create', '--data', json.dumps(DATA)])
    expected = {'id': 'VAN-1', 'native': {'retained': True}}
    assert args.handler(args) == expected
    assert CustomerReadService(client).run('create_vehicle', {'data': DATA}) == expected
    assert client.calls == [('POST', '/vehicles', {'json_body': DATA | {'vin': DATA['vin'].upper()}})] * 2


@pytest.mark.parametrize('data', [
    {k: v for k, v in DATA.items() if k != 'fleet_id'},
    DATA | {'unknown': True}, DATA | {'grounded': True},
    DATA | {'location': 'at_shop'}, DATA | {'expected_mileage': 0},
    DATA | {'dsp_id': 'DSP-0'}, DATA | {'mileage': -1},
    DATA | {'vin': 'I' * 17}, DATA | {'year': 1979}, DATA | {'plate': None},
])
def test_invalid_create_data_does_not_reach_server(data):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run('create_vehicle', {'data': data})
    assert not client.calls
