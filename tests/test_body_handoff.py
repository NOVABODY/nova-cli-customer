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
    assert 'navegador' in result['browser_guidance']


@pytest.mark.parametrize('url', ['//evil.example/pay', 'https://evil.example/pay', '/body-repairs/BRR-7/pay?token=secret'])
def test_invalid_handoff_does_not_escape_nova_origin(url):
    with pytest.raises(ValueError):
        surface({'browser_action': {'action': 'pay', 'url': url}}, 'https://nova.example')


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
