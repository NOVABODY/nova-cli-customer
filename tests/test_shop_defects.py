from types import SimpleNamespace

import pytest

from nova_cli_public import cli
from nova_cli_public.errors import ApiError
from nova_cli_public.shop_defects import execute


class Client:
    def __init__(self, result):
        self.result, self.calls = result, []
        self.profile = SimpleNamespace(auth='service')

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize('action,result', [
    ('accept', {'id': 'WO-00003', 'status': 'processing'}),
    ('reject', {'rejected_defect_ids': [7], 'declined_line_item_ids': [], 'total_amount': '0.00'}),
])
def test_defect_intake_cli_uses_only_defect_reference(monkeypatch, action, result):
    client = Client(result)
    monkeypatch.setattr(cli, 'client_from_args', lambda args: client)
    argv = ['defect', action, 'FD-7']
    if action == 'reject':
        argv += ['--reject-reason-code', 'already_completed_or_not_present']
    args = cli.build_parser().parse_args(argv)
    assert args.handler(args) == result
    assert client.calls[0][0] == ('POST', '/defects/FD-7/' + action)
    assert client.calls[0][1]['retry_auth'] is False
    assert 'defect_ids' not in client.calls[0][1]['json_body']


@pytest.mark.parametrize('result', [ApiError('timeout'), ApiError('failure', status=503), {}])
def test_unknown_intake_outcome_is_never_retried(result):
    client = Client(result)
    with pytest.raises(ApiError) as error:
        execute(client, 'accept_defect', {'defect_id': 'FD-7'})
    assert error.value.code == 'outcome_unknown'
    assert len(client.calls) == 1


@pytest.mark.parametrize('flag,expected', [(None, None), ('--reroute', True), ('--no-reroute', False)])
def test_decline_preserves_platform_reroute_policy(monkeypatch, flag, expected):
    client = Client({})
    monkeypatch.setattr(cli, 'client_from_args', lambda args: client)
    words = ['work-order', 'decline', 'WO-3', '--decline-reason-code', 'capacity_full']
    args = cli.build_parser().parse_args(words + ([flag] if flag else []))
    args.handler(args)
    body = client.calls[0][1]['json_body']
    assert body.get('reroute') is expected
    assert ('reroute' in body) is (expected is not None)


def test_defect_list_requests_available_findings(monkeypatch):
    client = Client({'items': [], 'total': 0})
    monkeypatch.setattr(cli, 'client_from_args', lambda args: client)
    args = cli.build_parser().parse_args(['defect', 'list'])
    args.handler(args)
    assert client.calls[0][1]['query']['include_available'] is True


def test_opportunity_command_requests_open_unaccepted_cmr_cnmr(monkeypatch):
    client = Client({'items': [], 'total': 0})
    monkeypatch.setattr(cli, 'client_from_args', lambda args: client)
    args = cli.build_parser().parse_args(['defect', 'opportunities'])
    args.handler(args)
    assert client.calls[0][0] == ('GET', '/defects')
    assert client.calls[0][1]['query']['opportunities_only'] is True


@pytest.mark.parametrize('name,arguments,value', [
    ('reject_defect', {'defect_id': 'FD-7', 'reject_reason_code': 'other'}, {'rejected_defect_ids': [7]}),
    ('list_defect_opportunities', {}, {'items': [], 'total': 0}),
])
def test_customer_mcp_dispatches_typed_shop_operations(name, arguments, value):
    from nova_cli_public.reads import CustomerReadService

    client = Client(value)
    assert CustomerReadService(client).run(name, arguments) == value
    assert len(client.calls) == 1
