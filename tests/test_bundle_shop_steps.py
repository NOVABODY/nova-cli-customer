from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from nova_cli_public import bundle_shop_steps as steps
from nova_cli_public.errors import ApiError, UsageError

VANS = {'vans': []}


@pytest.mark.parametrize('name,payload,suffix,result', [
    ('update_bundle_pickup', {'start': '2026-11-12T10:00:00Z', 'end': '2026-11-12T12:00:00Z', 'estimated_return_date': '2026-11-14'}, 'pickup', {'tasks': []}),
    ('confirm_bundle_no_charge', {}, 'confirm-no-charge', {'state': 'lapsed'}),
    ('request_bundle_contact', {}, 'contact', {'status': 'already_requested'}),
])
def test_fixed_write_and_refresh_without_payment(name, payload, suffix, result):
    client = SimpleNamespace(request=Mock(side_effect=[result, VANS]))
    value = steps.execute(client, name, {'ref': 'B-1', 'unit': 2, **payload})
    assert value == {**result, **VANS}
    calls = client.request.call_args_list
    assert calls[0].args == ('POST', '/bundle-offers/B-1/vans/2/' + suffix)
    assert calls[0].kwargs == {'retry_auth': False, **({'json_body': payload} if payload else {})}
    assert calls[1].args == ('GET', '/bundle-offers/B-1/vans')


@pytest.mark.parametrize('status', [401, 403, 404, 409, 413, 422])
def test_refusals_preserve_detail_and_never_retry(status):
    detail = {'message': 'Este paso no está disponible.'}
    client = SimpleNamespace(request=Mock(side_effect=ApiError('refused', status=status, code='conflict', detail=detail)))
    with pytest.raises(ApiError) as error:
        steps.execute(client, 'confirm_bundle_no_charge', {'ref': 'B-1', 'unit': 1})
    assert error.value.detail == detail and error.value.status == status
    assert client.request.call_count == 1


@pytest.mark.parametrize('value', [None, {}, {'status': 'sent'}])
def test_uncertain_write_never_retries(value):
    client = SimpleNamespace(request=Mock(return_value=value))
    with pytest.raises(ApiError, match='outcome|resultado') as error:
        steps.execute(client, 'request_bundle_contact', {'ref': 'B-1', 'unit': 1})
    assert error.value.code == 'outcome_unknown' and client.request.call_count == 1


def test_refresh_failure_keeps_confirmed_receipt():
    client = SimpleNamespace(request=Mock(side_effect=[{'status': 'requested'}, ApiError('offline')]))
    value = steps.execute(client, 'request_bundle_contact', {'ref': 'B-1', 'unit': 1})
    assert value['status'] == 'requested' and value['refresh_required']
    assert client.request.call_count == 2


@pytest.mark.parametrize('arguments', [{'ref': '../x', 'unit': 1}, {'ref': 'B-1', 'unit': 0}, {'ref': 'B-1', 'unit': 1, 'payment': True}])
def test_bad_input_cannot_select_route(arguments):
    client = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        steps.execute(client, 'confirm_bundle_no_charge', arguments)
    client.request.assert_not_called()


def test_pickup_requires_ordered_aware_window():
    with pytest.raises(ValidationError):
        steps.MODELS['update_bundle_pickup'].model_validate({'ref': 'B-1', 'unit': 1,
            'start': '2026-11-12T12:00:00Z', 'end': '2026-11-12T10:00:00Z'})


def test_authorization_upload_keeps_number_and_file():
    from nova_cli_public.capacity_evidence import execute
    payload = {'ref': 'B-1', 'unit': 1, 'kind': 'authorization', 'authorization_number': 'FMC-42',
        'content_type': 'application/pdf', 'content_base64': 'JVBERi0='}
    client = SimpleNamespace(request=Mock(return_value={'id': 1, 'review_state': 'unreviewed'}))
    execute(client, 'upload_capacity_evidence', payload)
    assert client.request.call_args_list[0].args == ('POST', '/bundle-offers/B-1/vans/1/evidence-content')
    assert client.request.call_args_list[0].kwargs['json_body']['authorization_number'] == 'FMC-42'
    assert client.request.call_args_list[0].kwargs['json_body']['content_base64'] == 'JVBERi0='


def test_pdf_route_is_admitted_but_payment_writes_are_not():
    from nova_cli_public.client import _pdf_target
    _pdf_target('GET', '/bundle-offers/B-1/vans/1/fmc.pdf', None, None, None)
    for suffix in ('readiness', 'accept', 'payment', 'update-payment'):
        with pytest.raises(UsageError):
            _pdf_target('POST', '/bundle-offers/B-1/vans/1/' + suffix, None, None, None)


