import asyncio
import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from mcp import types

from nova_cli_public import cli, delegated, legacy_writes
from nova_cli_public.capabilities import manifest
from nova_cli_public.errors import ApiError, AuthError, UsageError
from nova_cli_public.mcp import create_server
from nova_cli_public.reads import CustomerReadService


class Client:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json_body")))
        return {"ok": True}


@pytest.mark.parametrize(
    "argv,tool,arguments,expected",
    [
        (
            ["work-order", "schedule", "WO-1", "--clear-team", "--ro-number", "0012"],
            "schedule_work_order",
            {"wo_id": "WO-1", "clear_team": True, "ro_number": "0012"},
            {"team_id": None, "ro_number": "0012"},
        ),
        (
            [
                "work-order",
                "complete",
                "WO-1",
                "--last-mileage",
                "100",
                "--field",
                "work_photo_path=photo",
            ],
            "complete_work_order",
            {"wo_id": "WO-1", "last_mileage": 100, "field": ["work_photo_path=photo"]},
            {"last_mileage": 100, "work_photo_path": "photo"},
        ),
        (
            [
                "defect",
                "update",
                "FD-1",
                "--title",
                "  New title  ",
                "--expected-updated-at",
                "2026-10-23T00:00:00Z",
            ],
            "update_defect_title",
            {
                "defect_id": "FD-1",
                "title": "  New title  ",
                "expected_updated_at": "2026-10-23T00:00:00Z",
            },
            {"display_title": "New title", "expected_updated_at": "2026-10-23T00:00:00Z"},
        ),
        (
            ["work-order", "line-items", "update", "WO-1", "2", "--estimated-price", "12.30"],
            "update_work_order_line_item",
            {"wo_id": "WO-1", "line_item_id": "2", "estimated_price": "12.30"},
            {"estimated_price": "12.30"},
        ),
    ],
)
def test_cli_and_mcp_keep_same_write_payload(argv, tool, arguments, expected):
    direct, mcp = Client(), Client()
    args = cli.build_parser().parse_args(argv)
    args._client = direct
    args.handler(args)
    CustomerReadService(mcp).run(tool, arguments)
    assert direct.calls == mcp.calls
    assert direct.calls[0][2] == expected


def test_write_operations_need_explicit_scope_before_browser(monkeypatch):
    monkeypatch.setattr(delegated.webbrowser, "open", lambda url: pytest.fail("Browser opened"))
    with pytest.raises(UsageError, match="require --scope"):
        delegated.browser_code("https://nova.example", operations="vehicles.notes.create.v1")


def test_explicit_write_scope_keeps_selected_operations(monkeypatch):
    opened = []
    monkeypatch.setattr(delegated.webbrowser, "open", lambda url: opened.append(url) or False)
    with pytest.raises(AuthError):
        delegated.browser_code(
            "https://nova.example",
            operations="uploads.presign.v1 defects.photos.create.v1",
            scope="nova:read nova:write",
        )
    query = parse_qs(urlsplit(opened[0]).query)
    assert query["scope"] == ["nova:read nova:write"]
    assert query["operations"] == ["uploads.presign.v1 defects.photos.create.v1"]


def test_discovery_discloses_write_scope_and_separate_photo_commit():
    result = manifest(cli.build_parser(), "upload photo")["commands"][0]
    assert result["required_scope"] == "nova:read nova:write"
    assert result["required_operation"] == "uploads.presign.v1"
    assert result["conditional_operations"]["defect"] == "defects.photos.create.v1"
    assert result["effects"] == ["remote_write", "local_file_read"]
    assert result["api_routes"] == [{"method": "POST", "path_pattern": "/uploads/presigned"}]


def test_mcp_rejects_stdin_without_reading_or_sending(monkeypatch):
    monkeypatch.setattr(legacy_writes.sys, "stdin", io.StringIO("{}"))
    client = Client()
    with pytest.raises(UsageError, match="stdin"):
        CustomerReadService(client).run("create_vehicle_report", {"data_file": "-"})
    assert client.calls == []


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (409, "state_changed", "business_error"),
        (422, None, "business_error"),
        (None, "outcome_unknown", "outcome_unknown"),
    ],
)
def test_mcp_preserves_business_failure_and_unknown_outcome(status, code, expected):
    class Rejected(Client):
        def request(self, *args, **kwargs):
            raise ApiError(
                "synthetic",
                status=status,
                code=code,
                detail={"code": "state_changed", "minimum_mileage": 200},
            )

    server = create_server(CustomerReadService(Rejected()))
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(
            name="complete_work_order", arguments={"wo_id": "WO-1", "last_mileage": 100}
        ),
    )
    response = asyncio.run(server.request_handlers[types.CallToolRequest](request)).root
    assert response.isError
    assert response.structuredContent["error"]["code"] == expected
    if status:
        assert response.structuredContent["error"]["detail"]["minimum_mileage"] == 200


def test_cli_unknown_outcome_tells_user_to_check_before_retry(monkeypatch, capsys):
    class Rejected(Client):
        def request(self, *args, **kwargs):
            raise ApiError("synthetic", code="outcome_unknown")

    monkeypatch.setattr(legacy_writes, "client_from_args", lambda args: Rejected())
    assert cli.main(["work-order", "complete", "WO-1", "--last-mileage", "100", "--json"]) == 1
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["code"] == "outcome_unknown"
    assert "Check the record" in error["message"]
