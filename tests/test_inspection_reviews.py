import asyncio
import io
import json
import urllib.error
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, inspection_reviews, legacy_reads
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.read_routes import admitted_read
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.write_routes import admitted_write

ITEM = {'review_id': 4, 'observation_id': 8, 'verdict': 'invalid', 'invalid_reason': 'not_present', 'comment': 'Checked photo.'}
PREVIEW = {'token': 'tok-1', 'undecided': 0, 'blocking': [],
    'effects': [{'observation_id': 8, 'kind': 'withdraw_shop_request', 'shop_name': 'Westside Fleet Repair'},
                {'observation_id': 9, 'kind': 'comment', 'visibility': 'dsp_and_shop'}],
    'score': {'inspector_id': 5, 'inspector_name': 'Marcus Reed', 'before': None, 'after': 92.4}}
DONE = {'review': {'id': 4, 'status': 'completed'}, 'applied': PREVIEW['effects']}


def run_cli(monkeypatch, api, *argv):
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['inspection-review', *argv])
    return args.handler(args)


def call_tools(api, *calls):
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            return tools, [await sdk.call_tool(name, arguments) for name, arguments in calls]
    return asyncio.run(check())


def test_cli_and_mcp_share_the_draft_payload_and_consent(monkeypatch):
    api = SimpleNamespace(request=Mock(return_value={'observation_id': 8, 'verdict': 'invalid'}))
    run_cli(monkeypatch, api, 'set', '4', '8', '--verdict', 'invalid', '--invalid-reason', 'not_present', '--comment', ITEM['comment'])
    tools, [result] = call_tools(api, ('set_inspection_review_item', ITEM))
    assert not result.isError
    assert tools['get_inspector_quality'].annotations.readOnlyHint
    assert tools['preview_inspection_review'].annotations.readOnlyHint
    for name in ('set_inspection_review_item', 'unset_inspection_review_item', 'complete_inspection_review', 'mark_inspection_review_feedback_seen'):
        assert not tools[name].annotations.readOnlyHint and tools[name].annotations.destructiveHint
    assert 'draft' in tools['set_inspection_review_item'].description
    assert 'preview_token' in tools['complete_inspection_review'].inputSchema['required']
    body = {key: value for key, value in ITEM.items() if key not in {'review_id', 'observation_id'}}
    assert api.request.call_args_list == [(('PUT', '/inspection-reviews/4/items/8'), {'json_body': body, 'retry_auth': False})] * 2
    entry = manifest(cli.build_parser(), 'inspection-review set')['commands'][0]
    assert entry['required_operation'] == 'inspection_reviews.items.set.v1'
    assert entry['required_scope'] == 'nova:read nova:write'


@pytest.mark.parametrize('command,operation,scope,method', [
    ('inspection-review unset', 'inspection_reviews.items.clear.v1', 'nova:read nova:write', 'DELETE'),
    ('inspection-review preview', 'inspection_reviews.preview.get.v1', 'nova:read', 'GET'),
    ('inspection-review complete', 'inspection_reviews.complete.v1', 'nova:read nova:write', 'POST'),
    ('inspection-review feedback-summary', 'inspection_reviews.feedback.summary.get.v1', 'nova:read', 'GET'),
    ('inspection-review feedback-seen', 'inspection_reviews.feedback.seen.v1', 'nova:read nova:write', 'POST'),
])
def test_new_review_commands_declare_their_consent_and_route(command, operation, scope, method):
    entry = manifest(cli.build_parser(), command)['commands'][0]
    assert entry['required_operation'] == operation and entry['required_scope'] == scope
    assert [route['method'] for route in entry['api_routes']] == [method]


def test_new_review_routes_are_admitted():
    assert admitted_read('/inspection-reviews/4/completion-preview')
    assert admitted_read('/inspection-reviews/feedback/summary')
    assert admitted_write('DELETE', '/inspection-reviews/4/items/8')
    assert admitted_write('POST', '/inspection-reviews/feedback/12/seen')
    assert not admitted_write('DELETE', '/inspection-reviews/4')


def test_empty_comment_clears_and_missing_comment_keeps(monkeypatch):
    api = SimpleNamespace(request=Mock(return_value={}))
    run_cli(monkeypatch, api, 'set', '4', '8', '--verdict', 'confirmed', '--comment', '')
    run_cli(monkeypatch, api, 'set', '4', '8', '--verdict', 'confirmed')
    assert [call.kwargs['json_body'] for call in api.request.call_args_list] == [
        {'verdict': 'confirmed', 'comment': ''}, {'verdict': 'confirmed'}]