def test_browser_only_actions_keep_exact_api_links():
    from nova_cli_public.bundle_workflow import execute
    link = 'https://app.example/bundle-offers/B-1?van=2'
    van = {'unit': 2, 'state': 'approved', 'browser_url': link, 'workflow': {
        'step': 3, 'action': 'book_pickup', 'owner': 'shop', 'group': 'action_required', 'deadline': None}}
    client = SimpleNamespace(profile=SimpleNamespace(api='https://app.example/api'), request=Mock(return_value={'vans': [van]}))
    assert execute(client, 'list_bought_bundle_vans', {'ref': 'B-1'})['vans'][0]['browser_url'] == link
    assert 'browser_url' in steps.BROWSER and 'Abre' in steps.BROWSER


def test_cli_and_local_mcp_dispatch_all_steps_and_pdf(monkeypatch, tmp_path):
    import asyncio
    import base64

    from mcp.shared.memory import create_connected_server_and_client_session

    class Api:
        profile = SimpleNamespace(auth='service')
        def __init__(self):
            self.calls = []
        def request(self, method, path, **options):
            self.calls.append((method, path, options))
            if path.endswith('/fmc.pdf'):
                return b'%PDF-1.4\nsynthetic\n%%EOF'
            if method == 'GET':
                return VANS
            if path.endswith('/reject'):
                return {'ref': 'B-1', 'rejected': True}
            return {'tasks': []} if path.endswith('/pickup') else {'state': 'lapsed'} if path.endswith('/confirm-no-charge') else {'status': 'already_requested'}

    from nova_cli_public import cli, legacy_reads
    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService
    api = Api()
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    server = create_server(CustomerReadService(api))
    args = cli.build_parser().parse_args(['bundle-shop', 'fmc-pdf', 'B-1', '1', '--out', str(tmp_path / 'fmc.pdf')])
    assert args.handler(args)['content_type'] == 'application/pdf'
    assert (tmp_path / 'fmc.pdf').read_bytes().startswith(b'%PDF-')
    args = cli.build_parser().parse_args(['bundle-shop', 'pickup', 'B-1', '1',
        '--start', '2026-11-12T10:00:00Z', '--end', '2026-11-12T12:00:00Z'])
    assert args.handler(args)['tasks'] == []

    async def check():
        async with create_connected_server_and_client_session(server) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert steps.MODELS.keys() <= tools.keys()
            assert set(tools[steps.REJECT].inputSchema['required']) == {'ref', 'reason'}
            rejected = await sdk.call_tool(steps.REJECT, {'ref': 'B-1', 'reason': 'Cannot repair'})
            assert not rejected.isError and rejected.structuredContent['rejected'] is True
            assert tools[steps.PDF].annotations.readOnlyHint
            assert not tools[steps.CONTACT].annotations.readOnlyHint
            pdf = await sdk.call_tool(steps.PDF, {'ref': 'B-1', 'unit': 1})
            assert not pdf.isError
            resource = next(item.resource for item in pdf.content if item.type == 'resource')
            assert base64.b64decode(resource.blob).startswith(b'%PDF-')
            for name, payload, suffix, receipt in [
                (steps.PICKUP, {'start': '2026-11-12T10:00:00Z', 'end': '2026-11-12T12:00:00Z'}, 'pickup', 'tasks'),
                (steps.NO_CHARGE, {}, 'confirm-no-charge', 'state'),
                (steps.CONTACT, {}, 'contact', 'status')]:
                result = await sdk.call_tool(name, {'ref': 'B-1', 'unit': 1, **payload})
                assert not result.isError and receipt in result.structuredContent
                assert api.calls[-2][1].endswith('/' + suffix)
                assert api.calls[-1][1].endswith('/vans')
            assert not any('readiness' in name or 'payment' in name or name == 'accept_bundle' for name in tools)
    asyncio.run(check())


