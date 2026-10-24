import argparse
import asyncio

import pytest
from mcp import types
from pydantic import ValidationError

from nova_cli_public import cli
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import UsageError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService


class Client:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs["json_body"]))
        return {"id": "FD-1", "vehicle_id": "VAN-1"}


BASE = {
    "vehicle_id": "VAN-1",
    "source": "maintenance_request",
    "part": "headlight",
    "defect_type": "not_working",
}


def test_cli_and_local_mcp_report_with_same_catalog_and_routing_body():
    direct, local = Client(), Client()
    args = cli.build_parser().parse_args(
        [
            "defect",
            "create",
            "--vehicle-id",
            "VAN-1",
            "--source",
            "maintenance_request",
            "--part",
            "headlight",
            "--defect-type",
            "not_working",
            "--vendor-workshop-id",
            "3",
            "--details",
            '{"observed":"dark"}',
            "--notes",
            "Left lamp",
        ]
    )
    args._client = direct
    result = args.handler(args)
    assert (
        CustomerReadService(local).run(
            "create_defect",
            {
                **BASE,
                "vendor_workshop_id": 3,
                "details": '{"observed":"dark"}',
                "notes": "Left lamp",
            },
        )
        == result
    )
    assert (
        direct.calls
        == local.calls
        == [
            (
                "POST",
                "/defects",
                {
                    **BASE,
                    "vendor_workshop_id": 3,
                    "details": {"observed": "dark"},
                    "notes": "Left lamp",
                },
            )
        ]
    )


@pytest.mark.parametrize(
    "values",
    [
        {"details": "[]"},
        {"details": "{"},
        {"details": '{"value": NaN}'},
        {"details": "x" * 65537},
        {"source": "inspection"},
        {"inspection_id": "INS-1"},
        {"dsp_contact_user_id": 2},
        {"vendor_workshop_id": 2, "external_vendor_id": 3},
        {"part": " "},
        {"notes": "x" * 2001},
        {"reported_at": "2026-10-24T00:00:00"},
        {"reporter": {"email": "another@example.test"}},
        {"mileage_at_report": 10},
    ],
)
def test_invalid_or_service_only_intake_never_sends(values):
    client = Client()
    with pytest.raises((UsageError, ValidationError, ValueError, argparse.ArgumentTypeError)):
        CustomerReadService(client).run("create_defect", {**BASE, **values})
    assert client.calls == []


def test_reporting_discovery_names_write_authority_and_fixed_route():
    result = manifest(cli.build_parser(), "defect create")["commands"][0]
    assert result["required_scope"] == "nova:read nova:write"
    assert result["required_operation"] == "defects.create.v1"
    assert result["effects"] == ["remote_write"]
    assert result["api_routes"] == [{"method": "POST", "path_pattern": "/defects"}]
    assert result["tool_input_schema"]["additionalProperties"] is False


@pytest.mark.parametrize("values", [{"details": "[]"}, {"reported_at": "2026-10-24T00:00:00"}])
def test_mcp_reports_bad_intake_as_invalid_arguments(values):
    client = Client()
    server = create_server(CustomerReadService(client))
    request = types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(
        name="create_defect", arguments={**BASE, **values}))
    response = asyncio.run(server.request_handlers[types.CallToolRequest](request)).root
    assert response.isError
    assert response.structuredContent["error"]["code"] == "invalid_arguments"
    assert client.calls == []
