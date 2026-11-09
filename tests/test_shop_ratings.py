"""Closed rating inputs fail before a write can reach the API."""
import pytest
from pydantic import ValidationError

from nova_cli_public.shop_ratings import MODELS


@pytest.mark.parametrize('name,values', [
    ('rate_work_order', {'work_order_id': 'WO-7', 'stars': 5}),
    ('rate_work_order', {'work_order_id': 'WO-7', 'vote': 'down'}),
    ('rate_work_order', {'work_order_id': 'WO-7', 'completion_decision': 'correction_requested'}),
    ('rate_work_order', {'work_order_id': 'WO-7', 'body_repair_request_id': 'BRR-7'}),
    ('rate_work_order', {'work_order_id': 'WO-0'}),
    ('rate_work_order', {'work_order_id': 7}),
    ('rate_work_order', {'work_order_id': 'WO-7', 'reason': 'x' * 1001}),
    ('request_work_order_correction', {'work_order_id': '7'}),
    ('request_work_order_correction', {'work_order_id': '7', 'reason': '  '}),
    ('request_work_order_correction', {'work_order_id': '7', 'reason': 'Fix', 'vote': 'up'}),
    ('rate_body_repair', {'body_repair_request_id': 'BRR-7', 'stars': True}),
    ('rate_body_repair', {'body_repair_request_id': 'BRR-7', 'stars': 6}),
    ('rate_body_repair', {'body_repair_request_id': 'BRR-7', 'stars': 5, 'escalate': False}),
    ('rate_body_repair', {'body_repair_request_id': 'BRR-7', 'stars': 5, 'tags': ['problem_repair_quality']}),
    ('rate_body_repair', {'body_repair_request_id': 'BRR-7', 'stars': 3, 'tags': ['good_communication']}),
    ('rate_body_repair', {'body_repair_request_id': 'BRR-7', 'stars': 4, 'tags': ['bad']}),
    ('rate_body_repair', {'body_repair_request_id': 'BRR-7', 'stars': 4, 'tags': ['good_communication'] * 2}),
])
def test_invalid_rating_has_bilingual_error(name, values):
    with pytest.raises(ValidationError, match=' / '):
        MODELS[name].model_validate(values)


@pytest.mark.parametrize('stars,tags', [(5, ['good_repair_quality']), (4, ['good_communication', 'problem_pickup_return']), (1, ['problem_van_condition']), (2, []), (3, [])])
def test_body_rating_accepts_native_star_tag_rules(stars, tags):
    value = MODELS['rate_body_repair'].model_validate({'body_repair_request_id': 'BRR-7', 'stars': stars, 'tags': tags, 'reason': 'x' * 1000})
    assert value.stars == stars and value.tags == tags


def test_correction_keeps_full_reason_and_matching_decision():
    value = MODELS['request_work_order_correction'].model_validate({'work_order_id': 'WO-7', 'reason': 'x' * 1000})
    assert value.vote == 'down' and value.completion_decision == 'correction_requested'
    assert len(value.reason) == 1000

CASES = [
    ('rate_work_order', 'rate-work-order', {'work_order_id': 'WO-7'}, []),
    ('request_work_order_correction', 'request-correction', {'work_order_id': 'WO-7', 'reason': 'Fix finish'}, ['--reason', 'Fix finish']),
    ('rate_body_repair', 'rate-body-repair', {'body_repair_request_id': 'BRR-7', 'stars': 4, 'tags': ['good_communication', 'problem_pickup_return']}, ['--stars', '4', '--tags', 'good_communication', '--tags', 'problem_pickup_return']),
]


def receipt(name):
    body = name == 'rate_body_repair'
    correction = name == 'request_work_order_correction'
    return {'id': 9, 'subject_kind': 'body_repair' if body else 'work_order',
        'work_order_id': None if body else 7, 'body_repair_request_id': 7 if body else None,
        'vote': None if body else 'down' if correction else 'up', 'stars': 4 if body else None,
        'tags': ['good_communication', 'problem_pickup_return'] if body else [],
        'completion_decision': 'not_applicable' if body else 'correction_requested' if correction else 'approved',
        'correction_reopened': correction, 'native_extension': {'preserved': True}}

