"""Two standard fleet tools over the existing local MCP transport."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from nova_cli_public.errors import ApiError
from nova_cli_public.errors import ApiError as ResponseError
from nova_cli_public.fleet import DelegatedService
from nova_cli_public.mcp import create_server

VEHICLE = {
    "id": "VAN-0001",
    "fleet_id": "NF001",
    "vin": "SYNTHETIC",
    "plate": "TEST",
    "make": "Ford",
    "model": "Transit",
    "year": 2026,
    "mileage": 100,
    "grounded": False,
    "is_active": True,
}


class Reader:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, query=None):
        assert method == "GET"
        self.calls.append((path, query))
        if path == "/vehicles":
            return {
                "items": [{**VEHICLE, "server_note": "visible"}],
                "total": 1,
                "page": 1,
                "per_page": 20,
                "server_metadata": "visible",
            }
        if path == "/vehicles/VAN-0001":
            return {**VEHICLE, "server_note": "visible"}
        if path.startswith("/work-orders"):
            row = {"id": "WO-0001", "status": "reported", "vehicle_id": 1,
                   "dsp_id": 2, "vendor_workshop_id": 3, "notes": [{"text": "Visible"}]}
            return {"items": [row], "total": 1} if path.endswith("work-orders") else row
        if path.startswith("/defects"):
            row = {"id": "FD-0001", "vehicle_id": "VAN-0001", "fleet_id": "TEST",
                   "plate": "TEST", "vehicle_class": "regular_cargo_van", "source": "inspection",
                   "part": "tire", "defect_type": "worn", "details": {},
                   "reported_at": "2026-10-23T12:00:00Z", "created_at": "2026-10-23T12:00:00Z",
                   "updated_at": "2026-10-23T12:00:00Z", "notes": "Visible"}
            return {"items": [row], "total": 1, "page": 1, "per_page": 50} if path.endswith("defects") else row
        raise AssertionError(path)


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("list_vehicles", {"page": True}),
        ("list_vehicles", {"per_page": 101}),
        ("list_vehicles", {"profile": "other"}),
        ("list_vehicles", {"url": "https://evil.example"}),
        ("get_vehicle", {"vehicle_id": "../../auth/me"}),
        ("get_vehicle", {}),
        ("delete_vehicle", {}),
        ("nova_operations", {}),
        ("nova_fleet_read", {}),
    ],
)
def test_invalid_arguments_make_no_api_request(tool, arguments):
    reader = Reader()
    with pytest.raises(ValueError):
        DelegatedService(reader).run(tool, arguments)
    assert reader.calls == []


def test_discovery_is_static_and_exposes_only_typed_fleet_tools():
    reader = Reader()
    schemas = DelegatedService(reader).tool_schemas()
    assert set(schemas) == set(__import__("nova_cli_public.reads", fromlist=["BY_TOOL"]).BY_TOOL)
    assert schemas["get_vehicle"]["properties"]["vehicle_id"]["pattern"]
    assert all(s["additionalProperties"] is False for s in schemas.values())
    assert reader.calls == []


@pytest.mark.parametrize(
    "tool,args", [("list_vehicles", {}), ("get_vehicle", {"vehicle_id": "VAN-0001"})]
)
def test_bad_fleet_response_is_rejected(tool, args, monkeypatch):
    reader = Reader()
    monkeypatch.setattr(reader, "request", lambda *a, **kw: {"secret": "must not escape"})
    with pytest.raises(ResponseError):
        DelegatedService(reader).run(tool, args)


def test_real_stdio_discovery_list_get_and_legacy_denial(tmp_path):
    runner = tmp_path / "server.py"
    runner.write_text(
        "import runpy, asyncio\n"
        + f"ns=runpy.run_path({str(Path(__file__).resolve())!r})\n"
        + "from nova_cli_public.mcp import create_server, run_stdio\n"
        + "asyncio.run(run_stdio(create_server(ns['DelegatedService'](ns['Reader']()))))\n"
    )

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(runner)],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            assert {"list_repair_requests", "get_repair_request", "list_repair_request_external_vendor_options"} <= {tool.name for tool in tools}
            assert "set_defect_cost" in {tool.name for tool in tools}
            assert {"update_vehicle_note", "delete_vehicle_note"}.issubset({tool.name for tool in tools})
            assert all(t.outputSchema for t in tools)
            assert (await session.list_resources()).resources == []
            rows = await session.call_tool("list_vehicles", {"fleet_id": "NF001"})
            assert rows.structuredContent["items"] == [{**VEHICLE, "server_note": "visible"}]
            detail = await session.call_tool("get_vehicle", {"vehicle_id": "VAN-0001"})
            assert detail.structuredContent == {**VEHICLE, "server_note": "visible"}
            orders = await session.call_tool("list_work_orders", {"limit": 1})
            order = await session.call_tool("get_work_order", {"work_order_id": "WO-0001"})
            assert orders.structuredContent["items"][0] == order.structuredContent
            assert order.structuredContent["notes"] == [{"text": "Visible"}]
            defects = await session.call_tool("list_defects", {"open_only": True})
            defect = await session.call_tool("get_defect", {"defect_id": "FD-0001"})
            assert defects.structuredContent["items"][0] == defect.structuredContent
            assert defect.structuredContent["notes"] == "Visible"
            assert (await session.call_tool("show_workspace", {})).isError

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "authentication_required"),
        (403, "forbidden"),
        (404, "not_found"),
        (409, "unavailable"),
        (503, "unavailable"),
    ],
)
def test_live_api_denial_returns_safe_recovery_error(status, expected):
    reader = Reader()

    def fail(*args, **kwargs):
        raise ApiError("PRIVATE TOKEN BODY", status=status)

    reader.request = fail
    server = create_server(DelegatedService(reader))
    result = asyncio.run(
        server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="list_vehicles", arguments={}),
            )
        )
    )
    assert result.root.structuredContent == {"error": {"code": expected}}
    assert "PRIVATE" not in result.model_dump_json()


def test_stdio_handler_validates_before_api_reads():
    reader = Reader()
    server = create_server(DelegatedService(reader))
    result = asyncio.run(
        server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="list_vehicles", arguments={"page": True}),
            )
        )
    )
    assert result.root.structuredContent == {"error": {"code": "invalid_arguments"}}
    assert reader.calls == []
