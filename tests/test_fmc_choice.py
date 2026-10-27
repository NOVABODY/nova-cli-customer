import asyncio
import io
import json
import urllib.error
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.client import ApiClient
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService

CATALOG = [{'id': 'FMC-8', 'name': 'Synthetic Rentals', 'is_active': True, 'company_type': 'rental', 'aliases': []}]
VEHICLE = {'id': 'VAN-7', 'fmc_company_id': 'FMC-8', 'fmc': 'Synthetic Rentals', 'native': True}


class Opener:
    def __init__(self, value=VEHICLE, status=200):
        self.value, self.status, self.calls = value, status, []

    def open(self, request, timeout):
        self.calls.append(request)
        headers = Message()
        headers['Content-Type'] = 'application/json'
        if self.status != 200:
            raise urllib.error.HTTPError(request.full_url, self.status, 'rejected', headers, io.BytesIO(b'{}'))
        response = io.BytesIO(json.dumps(self.value).encode())
        response.status, response.headers = 200, headers
        return response


def client(opener):
    api = ApiClient(Profile('test', 'https://nova.example/api'), object(), opener=opener)
    api.access_token = 'synthetic-access'
    return api


@pytest.mark.parametrize('active_only', [True, False])
def test_catalog_cli_and_sdk_preserve_native_array_and_active_default(monkeypatch, active_only):
    opener = Opener(CATALOG)
    api = client(opener)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['fmc-company', 'list'] + ([] if active_only else ['--include-inactive']))
    assert args.handler(args) == CATALOG
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert tools['list_fmc_companies'].annotations.readOnlyHint
            result = await sdk.call_tool('list_fmc_companies', {'active_only': active_only})
            assert not result.isError and result.structuredContent == {'items': CATALOG}
    asyncio.run(check())
    assert len(opener.calls) == 2
    for call in opener.calls:
        assert call.method == 'GET' and urlsplit(call.full_url).path == '/api/fmc-companies' and call.data is None
        assert parse_qs(urlsplit(call.full_url).query) == ({} if active_only else {'active_only': ['false']})


def test_assignment_cli_and_sdk_use_fixed_put_and_native_company_receipt(monkeypatch):
    opener = Opener()
    api = client(opener)
    monkeypatch.setattr(legacy_reads, 'client_from_args', lambda args: api)
    args = cli.build_parser().parse_args(['vehicle', 'set-fmc-company', 'VAN-7', '--company-id', 'FMC-8'])
    assert args.handler(args) == VEHICLE
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert not tools['set_vehicle_fmc_company'].annotations.readOnlyHint
            result = await sdk.call_tool('set_vehicle_fmc_company', {'vehicle_id': 'VAN-7', 'company_id': 8})
            assert not result.isError and result.structuredContent == VEHICLE
    asyncio.run(check())
    assert len(opener.calls) == 2
    assert all(call.method == 'PUT' and call.full_url.endswith('/vehicles/VAN-7/fmc-company') for call in opener.calls)
    assert [json.loads(call.data) for call in opener.calls] == [{'company_id': 'FMC-8'}, {'company_id': 8}]


@pytest.mark.parametrize('arguments', [{'vehicle_id': 'VAN-0', 'company_id': 8}, {'vehicle_id': 'VAN-7', 'company_id': False}, {'vehicle_id': 'VAN-7', 'company_id': 'FMC-8', 'force': True}])
def test_closed_company_choice_arguments_fail_before_transport(arguments):
    opener = Opener()
    with pytest.raises(ValidationError):
        CustomerReadService(client(opener)).run('set_vehicle_fmc_company', arguments)
    assert not opener.calls


@pytest.mark.parametrize('value', [dict(VEHICLE, id='VAN-9'), dict(VEHICLE, fmc_company_id='FMC-9'), dict(VEHICLE, bad=float('nan'))])
def test_unconfirmed_assignment_receipt_is_unknown(value):
    opener = Opener(value)
    with pytest.raises(ApiError) as error:
        CustomerReadService(client(opener)).run('set_vehicle_fmc_company', {'vehicle_id': 'VAN-7', 'company_id': 'FMC-8'})
    assert error.value.code == 'outcome_unknown' and len(opener.calls) == 1


@pytest.mark.parametrize('status', [401, 403, 409, 503])
def test_assignment_never_refreshes_or_retries_an_uncertain_write(monkeypatch, status):
    opener = Opener(status=status)
    api = client(opener)
    monkeypatch.setattr(api, 'refresh', lambda: pytest.fail('Do not repeat company assignment'))
    with pytest.raises(ApiError):
        CustomerReadService(api).run('set_vehicle_fmc_company', {'vehicle_id': 'VAN-7', 'company_id': 'FMC-8'})
    assert len(opener.calls) == 1


@pytest.mark.parametrize('value', [{}, [{'id': False, 'name': 'Synthetic', 'is_active': True}]])
def test_invalid_native_catalog_is_not_a_success(value):
    opener = Opener(value)
    with pytest.raises(ApiError):
        CustomerReadService(client(opener)).run('list_fmc_companies', {})
    assert len(opener.calls) == 1


def test_catalog_input_is_closed_and_boolean_before_transport():
    opener = Opener(CATALOG)
    with pytest.raises(ValidationError):
        CustomerReadService(client(opener)).run('list_fmc_companies', {'active_only': 'false', 'url': 'https://evil.example'})
    assert not opener.calls
