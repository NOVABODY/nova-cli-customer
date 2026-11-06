import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import body_intake, cli, legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

CASES = [
    ('body-repair create --data', 'create_body_repair_request', {'data': {'vehicle_id': 7, 'mode': 'text', 'text_description': 'Repair the panel.'}}, '/body-repair/requests', {'vehicle_id': 7, 'mode': 'text', 'text_description': 'Repair the panel.'}),
    ('body-repair add-inspection-link BRR-7 --text https://capture.paveapi.com/s/AMWT-ONE --phase pickup', 'add_body_repair_inspection_link', {'request_ref': 'BRR-7', 'text': 'https://capture.paveapi.com/s/AMWT-ONE', 'phase': 'pickup'}, '/body-repair/requests/BRR-7/inspection-links', {'text': 'https://capture.paveapi.com/s/AMWT-ONE', 'phase': 'pickup'}),
    ('body-repair replace-inspection-link BRR-7 --key AMWT-ONE --url https://capture.paveapi.com/s/AMWT-TWO', 'replace_body_repair_inspection_link', {'request_ref': 'BRR-7', 'key': 'AMWT-ONE', 'url': 'https://capture.paveapi.com/s/AMWT-TWO'}, '/body-repair/requests/BRR-7/inspection-links', {'key': 'AMWT-ONE', 'url': 'https://capture.paveapi.com/s/AMWT-TWO'}),
    ('body-repair request-inspection-link BRR-7 --phase pickup --create-from-launcher', 'request_body_repair_inspection_link', {'request_ref': 'BRR-7', 'phase': 'pickup', 'create_from_launcher': True}, '/body-repair/requests/BRR-7/request-inspection-link', {'phase': 'pickup', 'create_from_launcher': True}),
]
RESULT = {'id': 'BRR-7', 'order_number': 'TEST-7', 'status': 'pending_quotes', 'pickup_blob': {}}


@pytest.mark.parametrize('command,name,arguments,path,body', CASES)
def test_cli_and_mcp_expose_same_typed_write(monkeypatch, command, name, arguments, path, body):
    value = RESULT
    api = SimpleNamespace(request=Mock(return_value=value), profile=SimpleNamespace(auth='service'))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    words = command.split() + ([json.dumps(arguments['data'])] if name == 'create_body_repair_request' else [])
    args = cli.build_parser().parse_args(words)
    assert args.handler(args) == value
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert not tools[name].annotations.readOnlyHint and not tools[name].annotations.idempotentHint
            result = await sdk.call_tool(name, arguments)
            assert not result.isError and result.structuredContent == value
    asyncio.run(check())
    verb = 'PATCH' if name == 'replace_body_repair_inspection_link' else 'POST'
    assert api.request.call_args_list == [((verb, path), {'json_body': body, 'retry_auth': False})] * 2


@pytest.mark.parametrize('name,arguments', [
    ('create_body_repair_request', {'data': {'vehicle_id': 0}}),
    ('create_body_repair_request', {'data': {'vehicle_id': 7, 'unknown': True}}),
    ('create_body_repair_request', {'data': {'vehicle_id': 7, 'issues': [{'description': 'Panel', 'photo_storage_keys': ['x'] * 9}]}}),
    ('request_body_repair_inspection_link', {'request_ref': 'BRR-7', 'create_from_launcher': True, 'cancel_from_launcher': True}),
])
def test_invalid_arguments_never_reach_server(name, arguments):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        body_intake.execute(api, name, arguments)
    api.request.assert_not_called()


@pytest.mark.parametrize('failure', [None, {'id': 'BRR-7'}, ApiError('unavailable', status=503), ApiError('connection lost')])
def test_uncertain_write_does_not_retry_or_claim_success(failure):
    api = SimpleNamespace(request=Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure))
    with pytest.raises(ApiError) as error:
        body_intake.execute(api, 'create_body_repair_request', {'data': {'vehicle_id': 7, 'text_description': 'Panel'}})
    assert error.value.code == 'outcome_unknown'
    assert api.request.call_count == 1


@pytest.mark.parametrize('status', [401, 403, 409, 422, 429])
def test_business_and_authorization_refusals_are_preserved(status):
    failure = ApiError('Refused', status=status, detail={'code': 'specific_gate'})
    api = SimpleNamespace(request=Mock(side_effect=failure))
    with pytest.raises(ApiError) as error:
        body_intake.execute(api, 'create_body_repair_request', {'data': {'vehicle_id': 7, 'text_description': 'Panel'}})
    assert error.value is failure and api.request.call_count == 1