@pytest.mark.parametrize('changes', [{'review_id': '../bad'}, {'invalid_reason': None}, {'group_to': 'CMR'},
    {'comment': 'x' * 2001}, {'expected_updated_at': '2026-11-11T12:00:00Z'}, {'private_note': 'secret'}])
def test_invalid_verdict_never_reaches_api(changes):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        inspection_reviews.execute(api, 'set_inspection_review_item', {**ITEM, **changes})
    api.request.assert_not_called()


def test_unset_and_seen_accept_no_content(monkeypatch):
    api = SimpleNamespace(request=Mock(return_value=None))
    assert run_cli(monkeypatch, api, 'unset', '4', '8') == {'review_id': 4, 'observation_id': 8, 'verdict': None}
    assert run_cli(monkeypatch, api, 'feedback-seen', '12') == {'item_id': 12, 'seen': True}
    assert api.request.call_args_list == [(('DELETE', '/inspection-reviews/4/items/8'), {'retry_auth': False}),
        (('POST', '/inspection-reviews/feedback/12/seen'), {'retry_auth': False})]


def test_feedback_summary_through_cli_and_mcp(monkeypatch):
    summary = {'unseen_count': 2, 'latest': None, 'score': 91.0, 'band': 'good'}
    api = SimpleNamespace(request=Mock(return_value=summary))
    assert run_cli(monkeypatch, api, 'feedback-summary') == summary
    _, [result] = call_tools(api, ('get_inspection_review_feedback_summary', {}))
    assert result.structuredContent == summary
    assert api.request.call_args_list == [(('GET', '/inspection-reviews/feedback/summary'), {})] * 2


def test_preview_is_a_read(monkeypatch):
    api = SimpleNamespace(request=Mock(return_value=PREVIEW))
    assert run_cli(monkeypatch, api, 'preview', '4') == PREVIEW
    api.request.assert_called_once_with('GET', '/inspection-reviews/4/completion-preview', query={'confirm_remaining': 'false'})


def test_cli_complete_prints_effects_then_posts_the_preview_token(monkeypatch, capsys):
    api = SimpleNamespace(request=Mock(side_effect=[PREVIEW, DONE]))
    assert run_cli(monkeypatch, api, 'complete', '4', '--confirm-remaining') == DONE
    assert api.request.call_args_list == [
        (('GET', '/inspection-reviews/4/completion-preview'), {'query': {'confirm_remaining': 'true'}}),
        (('POST', '/inspection-reviews/4/complete'), {'json_body': {'confirm_remaining': True, 'preview_token': 'tok-1'}, 'retry_auth': False})]
    printed = capsys.readouterr().err
    assert 'Westside Fleet Repair' in printed and 'dsp_and_shop' in printed and '- -> 92.4' in printed


def test_cli_complete_with_a_seen_token_skips_the_fetch(monkeypatch):
    api = SimpleNamespace(request=Mock(return_value=DONE))
    run_cli(monkeypatch, api, 'complete', '4', '--preview-token', 'tok-1')
    api.request.assert_called_once_with('POST', '/inspection-reviews/4/complete',
        json_body={'confirm_remaining': False, 'preview_token': 'tok-1'}, retry_auth=False)


@pytest.mark.parametrize('code,expected', [('undecided', 'inspection_review_undecided'), ('recategorize_not_allowed', 'inspection_review_blocked')])
def test_cli_complete_stops_before_posting_when_blocked(monkeypatch, code, expected):
    api = SimpleNamespace(request=Mock(return_value={**PREVIEW, 'blocking': [{'observation_id': 9, 'code': code}]}))
    with pytest.raises(ApiError) as error:
        run_cli(monkeypatch, api, 'complete', '4')
    assert error.value.code == expected and api.request.call_count == 1


def test_stale_preview_shows_fresh_effects_and_never_retries(monkeypatch):
    fresh = {**PREVIEW, 'token': 'tok-2', 'effects': [{'observation_id': 8, 'kind': 'score_only_invalid'}]}
    stale = ApiError('stale', status=409, code='inspection_review_preview_stale',
        detail={'code': 'inspection_review_preview_stale', 'preview': fresh})
    api = SimpleNamespace(request=Mock(side_effect=[PREVIEW, stale]))
    with pytest.raises(ApiError) as error:
        run_cli(monkeypatch, api, 'complete', '4')
    assert error.value.code == 'inspection_review_preview_stale' and 'not valid, score only' in str(error.value)
    assert 'token' not in error.value.detail['preview'] and api.request.call_count == 2


