import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.reads import CustomerReadService


class Client:
    def __init__(self, receipt=None):
        self.calls = []
        self.receipt = receipt if receipt is not None else {'defect_id': 7, 'estimated_cost': 12.345, 'auto_approved': False, 'extra': 'kept'}

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.receipt


def test_cli_and_mcp_preserve_cost_request_and_native_receipt(monkeypatch):
    client = Client()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: client)
    args = cli.build_parser().parse_args(['defect', 'set-cost', 'FD-7', '--estimated-cost', '12.3450'])
    assert args.handler(args) is client.receipt
    assert CustomerReadService(client).run('set_defect_cost', {'defect_id': 'FD-7', 'estimated_cost': '12.3450'}) is client.receipt
    assert client.calls == [(('POST', '/defects/FD-7/cost'), {'json_body': {'estimated_cost': '12.3450'}})] * 2


@pytest.mark.parametrize('amount', [0, True, '0', '-1', 'NaN', 'Infinity', '1000000', ''])
def test_invalid_cost_never_reaches_transport(amount):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run('set_defect_cost', {'defect_id': 'FD-7', 'estimated_cost': amount})
    assert not client.calls


@pytest.mark.parametrize('change', [
    {'defect_id': 8}, {'defect_id': True}, {'auto_approved': 1},
    {'estimated_cost': None}, {'estimated_cost': True}, {'estimated_cost': []},
    {'estimated_cost': 'NaN'}, {'estimated_cost': float('inf')}, {'estimated_cost': '-1'},
])
def test_uncertain_receipt_is_unknown_without_retry(change):
    client = Client({'defect_id': 7, 'estimated_cost': '1', 'auto_approved': False, **change})
    with pytest.raises(ApiError, match='unknown') as error:
        CustomerReadService(client).run('set_defect_cost', {'defect_id': '7', 'estimated_cost': '1'})
    assert error.value.code == 'outcome_unknown'
    assert len(client.calls) == 1


@pytest.mark.parametrize('amount', ['0', 0, 0.0, '1000000.001', 1000000, 1.2345])
def test_native_cost_receipt_is_not_rounded_capped_or_compared_to_input(amount):
    client = Client({'defect_id': 7, 'estimated_cost': amount, 'auto_approved': True})
    assert CustomerReadService(client).run('set_defect_cost', {'defect_id': '7', 'estimated_cost': '1'}) is client.receipt
    assert len(client.calls) == 1


@pytest.mark.parametrize('status', [200, 401])
def test_cost_real_client_admission_and_no_auth_retry(status, monkeypatch):
    import io
    import json
    import urllib.error
    from email.message import Message

    from nova_cli_public.client import ApiClient
    from nova_cli_public.config import Profile
    from nova_cli_public.delegated import OPERATIONS

    receipt = {'defect_id': 7, 'estimated_cost': '12.345', 'auto_approved': False}
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            headers = Message()
            headers['Content-Type'] = 'application/json'
            if status == 401:
                raise urllib.error.HTTPError(request.full_url, status, 'denied', headers, io.BytesIO(b'{}'))
            response = io.BytesIO(json.dumps(receipt).encode())
            response.status, response.headers = status, headers
            return response
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=Opener())
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(client, 'refresh', lambda: pytest.fail('Cost mutation must not retry via refresh'))
    if status == 200:
        assert CustomerReadService(client).run('set_defect_cost', {'defect_id': 'FD-7', 'estimated_cost': '12.3450'}) == receipt
    else:
        with pytest.raises(ApiError) as error:
            CustomerReadService(client).run('set_defect_cost', {'defect_id': 'FD-7', 'estimated_cost': '12.3450'})
        assert error.value.status == 401
    assert 'defects.cost.set.v1' in OPERATIONS
    assert len(calls) == 1 and calls[0].method == 'POST'
    assert calls[0].full_url == 'https://nova.example/api/defects/FD-7/cost'
    assert json.loads(calls[0].data) == {'estimated_cost': '12.3450'}
