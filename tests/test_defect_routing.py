import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.read_routes import READ_ROUTES
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.write_routes import WRITE_ROUTES


class Client:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {'items': [], 'total': 0} if method == 'GET' else {'id': 'RR-7', 'status': 'open', 'work_order_ids': [8]}


@pytest.mark.parametrize('argv,tool,arguments,path,kwargs', [
    (['defect-routing', 'shops', '--vehicle-id', 'VAN-7', '--repair-type', 'mechanical', '--service-station-code', 'TEST1'],
     'list_defect_routing_shops', {'vehicle_id': 'VAN-7', 'repair_type': 'mechanical', 'service_station_code': 'TEST1'},
     '/vendor-workshops', {'query': {'vehicle_id': 'VAN-7', 'repair_type': 'mechanical', 'service_station_code': 'TEST1'}}),
    (['defect-routing', 'resume', 'RR-7', '--vendor-workshop-id', '3'],
     'route_repair_request', {'rr_id': 'RR-7', 'vendor_workshop_id': 3}, '/repair-requests/RR-7/route',
     {'query': {'mode': 'resume'}, 'json_body': {'vendor_workshop_id': 3}}),
])
def test_cli_and_mcp_share_native_routing(monkeypatch, argv, tool, arguments, path, kwargs):
    client = Client()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    args = cli.build_parser().parse_args(argv)
    args.handler(args)
    CustomerReadService(client).run(tool, arguments)
    assert client.calls == [('POST' if tool == 'route_repair_request' else 'GET', path, kwargs)] * 2


@pytest.mark.parametrize('tool,arguments', [
    ('route_repair_request', {'rr_id': 'RR-0', 'vendor_workshop_id': 3}),
    ('route_repair_request', {'rr_id': '../7', 'vendor_workshop_id': 3}),
    ('route_repair_request', {'rr_id': 'RR-7', 'vendor_workshop_id': 0}),
    ('route_repair_request', {'rr_id': 'RR-7', 'vendor_workshop_id': 3, 'force': True}),
    ('list_defect_routing_shops', {'vehicle_id': 'VAN-7', 'repair_type': 'unknown'}),
])
def test_invalid_routing_arguments_do_not_call_api(tool, arguments):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run(tool, arguments)
    assert not client.calls


def test_routing_uses_exact_operation_admission():
    assert READ_ROUTES[r'/vendor-workshops'] == 'vendor_workshops.list.v1'
    assert WRITE_ROUTES['POST', r'/repair-requests/(?:RR-)?[0-9]{1,14}/route'] == 'repair_requests.route.v1'


@pytest.mark.parametrize('value', [{'id': 'RR-8', 'status': 'open', 'work_order_ids': []}, {}])
def test_unmatched_route_receipt_is_unknown(monkeypatch, value):
    from nova_cli_public.errors import ApiError

    client = Client()
    def request(*args, **kwargs):
        client.calls.append((args, kwargs))
        return value
    monkeypatch.setattr(client, 'request', request)
    with pytest.raises(ApiError) as error:
        CustomerReadService(client).run('route_repair_request', {'rr_id': 'RR-7', 'vendor_workshop_id': 3})
    assert error.value.code == 'outcome_unknown' and len(client.calls) == 1
