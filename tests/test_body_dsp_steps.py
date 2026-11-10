from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from nova_cli_public import body_intake


@pytest.mark.parametrize('name,body', [
    ('select_body_repair_quote', {'quote_id': 'BRQ-9', 'grade': 4}),
    ('confirm_body_repair_pickup', {'van_location': 'Bay 2', 'key_location': 'Office', 'expected_version': 7}),
    ('accept_body_repair_pickup', {'expected_version': 7}),
])
def test_decision_sends_closed_body_once_with_version(name, body):
    result = {'id': 'BRR-7', 'order_number': 'TEST-7', 'status': 'pickup_scheduled'}
    api = SimpleNamespace(request=Mock(return_value=result))
    assert body_intake.execute(api, name, {'request_ref': 'BRR-7', **body}) == result
    suffix = {'select_body_repair_quote': 'select-quote', 'confirm_body_repair_pickup': 'confirm-pickup',
        'accept_body_repair_pickup': 'accept-pickup'}[name]
    api.request.assert_called_once_with('POST', '/body-repair/requests/BRR-7/' + suffix,
        json_body=body, retry_auth=False)
    assert 'use_referral_credit' not in api.request.call_args.kwargs['json_body']


@pytest.mark.parametrize('name,body', [
    ('select_body_repair_quote', {'quote_id': 9, 'use_referral_credit': True}),
    ('select_body_repair_quote', {'quote_id': 9, 'grade': True}),
    ('select_body_repair_quote', {'quote_id': 9, 'suggested_time': {'proposed_date': '2026-11-10', 'pickup_window': 'morning', 'reason': 'Available'}}),
    ('confirm_body_repair_pickup', {'van_location': 'Bay 2', 'key_location': 'Office'}),
    ('accept_body_repair_pickup', {'expected_version': 7, 'return_date': '2026-11-11'}),
])
def test_browser_only_or_invalid_fields_never_reach_api(name, body):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        body_intake.execute(api, name, {'request_ref': 'BRR-7', **body})
    api.request.assert_not_called()


@pytest.mark.parametrize('status,code', [(400, 'invalid_logistics'), (401, 'authentication_required'), (403, 'body_repair_denied'), (404, 'not_found'),
    (409, 'body_repair_conflict'), (422, 'invalid_arguments'), (503, 'body_repair_unavailable'), (500, 'outcome_unknown')])
def test_decision_error_retains_contract_and_does_not_retry(status, code):
    from nova_cli_public.errors import ApiError
    failure = ApiError('Refused', status=status, detail={'code': 'native_gate'})
    api = SimpleNamespace(request=Mock(side_effect=failure))
    with pytest.raises(ApiError) as caught:
        body_intake.execute(api, 'accept_body_repair_pickup', {'request_ref': 'BRR-7', 'expected_version': 7})
    assert api.request.call_count == 1
    if code is None:
        assert caught.value is failure
    else:
        assert caught.value.code == code
        assert '/' in str(caught.value)


def test_select_quote_preserves_all_optional_booking_fields():
    fields = {'quote_id': 9, 'grade': 5, 'scope': 'new_damage', 'pickup_report_id': 3,
        'pickup_details': {'van_location': 'Bay', 'key_location': 'Office', 'expected_version': 7,
            'address': 'Test depot', 'contact_name': 'Test', 'contact_phone': '555-0100', 'access_notes': 'Gate'},
        'suggested_time': {'proposed_date': '2026-11-10', 'pickup_window': '8:00am - 10:00am', 'reason': 'Available'}}
    api = SimpleNamespace(request=Mock(return_value={'id': 'BRR-7', 'order_number': 'TEST-7', 'status': 'pickup_proposed'}))
    body_intake.execute(api, 'select_body_repair_quote', {'request_ref': 'BRR-7', **fields})
    assert api.request.call_args.kwargs['json_body'] == fields


def test_missing_operation_consent_requires_new_connection():
    from nova_cli_public.errors import ApiError
    api = SimpleNamespace(request=Mock(side_effect=ApiError('private', status=403,
        detail={'code': 'operation_requires_consent'})))
    with pytest.raises(ApiError) as caught:
        body_intake.execute(api, 'accept_body_repair_pickup', {'request_ref': 'BRR-7', 'expected_version': 7})
    assert caught.value.code == 'connection_requires_consent'
    assert 'conexión nueva' in str(caught.value) and api.request.call_count == 1
