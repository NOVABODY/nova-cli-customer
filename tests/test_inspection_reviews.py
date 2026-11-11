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


@pytest.mark.parametrize('action,flags,tool,path,params', [
    ('queue', ['--status', 'completed', '--limit', '200', '--offset', '200'],
     'list_inspection_reviews', '/inspection-reviews/queue', {'status': 'completed', 'limit': 200, 'offset': 200}),
    ('feedback', ['--days', '60', '--limit', '50', '--offset', '100'],
     'list_inspection_review_feedback', '/inspection-reviews/feedback', {'days': 60, 'limit': 50, 'offset': 100}),
    ('quality', [], 'get_inspector_quality', '/inspection-reviews/quality', {'days': 30}),
])
def test_review_cli_forwards_filters_and_page(monkeypatch, action, flags, tool, path, params):
    api = SimpleNamespace(request=Mock(return_value={'items': [], 'total': 0}))
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['inspection-review', action, *flags])
    args.handler(args)
    api.request.assert_called_once_with('GET', path, params=params)
    schema = inspection_reviews.MODELS[tool].model_json_schema()['properties']
    assert schema.get('days', {}).get('default', 30) == 30
    if action != 'quality':
        assert schema['limit']['maximum'] == 200 and schema['offset']['minimum'] == 0


@pytest.mark.parametrize('tool,arguments', [
    ('list_inspection_reviews', {'limit': 201}),
    ('list_inspection_reviews', {'offset': -1}),
    ('list_inspection_review_feedback', {'limit': 0}),
    ('list_inspection_review_feedback', {'offset': -1}),
])
def test_invalid_review_page_does_not_reach_api(tool, arguments):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        inspection_reviews.execute(api, tool, arguments)
    api.request.assert_not_called()


def test_local_mcp_review_schema_exposes_pagination():
    api = SimpleNamespace(request=Mock(return_value={'items': [], 'total': 300}))

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            queue = tools['list_inspection_reviews'].inputSchema['properties']
            assert queue['limit']['maximum'] == 200
            assert queue['status']['enum'] == ['unreviewed', 'in_progress', 'completed', 'all']
            feedback = tools['list_inspection_review_feedback'].inputSchema['properties']
            assert feedback['days']['default'] == 30 and feedback['offset']['default'] == 0
            result = await sdk.call_tool('list_inspection_review_feedback', {'days': 60, 'limit': 50, 'offset': 100})
            assert not result.isError
    asyncio.run(check())
    api.request.assert_called_once_with('GET', '/inspection-reviews/feedback', params={'days': 60, 'limit': 50, 'offset': 100})