import asyncio
from types import SimpleNamespace

from mcp.shared.memory import create_connected_server_and_client_session

from nova_cli_public import cli, shop_ratings
from nova_cli_public.errors import ApiError


class Api:
    profile = SimpleNamespace(auth='delegated')

    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


@pytest.mark.parametrize('name,action,values,flags', CASES)
def test_cli_and_sdk_send_exact_subject_and_keep_native_receipt(monkeypatch, name, action, values, flags):
    api = Api(receipt(name))
    from nova_cli_public import legacy_reads
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['vendor-scorecard', action, 'BRR-7' if name == 'rate_body_repair' else 'WO-7', *flags])
    assert args.handler(args) == receipt(name)

    async def check():
        from nova_cli_public.mcp import create_server
        from nova_cli_public.reads import CustomerReadService
        server = create_server(CustomerReadService(api))
        async with create_connected_server_and_client_session(server) as sdk:
            tools = {item.name: item for item in (await sdk.list_tools()).tools}
            assert set(shop_ratings.MODELS) <= tools.keys()
            assert not tools[name].annotations.readOnlyHint
            assert not tools[name].annotations.idempotentHint
            assert 'Confirm' in tools[name].description and shop_ratings.GRANTS[name] in tools[name].description
            result = await sdk.call_tool(name, values)
            assert not result.isError and result.structuredContent == receipt(name)
            before = len(api.calls)
            bad = await sdk.call_tool(name, {**values, 'unknown': True})
            assert bad.isError and len(api.calls) == before
    asyncio.run(check())
    assert len(api.calls) == 2
    for args, kwargs in api.calls:
        assert args == ('POST', '/vendor-scorecard/feedback')
        assert kwargs == {'json_body': shop_ratings.MODELS[name].model_validate(values).model_dump(exclude_none=True), 'retry_auth': False}


@pytest.mark.parametrize('status', [400, 401, 403, 404, 409, 422, 429, 503])
def test_rating_errors_are_bounded_bilingual_and_never_retried(status):
    api = Api(ApiError('PRIVATE', status=status))
    with pytest.raises(ApiError) as error:
        shop_ratings.execute(api, 'rate_work_order', {'work_order_id': '7'})
    assert error.value.status == status and 'PRIVATE' not in str(error.value)
    assert ' / ' in str(error.value) and len(api.calls) == 1


@pytest.mark.parametrize('value', [ApiError('PRIVATE'), ApiError('PRIVATE', status=502), {},
    {**receipt('rate_work_order'), 'work_order_id': 8},
    {**receipt('rate_work_order'), 'vote': 'down'},
    {**receipt('rate_work_order'), 'extra': float('nan')}])
def test_uncertain_receipt_requires_read_before_another_attempt(value):
    api = Api(value)
    with pytest.raises(ApiError) as error:
        shop_ratings.execute(api, 'rate_work_order', {'work_order_id': '7'})
    assert error.value.code == 'outcome_unknown' and len(api.calls) == 1


@pytest.mark.parametrize('name,action,values,flags', CASES)
def test_customer_inventory_reports_exact_write_grant_and_fixed_route(name, action, values, flags):
    from nova_cli_public.capabilities import manifest
    from nova_cli_public.write_routes import admitted_write

    capability = manifest(cli.build_parser(), 'vendor-scorecard ' + action)['commands'][0]
    assert capability['required_operation'] == shop_ratings.GRANTS[name]
    assert capability['required_scope'] == 'nova:read nova:write'
    assert capability['effects'] == ['remote_write']
    assert capability['api_routes'] == [{'method': 'POST', 'path_pattern': '/vendor-scorecard/feedback'}]
    assert admitted_write('POST', '/vendor-scorecard/feedback')
    assert not admitted_write('POST', '/vendor-scorecard/feedback/other')
