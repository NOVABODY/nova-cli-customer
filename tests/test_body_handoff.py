import pytest

from nova_cli_public.body_handoff import surface


@pytest.mark.parametrize('action,page', [('sign_off', 'report'), ('pay', 'pay')])
@pytest.mark.parametrize('listing', [False, True])
def test_browser_action_uses_web_origin_and_preserves_payment_url(action, page, listing):
    row = {'id': 'BRR-7', 'browser_action': {'action': action, 'url': '/body-repairs/public-token/' + page},
        'payment_url': None, 'other': 'kept'}
    value = {'items': [row], 'total': 1} if listing else row
    output = surface(value, 'https://nova.example/api')
    result = output['items'][0] if listing else output
    assert result['browser_action']['url'] == 'https://nova.example/body-repairs/public-token/' + page
    assert result['payment_url'] is None and result['other'] == 'kept'
    assert 'browser' in result['browser_guidance'] and 'navegador' in result['browser_guidance']
    assert row['browser_action']['url'].startswith('/')


def test_payment_url_is_retained_without_inventing_handoff():
    row = {'browser_action': None, 'payment_url': 'https://invoice.stripe.com/test'}
    result = surface(row, 'https://nova.example')
    assert result['browser_action'] is None and result['payment_url'] == row['payment_url']
    assert result['payment_link_label'] == 'Invoice or receipt / Factura o recibo'
    assert 'browser_guidance' not in result


@pytest.mark.parametrize('action', [
    {'action': 'pay', 'url': '//evil.example/pay'},
    {'action': 'pay', 'url': 'https://evil.example/pay'},
    {'action': 'pay', 'url': '/body-repairs/BRR-7/pay?token=secret'},
    {'action': 'unknown', 'url': '/body-repairs/token/pay'},
    {'action': 'pay', 'url': None}, 'invalid', [],
])
def test_invalid_handoff_keeps_row_and_other_list_items(action):
    row = {'id': 'BRR-7', 'browser_action': action, 'status': 'completed'}
    other = {'id': 'BRR-8', 'browser_action': None}
    result = surface({'items': [row, other], 'total': 2}, 'https://nova.example')
    assert result['items'][0]['browser_action'] is None
    assert result['items'][0]['status'] == 'completed'
    assert result['items'][0]['browser_guidance'] == 'Link not available. / Enlace no disponible.'
    assert result['items'][1] == other and result['total'] == 2
    assert row['browser_action'] == action


@pytest.mark.parametrize('url', ['http://invoice.example', 'javascript:alert(1)', '//invoice.example',
    'https://', 'https://[invalid', 'https://invoice.example:bad', 7])
def test_invalid_payment_link_is_removed(url):
    result = surface({'id': 'BRR-7', 'payment_url': url}, 'https://nova.example')
    assert result['payment_url'] is None and result['id'] == 'BRR-7'
    assert result['browser_guidance'] == 'Link not available. / Enlace no disponible.'


def test_paid_receipt_does_not_request_payment():
    result = surface({'payment_status': 'SUCCEEDED', 'browser_action': None,
        'payment_url': 'https://invoice.stripe.com/receipt'}, 'https://nova.example')
    assert result['payment_url'] == 'https://invoice.stripe.com/receipt'
    assert result['payment_link_label'] == 'Invoice or receipt / Factura o recibo'
    assert 'browser_guidance' not in result


@pytest.mark.parametrize('origin', [None, '', 'https://[invalid', 'https://web.example:bad'])
def test_missing_or_invalid_origin_omits_handoff(origin):
    result = surface({'browser_action': {'action': 'pay', 'url': '/body-repairs/token/pay'}}, origin)
    assert result['browser_action'] is None
    assert result['browser_guidance'] == 'Link not available. / Enlace no disponible.'



def test_cli_read_surfaces_browser_action_from_api(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from nova_cli_public import cli
    from nova_cli_public import legacy_reads as handlers
    value = {'id': 'BRR-7', 'browser_action': {'action': 'sign_off', 'url': '/body-repairs/token/report'}, 'payment_url': None}
    api = SimpleNamespace(request=Mock(return_value=value), profile=SimpleNamespace(api='https://nova.example/api'))
    monkeypatch.setattr(handlers, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['body-repair', 'get', 'BRR-7'])
    result = args.handler(args)
    assert result['browser_action']['url'] == 'https://nova.example/body-repairs/token/report'
    assert result['payment_url'] is None


def test_local_mcp_read_retains_browser_handoff():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from nova_cli_public.reads import CustomerReadService
    api = SimpleNamespace(request=Mock(return_value={'browser_action': {'action': 'pay', 'url': '/body-repairs/token/pay'}, 'payment_url': None}),
        profile=SimpleNamespace(api='https://nova.example/api'))
    result = CustomerReadService(api).run('get_body_repair_request', {'request_ref': 'BRR-7'})
    assert result['browser_action']['url'] == 'https://nova.example/body-repairs/token/pay'
