import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

KEY = '12345678-1234-4234-8234-123456789abc'
QUOTE = {'id': 9, 'source': 'service_writer', 'vehicle_id': 2, 'status': 'submitted',
    'lines': [{'defect_id': 7, 'amount_cents': 1250, 'decision': None}], 'native_extension': True}
SUBMIT = {'vehicle_id': 'VAN-2', 'lines': [{'defect_id': 'FD-7', 'amount_cents': 1250}], 'idempotency_key': KEY}


@pytest.mark.parametrize('action,tool,values,path,result', [
    ('submit', 'submit_cmr_quote', SUBMIT, '/cmr-quotes', QUOTE),
    ('get', 'get_cmr_quote', {'quote_id': 9}, '/cmr-quotes/9', QUOTE),
    ('list', 'list_cmr_quotes', {'status': 'all', 'defect_ids': [7]}, '/cmr-quotes', {'rows': [QUOTE], 'count': 1}),
    ('withdraw', 'withdraw_cmr_quote', {'quote_id': 9, 'idempotency_key': KEY}, '/cmr-quotes/9/withdraw', {**QUOTE, 'status': 'withdrawn'}),
    ('dismiss', 'dismiss_cmr_quote_line', {'quote_id': 9, 'defect_id': 'FD-7', 'idempotency_key': KEY}, '/cmr-quotes/9/lines/7/dismiss',
     {**QUOTE, 'lines': [{**QUOTE['lines'][0], 'dismissed_at': '2026-11-11T00:00:00Z'}]}),
    ('decide', 'decide_cmr_quote_line', {'quote_id': 9, 'defect_id': 'FD-7', 'decision': 'approved', 'expected_amount_cents': 1250, 'idempotency_key': KEY},
     '/cmr-quotes/9/lines/7/decision', {**QUOTE, 'lines': [{**QUOTE['lines'][0], 'decision': 'approved'}]}),
])
def test_cli_and_mcp_send_the_same_quote_operation_once(monkeypatch, action, tool, values, path, result):
    from nova_cli_public import cmr_quotes
    api = SimpleNamespace(profile=SimpleNamespace(auth='service'), request=Mock(return_value=result))
    monkeypatch.setattr(cli, 'client_from_args', lambda args: api)
    argv = ['cmr-quote', action]
    if action == 'submit':
        argv += ['--data', json.dumps(values)]
    else:
        if 'quote_id' in values:
            argv.append(str(values['quote_id']))
        for key, value in values.items():
            if key != 'quote_id':
                argv += ['--' + key.replace('_', '-'), str(value[0] if isinstance(value, list) else value)]
    args = cli.build_parser().parse_args(argv)
    assert args.handler(args) == result
    async def check():
        server = create_server(CustomerReadService(api))
        async with create_connected_server_and_client_session(server) as sdk:
            tools = {t.name: t for t in (await sdk.list_tools()).tools}
            assert tools[tool].annotations.readOnlyHint is (tool not in cmr_quotes.WRITES)
            reply = await sdk.call_tool(tool, values)
            assert not reply.isError and reply.structuredContent == result
    asyncio.run(check())
    assert api.request.call_count == 2
    first, second = api.request.call_args_list
    assert first == second and first.args[1] == path
    if tool in cmr_quotes.WRITES:
        assert first.kwargs['retry_auth'] is False
        assert KEY in str(first.kwargs)
    if action == 'submit':
        assert first.kwargs['json_body'] == {'source': 'service_writer', 'vehicle_id': 2, 'lines': [{'defect_id': 7, 'amount_cents': 1250}]}
    if action == 'decide':
        assert first.kwargs['json_body'] == {'decision': 'approved', 'expected_amount_cents': 1250}


@pytest.mark.parametrize('change', [{'vehicle_id': True}, {'vehicle_id': 'VAN-0'}, {'lines': []},
    {'lines': [{'defect_id': 7, 'amount_cents': True}]}, {'idempotency_key': 'bad'}, {'force': True}])
def test_invalid_quote_never_reaches_transport(change):
    from nova_cli_public import cmr_quotes
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        cmr_quotes.execute(api, 'submit_cmr_quote', SUBMIT | change)
    api.request.assert_not_called()


@pytest.mark.parametrize('value', [ApiError('PRIVATE', status=503), ApiError('PRIVATE'),
    {**QUOTE, 'vehicle_id': 3}, {**QUOTE, 'lines': []}, None])
def test_unknown_quote_write_is_not_success_or_replayed(value):
    from nova_cli_public import cmr_quotes
    api = SimpleNamespace(request=Mock(side_effect=value) if isinstance(value, Exception) else Mock(return_value=value))
    with pytest.raises(ApiError) as error:
        cmr_quotes.execute(api, 'submit_cmr_quote', SUBMIT)
    assert error.value.code == 'outcome_unknown' and 'PRIVATE' not in str(error.value)
    assert api.request.call_count == 1


@pytest.mark.parametrize('status,code', [(403, 'forbidden'), (409, 'cmr_quote_amount_changed'), (422, 'payout_account_required')])
def test_quote_denials_and_conflicts_preserve_only_safe_codes(status, code):
    from nova_cli_public import cmr_quotes
    api = SimpleNamespace(request=Mock(side_effect=ApiError('PRIVATE', status=status, code=code)))
    with pytest.raises(ApiError) as error:
        cmr_quotes.execute(api, 'submit_cmr_quote', SUBMIT)
    assert error.value.status == status and error.value.code == code
    assert 'PRIVATE' not in str(error.value) and api.request.call_count == 1


def test_quote_transport_preserves_key_repeated_filters_and_status(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from nova_cli_public import cmr_quotes
    from nova_cli_public.client import ApiClient, Response
    from nova_cli_public.config import Profile
    api = ApiClient(Profile('audit', 'https://nova.example/api'), None)
    api.access_token = 'synthetic'
    send = Mock(return_value=Response(201, {}, QUOTE))
    monkeypatch.setattr(api, '_send', send)
    assert cmr_quotes.execute(api, 'submit_cmr_quote', SUBMIT) == QUOTE
    assert send.call_count == 1 and send.call_args.kwargs['headers']['Idempotency-Key'] == KEY
    assert send.call_args.kwargs['max_bytes'] == 2 * 1024 * 1024
    assert send.call_args.kwargs['headers']['Authorization'] == 'Bearer synthetic'
    assert parse_qs(urlsplit(api._url('/cmr-quotes', {'defect_ids': [7, 8]})).query)['defect_ids'] == ['7', '8']
    send.reset_mock()
    send.return_value = Response(202, {}, QUOTE)
    with pytest.raises(ApiError) as error:
        cmr_quotes.execute(api, 'submit_cmr_quote', SUBMIT)
    assert error.value.code == 'outcome_unknown' and send.call_count == 1


def test_quote_discovery_names_consent_and_does_not_admit_other_routes():
    from nova_cli_public.capabilities import manifest
    from nova_cli_public.read_routes import admitted_read
    from nova_cli_public.write_routes import admitted_write
    entry = manifest(cli.build_parser(), 'cmr-quote decide')['commands'][0]
    assert entry['required_operation'] == 'cmr_quotes.decide.v1'
    assert entry['required_scope'] == 'nova:read nova:write'
    assert entry['effects'] == ['remote_write']
    assert admitted_read('/cmr-quotes/9') and admitted_write('POST', '/cmr-quotes/9/lines/7/decision')
    assert not admitted_write('DELETE', '/cmr-quotes/9')
    assert not admitted_write('POST', '/cmr-quotes/9/collect-directly')
