from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from nova_cli_public import bundle_returns as returns
from nova_cli_public.errors import ApiError


def test_return_confirms_task_and_mileage_without_retry():
    api = Mock()
    api.request.return_value = {'task_id': 7, 'status': 'checked_in', 'mileage': 120}
    args = {'task_id': 7, 'mileage': 120, 'photos': [{'storage_key': 'synthetic/photo'}]}
    assert returns.execute(api, args) == api.request.return_value
    api.request.assert_called_once_with('POST', '/bundle-offers/transport/7/check-in',
        json_body={'mileage': 120, 'photos': args['photos']}, retry_auth=False)


@pytest.mark.parametrize('task_id', [0, -1, '../7', True])
def test_invalid_task_never_reaches_transport(task_id):
    api = Mock()
    with pytest.raises(ValidationError):
        returns.execute(api, {'task_id': task_id, 'mileage': 120, 'photos': [{}]})
    api.request.assert_not_called()


def test_unconfirmed_return_is_unknown_and_never_retried():
    api = Mock()
    api.request.return_value = {'task_id': 8, 'status': 'checked_in', 'mileage': 120}
    with pytest.raises(ApiError) as failure:
        returns.execute(api, {'task_id': 7, 'mileage': 120, 'photos': [{}]})
    assert failure.value.code == 'outcome_unknown'
    assert api.request.call_count == 1


def test_cli_and_local_mcp_share_the_named_operation(monkeypatch):
    from nova_cli_public import cli, legacy_writes
    from nova_cli_public.reads import CustomerReadService
    from nova_cli_public.write_routes import admitted_write
    api = Mock()
    api.request.return_value = {'task_id': 7, 'status': 'checked_in', 'mileage': 120}
    monkeypatch.setattr(legacy_writes, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['bundle-return', 'record', '7', '--mileage', '120', '--photos', '[{}]'])
    assert args.handler(args) == api.request.return_value
    service = CustomerReadService(api)
    assert service.tool_schemas()['record_bundle_return']['properties']['photos']['type'] == 'array'
    assert service.run('record_bundle_return', {'task_id': 7, 'mileage': 120, 'photos': [{}]}) == api.request.return_value
    assert admitted_write('POST', '/bundle-offers/transport/7/check-in')
