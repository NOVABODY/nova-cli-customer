import io
import json
from email.message import Message

import pytest

from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.reads import CustomerReadService


@pytest.mark.parametrize('status', ['cancelled', 'fulfilled', 'open', 'accepted', 'stale'])
def test_native_cancel_preserves_terminal_receipt_and_posts_once(status, monkeypatch):
    value = {'id': 'RR-7', 'status': status, 'work_order_ids': [8], 'native': True}
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            response = io.BytesIO(json.dumps(value).encode())
            response.status, response.headers = 200, Message()
            response.headers['Content-Type'] = 'application/json'
            return response
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=Opener())
    client.access_token = 'synthetic-access'
    monkeypatch.setattr(client, 'refresh', lambda: pytest.fail('Do not retry cancellation'))
    assert CustomerReadService(client).run('cancel_repair_request', {'rr_id': 'RR-7', 'reason': ' Done '}) == value
    assert len(calls) == 1 and calls[0].method == 'POST'
    assert calls[0].full_url == 'https://nova.example/api/repair-requests/RR-7/cancel'
    assert json.loads(calls[0].data) == {'reason': 'Done'}


@pytest.mark.parametrize('args', [{'rr_id': 'RR-0'}, {'rr_id': 'RR-7', 'reason': 'x' * 501}, {'rr_id': 'RR-7', 'reason': False}, {'rr_id': 'RR-7', 'force': True}])
def test_cancel_input_is_closed_and_bounded(args):
    from pydantic import ValidationError

    from nova_cli_public.repair_cancel import Cancel
    with pytest.raises(ValidationError):
        Cancel(**args)

@pytest.mark.parametrize('value', [{'id': 'RR-8', 'status': 'cancelled'}, {'id': 'RR-7', 'status': 'unknown'}, {'id': 'RR-7', 'status': 'cancelled', 'bad': float('nan')}])
def test_cancel_malformed_receipt_is_unknown(monkeypatch, value):
    from nova_cli_public import legacy_reads
    from nova_cli_public.errors import ApiError
    class Client:
        def request(self, *args, **kwargs):
            return value
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: Client())
    with pytest.raises(ApiError) as error:
        CustomerReadService(Client()).run('cancel_repair_request', {'rr_id': 'RR-7'})
    assert error.value.code == 'outcome_unknown'