def test_customer_route_admission_and_discovery():
    from nova_cli_public import cli
    from nova_cli_public.capabilities import manifest
    from nova_cli_public.write_routes import admitted_write
    for name in steps.WRITES:
        route = '/bundle-offers/B-1/reject' if name == steps.REJECT else '/bundle-offers/B-1/vans/1/' + steps.SUFFIXES[name]
        assert admitted_write('POST', route)
    for suffix in ('readiness', 'accept', 'payment', 'update-payment'):
        assert not admitted_write('POST', '/bundle-offers/B-1/vans/1/' + suffix)
    assert not admitted_write('POST', '/bundle-offers/B-1/accept')
    rejection = manifest(cli.build_parser(), 'bundle-shop reject')['commands'][0]
    assert rejection['required_operation'] == 'capacity.bundles.reject.v1'
    assert rejection['effects'] == ['remote_write']
    entry = manifest(cli.build_parser(), 'bundle-shop contact')['commands'][0]
    assert entry['required_operation'] == 'capacity.contact.create.v1'
    assert entry['required_scope'] == 'nova:read nova:write'


@pytest.mark.parametrize('name,value', [
    ('list_bundle_offers', {'rows': [{'ref': 'B-1', 'status': 'open', 'total_price_cents': 0, 'browser_url': 'https://app.example/bundle-offers/B-1'}]}),
    ('get_bundle_offer_report', {'ref': 'B-1', 'status': 'awarded', 'report': None, 'browser_url': 'https://app.example/bundle-offers/B-1'}),
])
def test_offer_and_report_keep_purchase_browser_url(name, value):
    from nova_cli_public.bundle_workflow import execute
    client = SimpleNamespace(profile=SimpleNamespace(api='https://app.example/api'), request=Mock(return_value=value))
    assert execute(client, name, {} if name == 'list_bundle_offers' else {'ref': 'B-1'}) == value


@pytest.mark.parametrize('status', ['requested', 'already_requested'])
def test_contact_status_is_never_invented(status):
    client = SimpleNamespace(request=Mock(side_effect=[{'status': status}, VANS]))
    assert steps.execute(client, steps.CONTACT, {'ref': 'B-1', 'unit': 1})['status'] == status


def test_missing_authorization_number_never_uploads():
    from nova_cli_public.capacity_evidence import execute
    client = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError, match='authorization|autorización'):
        execute(client, 'upload_capacity_evidence', {'ref': 'B-1', 'unit': 1, 'kind': 'authorization',
            'content_type': 'application/pdf', 'content_base64': 'JVBERi0='})
    client.request.assert_not_called()


@pytest.mark.parametrize('status', [401, 403, 404, 409, 413, 422])
def test_local_mcp_keeps_localized_errors_without_retry(status):
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session
    api = SimpleNamespace(profile=SimpleNamespace(auth='service'), request=Mock(
        side_effect=ApiError('Este paso no está disponible.', status=status, code='refused', detail={'message': 'Detalle localizado.'})))
    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService
    server = create_server(CustomerReadService(api))
    async def check():
        async with create_connected_server_and_client_session(server) as sdk:
            result = await sdk.call_tool(steps.NO_CHARGE, {'ref': 'B-1', 'unit': 1})
            assert result.isError
            assert 'Detalle localizado.' in result.content[0].text
    asyncio.run(check())
    assert api.request.call_count == 1


def test_reject_cmr_bundle_has_no_unit_and_refreshes_confirmed_receipt():
    result = {'ref': 'B-1', 'rejected': True}
    client = SimpleNamespace(request=Mock(side_effect=[result, VANS]))
    value = steps.execute(client, steps.REJECT, {'ref': 'B-1', 'reason': 'Cannot repair'})
    assert value == {**result, **VANS}
    assert client.request.call_args_list[0].args == ('POST', '/bundle-offers/B-1/reject')
    assert client.request.call_args_list[0].kwargs == {'retry_auth': False, 'json_body': {'reason': 'Cannot repair'}}
    command = next(entry for entry in steps.COMMANDS if entry['tool'] == steps.REJECT)
    assert command['grant'] == 'capacity.bundles.reject.v1'
    assert command['effect'] == 'remote_write'


@pytest.mark.parametrize('arguments', [{'ref': 'B-1', 'reason': ' '}, {'ref': 'B-1', 'reason': 'Cannot repair', 'unit': 1}])
def test_reject_cmr_bundle_requires_whole_bundle_and_reason(arguments):
    client = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        steps.execute(client, steps.REJECT, arguments)
    client.request.assert_not_called()


def test_reject_cmr_bundle_does_not_repeat_uncertain_write():
    client = SimpleNamespace(request=Mock(side_effect=ApiError('offline', status=503)))
    with pytest.raises(ApiError) as error:
        steps.execute(client, steps.REJECT, {'ref': 'B-1', 'reason': 'Cannot repair'})
    assert error.value.code == 'outcome_unknown'
    assert client.request.call_count == 1
