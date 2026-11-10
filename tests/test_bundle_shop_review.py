"""Regression coverage for shop-step review findings."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from nova_cli_public import bundle_shop_steps as steps
from nova_cli_public import bundle_workflow


@pytest.mark.parametrize('field,value', [
    ('start', 1794477600), ('end', 1794484800),
    ('start', '1794477600'), ('start', '2026-11-12T10:00:00'),
    ('estimated_return_date', '2026-11-14T00:00:00Z'),
    ('estimated_return_date', 1794614400),
])
def test_pickup_rejects_non_iso_dates(field, value):
    with pytest.raises(ValidationError):
        steps.Pickup.model_validate({'ref': 'B-1', 'unit': 1,
            'start': '2026-11-12T10:00:00Z', 'end': '2026-11-12T12:00:00Z', field: value})


@pytest.mark.parametrize('url', [
    'https://foreign.example/bundle-offers/B-1',
    'http://app.example/bundle-offers/B-1',
    'javascript:alert(1)',
    'https://user@app.example/bundle-offers/B-1',
    'https://app.example/bundle-offers/B-2',
    'https://app.example/other/B-1',
    'https://app.example:0/bundle-offers/B-1',
    'https://app.example/bundle-offers/B-1\n',
])
def test_untrusted_browser_links_are_dropped(url):
    value = bundle_workflow.safe_browser_urls({'vans': [{'browser_url': url}]}, 'https://app.example', 'B-1')
    van = value['vans'][0]
    assert 'browser_url' not in van
    assert 'Browser link' in van['browser_url_note'] and 'enlace' in van['browser_url_note']


def test_configured_origin_bundle_link_is_preserved():
    value = {'vans': [{'browser_url': 'https://app.example/bundle-offers/B-1?van=2'}]}
    assert bundle_workflow.safe_browser_urls(value, 'https://app.example', 'B-1') == value


@pytest.mark.parametrize('upload', [False, True])
def test_auth_failure_after_confirmed_write_keeps_success(upload):
    from unittest.mock import Mock

    from nova_cli_public.capacity_evidence import execute
    from nova_cli_public.errors import AuthError
    receipt = {'id': 1, 'review_state': 'unreviewed'} if upload else {'status': 'requested'}
    client = SimpleNamespace(request=Mock(side_effect=[receipt, AuthError('expired')]))
    if upload:
        value = execute(client, 'upload_capacity_evidence', {'ref': 'B-1', 'unit': 1,
            'kind': 'authorization', 'authorization_number': 'FMC-1',
            'content_type': 'application/pdf', 'content_base64': 'JVBERi0='})
    else:
        value = steps.execute(client, steps.CONTACT, {'ref': 'B-1', 'unit': 1})
    assert value.items() >= receipt.items()
    assert value['refresh_required'] and 'Read the vans' in value['message']
    assert client.request.call_count == 2


@pytest.mark.parametrize('name,body', [
    ('list_bundle_offers', {'rows': [{'ref': 'B-1', 'status': 'open', 'total_price_cents': 0}]}),
    ('get_bundle_offer_report', {'ref': 'B-1', 'status': 'open', 'report': None}),
    ('list_bought_bundle_vans', {'vans': [{'unit': 1, 'state': 'approved', 'workflow': {
        'step': 3, 'action': 'book_pickup', 'owner': 'shop', 'group': 'action_required', 'deadline': None}}]}),
])
def test_workflow_reads_strip_unsafe_links(name, body):
    from unittest.mock import Mock
    row = body.get('rows', body.get('vans', [body]))[0]
    row['browser_url'] = 'https://foreign.example/bundle-offers/B-1'
    client = SimpleNamespace(profile=SimpleNamespace(api='https://app.example/api'), request=Mock(return_value=body))
    result = bundle_workflow.execute(client, name, {} if name == 'list_bundle_offers' else {'ref': 'B-1'})
    assert 'foreign.example' not in str(result)
    assert 'browser_url_note' in str(result)


def test_failed_refresh_cannot_return_unsafe_receipt_link():
    from unittest.mock import Mock

    from nova_cli_public.errors import AuthError
    client = SimpleNamespace(profile=SimpleNamespace(api='https://app.example/api'), request=Mock(side_effect=AuthError('expired')))
    value = steps.refresh(client, 'B-1', {'status': 'requested', 'browser_url': 'javascript:alert(1)'})
    assert value['status'] == 'requested' and value['refresh_required']
    assert 'browser_url' not in value and 'browser_url_note' in value