def test_mcp_stale_and_undecided_completion_explain_the_fix():
    fresh = {**PREVIEW, 'token': 'tok-2'}
    api = SimpleNamespace(request=Mock(side_effect=[
        ApiError('stale', status=409, code='inspection_review_preview_stale', detail={'preview': fresh}),
        ApiError('undecided', status=409, code='inspection_review_undecided')]))
    complete = ('complete_inspection_review', {'review_id': 4, 'preview_token': 'tok-1'})
    _, [stale, undecided] = call_tools(api, complete, complete)
    assert stale.isError and stale.structuredContent['error']['code'] == 'inspection_review_preview_stale'
    assert stale.structuredContent['error']['detail']['preview']['effects'] == PREVIEW['effects']
    assert 'tok-2' not in json.dumps(stale.structuredContent) + stale.content[0].text
    assert undecided.isError and 'confirm_remaining' in undecided.content[0].text
    assert api.request.call_count == 2


def test_mcp_completion_requires_a_preview_token():
    api = SimpleNamespace(request=Mock())
    _, results = call_tools(api, ('complete_inspection_review', {'review_id': 4}),
        ('complete_inspection_review', {'review_id': 4, 'preview_token': ''}))
    assert all(result.isError for result in results)
    api.request.assert_not_called()


@pytest.mark.parametrize('name,arguments', [('set_inspection_review_item', ITEM),
    ('complete_inspection_review', {'review_id': 4, 'preview_token': 'tok-1'}),
    ('unset_inspection_review_item', {'review_id': 4, 'observation_id': 8}),
    ('mark_inspection_review_feedback_seen', {'item_id': 12})])
def test_unknown_write_is_not_replayed(name, arguments):
    api = SimpleNamespace(request=Mock(side_effect=ApiError('unavailable', status=503)))
    with pytest.raises(ApiError) as error:
        inspection_reviews.execute(api, name, arguments)
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
    run_cli(monkeypatch, api, action, *flags)
    api.request.assert_called_once_with('GET', path, query=params)
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
    tools, [result] = call_tools(api, ('list_inspection_review_feedback', {'days': 60, 'limit': 50, 'offset': 100}))
    queue = tools['list_inspection_reviews'].inputSchema['properties']
    assert queue['limit']['maximum'] == 200
    assert queue['status']['enum'] == ['unreviewed', 'in_progress', 'completed', 'all']
    feedback = tools['list_inspection_review_feedback'].inputSchema['properties']
    assert feedback['days']['default'] == 30 and feedback['offset']['default'] == 0
    assert not result.isError
    api.request.assert_called_once_with('GET', '/inspection-reviews/feedback', query={'days': 60, 'limit': 50, 'offset': 100})


class Opener:
    """Real urllib transport: one JSON reply per request, HTTP errors raised."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def open(self, request, timeout):
        self.calls.append(request)
        status, body = self.replies.pop(0)
        headers = Message()
        headers['Content-Type'] = 'application/json'
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, '', headers, io.BytesIO(json.dumps(body).encode()))
        response = io.BytesIO(json.dumps(body).encode())
        response.status, response.headers = status, headers
        return response


def test_real_client_sends_query_and_reads_the_stale_body():
    from nova_cli_public.client import ApiClient
    from nova_cli_public.config import Profile

    opener = Opener((200, {'items': [], 'total': 0}),
        (409, {'detail': {'code': 'inspection_review_preview_stale', 'preview': {**PREVIEW, 'token': 'tok-2'}}}))
    client = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    client.access_token = 'synthetic-access'
    inspection_reviews.execute(client, 'list_inspection_reviews', {'status': 'in_progress', 'limit': 5})
    with pytest.raises(ApiError) as error:
        inspection_reviews.execute(client, 'complete_inspection_review', {'review_id': 4, 'preview_token': 'tok-1'})
    assert opener.calls[0].full_url == 'https://nova.example/api/inspection-reviews/queue?status=in_progress&limit=5&offset=0'
    assert json.loads(opener.calls[1].data) == {'confirm_remaining': False, 'preview_token': 'tok-1'}
    assert error.value.detail['preview']['effects'] == PREVIEW['effects'] and len(opener.calls) == 2
