import json
import shlex

import pytest

from nova_cli_public import cli


def manifest(capsys, *args):
    assert cli.main(['capabilities', '--json', *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_discovery_needs_no_profile_credentials_or_network(capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Offline capability discovery accessed authentication')
    monkeypatch.setattr(cli, 'client_from_args', forbidden)
    monkeypatch.setattr(cli, 'profile_from_args', forbidden)
    result = manifest(capsys)
    assert result['schema_version'] == 1
    assert result['authorization'] == 'not_checked'
    assert result['full_customer_parity'] is False
    assert result['mcp']['command'] == 'nova-mcp --profile PROFILE'
    assert result['mcp']['transport'] == 'stdio'
    assert set(result['mcp']['tools']) == {'list_vehicles', 'get_vehicle'}
    assert {c['command'] for c in result['commands']} == {
        'capabilities', 'profile set', 'profile use', 'profile show', 'profile remove',
        'profile list', 'auth login', 'auth status', 'auth refresh', 'auth logout',
        'vehicle list', 'vehicle get',
    }
    for command in result['commands']:
        for example in command['examples']:
            cli.build_parser().parse_args(shlex.split(example)[1:])


def test_fleet_discovery_includes_exact_schemas_and_read_only_scope(capsys):
    from nova_cli_public.fleet import ARGUMENTS, OUTPUTS
    result = manifest(capsys, '--command', 'vehicle get')
    entry, = result['commands']
    assert entry['tool_input_schema'] == ARGUMENTS['get_vehicle'].model_json_schema()
    assert set(entry['input_schema']['properties']) == {'vehicle_id', 'profile', 'json'}
    assert entry['input_schema']['properties']['vehicle_id']['pattern']
    assert entry['output_schema'] == OUTPUTS['get_vehicle'].model_json_schema()
    assert entry['effects'] == ['remote_read']
    assert entry['required_scope'] == 'nova:read'
    assert entry['mcp_tool'] == 'get_vehicle'
    assert entry['api'] == {'method': 'GET', 'path': '/assistant/vehicles/{vehicle_id}'}


def test_local_logout_discovery_does_not_claim_server_revocation(capsys):
    entry, = manifest(capsys, '--command', 'auth logout')['commands']
    assert entry['effects'] == ['local_credentials_delete']
    assert 'server connection remains' in entry['description']


def test_unknown_capability_is_an_error_not_a_successful_empty_result(capsys):
    assert cli.main(['capabilities', '--command', 'admin users', '--json']) == 2
    assert 'Unknown customer command' in capsys.readouterr().err
