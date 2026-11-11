import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, inspection_reviews, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

ITEM = {'review_id': 4, 'observation_id': 8, 'verdict': 'invalid',
    'invalid_reason': 'not_present', 'expected_updated_at': '2026-11-11T12:00:00Z', 'comment': 'Checked photo.'}


def test_cli_and_mcp_share_verdict_payload_and_consent(monkeypatch):
    api = SimpleNamespace(request=Mock(return_value={'operational_effect': 'recorded_only'}))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['inspection-review', 'set', '4', '8', '--verdict', 'invalid',
        '--invalid-reason', 'not_present', '--expected-updated-at', ITEM['expected_updated_at'], '--comment', ITEM['comment']])
    args.handler(args)

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools['get_inspector_quality'].annotations.readOnlyHint
            assert not tools['set_inspection_review_item'].annotations.readOnlyHint
            result = await sdk.call_tool('set_inspection_review_item', ITEM)
            assert not result.isError and result.structuredContent == {'operational_effect': 'recorded_only'}
    asyncio.run(check())
    body = {key: value for key, value in ITEM.items() if key not in {'review_id', 'observation_id'}}
    assert api.request.call_args_list == [(('PUT', '/inspection-reviews/4/items/8'), {'json_body': body, 'retry_auth': False})] * 2
    entry = manifest(cli.build_parser(), 'inspection-review set')['commands'][0]
    assert entry['required_operation'] == 'inspection_reviews.items.set.v1'
    assert entry['required_scope'] == 'nova:read nova:write'


@pytest.mark.parametrize('changes', [{'review_id': '../bad'}, {'invalid_reason': None}, {'group_to': 'CMR'},
    {'expected_updated_at': '2026-11-11'}, {'private_note': 'secret'}])
def test_invalid_verdict_never_reaches_api(changes):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        inspection_reviews.execute(api, 'set_inspection_review_item', {**ITEM, **changes})
    api.request.assert_not_called()


def test_unknown_write_is_not_replayed():
    api = SimpleNamespace(request=Mock(side_effect=ApiError('unavailable', status=503)))
    with pytest.raises(ApiError) as error:
        inspection_reviews.execute(api, 'set_inspection_review_item', ITEM)
    assert error.value.code == 'outcome_unknown'
    assert api.request.call_count == 1
