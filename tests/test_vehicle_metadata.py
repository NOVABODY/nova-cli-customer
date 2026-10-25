import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.reads import CustomerReadService


class Client:
    def __init__(self):
        self.calls = []
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {'id': 'VAN-1', 'extra': {'retained': True}}

@pytest.mark.parametrize('argv,tool,arguments,expected_request', [
    (['vehicle', 'decode-vin', '1ftbr1c80mka12345'], 'decode_vehicle_vin', {'vin': '1ftbr1c80mka12345'}, ('GET', '/vehicles/decode-vin/1FTBR1C80MKA12345', {})),
    (['vehicle', 'decode-vin', '1FTBR1C80MKA12345'], 'decode_vehicle_vin', {'vin': '1FTBR1C80MKA12345'}, ('GET', '/vehicles/decode-vin/1FTBR1C80MKA12345', {})),
    (['vehicle', 'update', 'VAN-1', '--data', '{"location":"offsite"}'], 'update_vehicle', {'vehicle_id': 'VAN-1', 'data': {'location': 'offsite'}}, ('PATCH', '/vehicles/VAN-1', {'json_body': {'location': 'offsite'}})),
    (['vehicle', 'update', 'VAN-1', '--data', '{"dsp_id":"DSP-1"}'], 'update_vehicle', {'vehicle_id': 'VAN-1', 'data': {'dsp_id': 'DSP-1'}}, ('PATCH', '/vehicles/VAN-1', {'json_body': {'dsp_id': 'DSP-1'}})),
    (['vehicle', 'update', 'VAN-1', '--data', '{"grounded":false,"fmc":null,"mileage":0}'], 'update_vehicle', {'vehicle_id': 'VAN-1', 'data': {'grounded': False, 'fmc': None, 'mileage': 0}}, ('PATCH', '/vehicles/VAN-1', {'json_body': {'grounded': False, 'fmc': None, 'mileage': 0}})),
])
def test_cli_mcp_preserve_native_requests_and_responses(monkeypatch, argv, tool, arguments, expected_request):
    client = Client()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    args = cli.build_parser().parse_args(argv)
    expected = {'id': 'VAN-1', 'extra': {'retained': True}}
    assert args.handler(args) == expected
    assert CustomerReadService(client).run(tool, arguments) == expected
    assert client.calls == [expected_request] * 2

@pytest.mark.parametrize('tool,arguments', [
    ('decode_vehicle_vin', {'vin': '../escape'}),
    ('decode_vehicle_vin', {'vin': 'I' * 17}),
    ('update_vehicle', {'vehicle_id': 'VAN-0', 'data': {'plate': 'A'}}),
    ('update_vehicle', {'vehicle_id': 'VAN-2147483648', 'data': {'plate': 'A'}}),
    ('update_vehicle', {'vehicle_id': 'VAN-1', 'data': {}}),
    ('update_vehicle', {'vehicle_id': 'VAN-1', 'data': {'location': 'at_shop'}}),
    ('update_vehicle', {'vehicle_id': 'VAN-1', 'data': {'mileage': -1}}),
    ('update_vehicle', {'vehicle_id': 'VAN-1', 'data': {'plate': 'a' * 21}}),
    ('update_vehicle', {'vehicle_id': 'VAN-1', 'data': {'unknown': True}}),
])
def test_invalid_metadata_never_reaches_transport(tool, arguments):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run(tool, arguments)
    assert not client.calls
