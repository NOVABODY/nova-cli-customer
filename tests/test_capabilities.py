import json

import pytest

from nova_cli_public import cli
from nova_cli_public.reads import BY_COMMAND, BY_TOOL, MODELS, CustomerReadService


def manifest(capsys, *args):
    assert cli.main(["capabilities", "--json", *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_discovery_needs_no_profile_credentials_or_network(capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline capability discovery accessed authentication")

    monkeypatch.setattr(cli, "client_from_args", forbidden)
    monkeypatch.setattr(cli, "profile_from_args", forbidden)
    result = manifest(capsys)
    assert result["authorization"] == "not_checked"
    assert result["full_customer_parity"] is False
    assert result["legacy_customer_parity"] is True
    assert set(result["mcp"]["tools"]) == set(BY_TOOL)
    names = [entry["command"] for entry in result["commands"]]
    assert len(names) == len(set(names))
    assert set(BY_COMMAND) <= set(names)
    assert "work-orders get" not in names  # aliases do not duplicate canonical entries


@pytest.mark.parametrize(
    "command,tool,grant",
    [
        ("vehicle get", "get_vehicle", "vehicles.get_full.v1"),
        ("work-order get", "get_work_order", "work_orders.get.v1"),
        ("defect get", "get_defect", "defects.get.v1"),
        ("defect photos", "download_defect_photos", "defects.photos.list.v1"),
    ],
)
def test_discovery_uses_execution_contract_and_explicit_grant(capsys, command, tool, grant):
    (entry,) = manifest(capsys, "--command", command)["commands"]
    assert entry["tool_input_schema"] == MODELS[tool].model_json_schema()
    assert entry["output_schema"] == CustomerReadService(None).output_schema(tool)
    assert entry["required_operation"] == grant
    assert entry["required_scope"] == "nova:read"
    assert entry["mcp_tool"] == tool
    assert entry["output_schema"]["additionalProperties"] is True


def test_local_logout_discovery_does_not_claim_server_revocation(capsys):
    (entry,) = manifest(capsys, "--command", "auth logout")["commands"]
    assert entry["effects"] == ["local_credentials_delete"]
    assert "server connection remains" in entry["description"]


def test_unknown_capability_is_an_error_not_a_successful_empty_result(capsys):
    assert cli.main(["capabilities", "--command", "admin users", "--json"]) == 2
    assert "Unknown customer command" in capsys.readouterr().err
