import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nova_cli_public import cli, delegated, legacy_reads, reads
from nova_cli_public.errors import UsageError
from nova_cli_public.event_commands import EVENT_LOCAL_TOOLS


class Reader:
    profile = SimpleNamespace(api="https://nova.example/api", name="test")

    def __init__(self):
        self.calls = []
        self.identity = ("https://nova.example", "1", "1", "connection-a")
        self.rows = [{"id": "FD-1", "reported_at": "2026-10-23T12:00:00Z"}]

    def refresh(self):
        pass

    def connection_identity(self):
        return self.identity

    def request(self, method, path, *, query=None):
        self.calls.append((method, path, query))
        return {"items": self.rows, "total": len(self.rows), "page": 1,
                "per_page": (query or {}).get("per_page", 50), "keyset": True}


def test_registry_contains_30_reads_27_full_scope_tools_and_4_events_without_admin_or_generic_api():
    assert reads.BY_COMMAND["repair-request list"]["grant"] == "repair_requests.list.v1"
    assert reads.BY_COMMAND["defect set-cost"]["grant"] == "defects.cost.set.v1"
    assert reads.BY_COMMAND["vehicle update-note"]["grant"] == "vehicles.notes.update.v1"
    assert {
        "defect photos",
        "defect pull",
        "vehicle-report pull",
        "work-order wait",
        "health check",
        "health ready",
        "auth whoami",
    } <= reads.BY_COMMAND.keys()
    parser = cli.build_parser()
    for command in ["admin users mfa-reset", "api GET /vehicles"]:
        with pytest.raises(SystemExit):
            parser.parse_args(command.split())


def test_aliases_reuse_same_handler_and_defaults():
    parser = cli.build_parser()
    for canonical, alias in [
        ("work-order get WO-1", "wo get WO-1"),
        ("defect list", "defects list"),
        ("notification list", "notifications list"),
    ]:
        left, right = parser.parse_args(canonical.split()), parser.parse_args(alias.split())
        assert left.handler is right.handler
        assert left.read_command == right.read_command


def test_default_browser_grants_match_default_full_vehicle_tools():
    assert set(delegated.DEFAULT_OPERATIONS.split()) == {
        reads.BY_TOOL["list_vehicles"]["grant"],
        reads.BY_TOOL["get_vehicle"]["grant"],
    }
    assert "vehicles.list.v1" not in delegated.DEFAULT_OPERATIONS


def test_mcp_numeric_custom_parser_types_keep_integer_contract():
    client = Reader()
    reads.CustomerReadService(client).run("list_vehicle_reports", {"page": 2, "per_page": 10})
    assert client.calls == [("GET", "/vehicle-reports", {"limit": 10, "offset": 10})]
    assert (
        reads.MODELS["list_vehicle_reports"].model_json_schema()["properties"]["page"]["type"]
        == "integer"
    )


def test_full_vehicle_output_is_not_silently_projected():
    client = Reader()
    client.rows = [{"id": "VAN-1", "is_active": False, "dsp_name": "Synthetic DSP", "history": [1]}]
    result = reads.CustomerReadService(client).run(
        "list_vehicles", {"status": "all", "dsp_id": "DSP-1"}
    )
    assert result["items"] == client.rows
    assert client.calls == [("GET", "/vehicles", {"dsp_id": "DSP-1", "include_inactive": True})]


@pytest.mark.parametrize("ids", [["../escape"], ["FD-1/../../escape"], ["https://example.test"]])
def test_photos_reject_invalid_ids_before_network_or_filesystem(tmp_path, ids):
    client = Reader()
    with pytest.raises(UsageError):
        legacy_reads.download_defect_photos(client, ids, tmp_path / "never", fetch=lambda url: b"x")
    assert not client.calls
    assert not (tmp_path / "never").exists()


def test_relative_signed_photo_uses_profile_api_prefix_and_no_authenticated_request(tmp_path):
    client = Reader()
    client.rows = [
        {
            "id": "P-1",
            "url": "/uploads/object/defects/photo.jpg?token=signed",
            "content_type": "image/jpeg",
        }
    ]
    fetched = []
    result = legacy_reads.download_defect_photos(
        client, ["FD-1"], tmp_path, fetch=lambda url: fetched.append(url) or b"bytes"
    )
    assert fetched == ["https://nova.example/api/uploads/object/defects/photo.jpg?token=signed"]
    assert client.calls == [("GET", "/defects/FD-1/photos", None)]
    assert Path(result["photos"]["FD-1"][0]["path"]).read_bytes() == b"bytes"


@pytest.mark.parametrize("url", ["//other.example/photo", "/auth/me", "http://other.example/photo"])
def test_relative_photo_resolution_refuses_unrelated_targets(url):
    with pytest.raises(UsageError):
        legacy_reads.resolve_photo_url(url, Reader())


def test_defect_cursor_does_not_advance_when_output_write_fails(monkeypatch, tmp_path):
    client = Reader()
    cursor = tmp_path / "cursor.json"
    args = cli.build_parser().parse_args(
        [
            "defect",
            "pull",
            "--new",
            "--cursor-file",
            str(cursor),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    args._client = client
    monkeypatch.setattr(
        legacy_reads, "write_json_file", lambda *a: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError):
        args.handler(args)
    assert not cursor.exists()


def test_defect_cursor_does_not_advance_when_stdout_fails(monkeypatch, tmp_path):
    client = Reader()
    cursor = tmp_path / "cursor.json"
    args = cli.build_parser().parse_args(["defect", "pull", "--new", "--cursor-file", str(cursor)])
    args._client = client
    monkeypatch.setattr(
        legacy_reads, "emit", lambda *a, **kw: (_ for _ in ()).throw(OSError("broken pipe"))
    )
    with pytest.raises(UsageError):
        args.handler(args)
    assert not cursor.exists()


def test_mcp_relogin_uses_separate_cursor_and_returns_local_file_refs(monkeypatch, tmp_path):
    monkeypatch.setattr(reads, "data_dir", lambda: tmp_path)
    client = Reader()
    service = reads.CustomerReadService(client)
    first = service.run("pull_defects", {"new": True})
    client.identity = ("https://nova.example", "2", "2", "connection-b")
    second = service.run("pull_defects", {"new": True})
    assert len(list((tmp_path / "mcp-cursors").glob("*.json"))) == 2
    assert all("date_from" not in call[2] for call in client.calls)
    for result in [first, second]:
        assert result["files"][0]["uri"].startswith("file:///")
        assert json.loads(Path(result["files"][0]["path"]).read_text())["count"] == 1


def test_mcp_connection_change_during_pull_does_not_advance_cursor(monkeypatch, tmp_path):
    monkeypatch.setattr(reads, "data_dir", lambda: tmp_path)
    client = Reader()
    original = client.request

    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        client.identity = ("https://nova.example", "2", "2", "other")
        return value

    client.request = changed
    with pytest.raises(UsageError, match="Connection changed"):
        reads.CustomerReadService(client).run("pull_defects", {"new": True})
    assert not list(tmp_path.rglob("mcp-cursors/*.json"))


def test_mcp_photo_files_have_count_bound_and_no_binary_in_result(monkeypatch, tmp_path):
    monkeypatch.setattr(reads, "data_dir", lambda: tmp_path)
    client = Reader()
    client.rows = [
        {"id": "P-1", "url": "https://storage.example/photo", "content_type": "image/png"}
    ]
    monkeypatch.setattr(legacy_reads, "fetch_presigned", lambda url, max_bytes: b"PNG bytes")
    result = reads.CustomerReadService(client).run(
        "download_defect_photos", {"defect_ids": ["FD-1"]}
    )
    assert result["files"][0]["size_bytes"] == 9
    assert Path(result["files"][0]["path"]).read_bytes() == b"PNG bytes"
    assert "PNG bytes" not in json.dumps(result)
    client.rows *= 21
    with pytest.raises(UsageError, match="count limit"):
        reads.CustomerReadService(client).run("download_defect_photos", {"defect_ids": ["FD-1"]})


def test_mcp_wait_is_bounded_before_any_request():
    client = Reader()
    with pytest.raises(ValueError):
        reads.CustomerReadService(client).run(
            "wait_work_order", {"wo_id": "WO-1", "until": "completed", "max_wait": 30}
        )
    assert not client.calls


def test_empty_defect_page_with_remaining_total_fails_instead_of_looping():
    client = Reader()
    client.request = lambda *args, **kwargs: {"items": [], "total": 1, "page": 1, "per_page": 50, "keyset": True}
    with pytest.raises(legacy_reads.ApiError, match="Invalid defect page"):
        legacy_reads.fetch_all_defects(client, {})


def test_mcp_annotations_disclose_file_writes():
    import asyncio

    from mcp import types

    from nova_cli_public.mcp import create_server

    server = create_server(reads.CustomerReadService(Reader()))
    result = asyncio.run(
        server.request_handlers[types.ListToolsRequest](types.ListToolsRequest(method="tools/list"))
    )
    for tool in result.root.tools:
        assert tool.annotations.readOnlyHint == (
            tool.name == "preview_fleet_import" or tool.name not in reads.FILE_TOOLS | reads.WRITE_TOOLS | EVENT_LOCAL_TOOLS
        )
        assert tool.annotations.idempotentHint == (
            tool.name == "preview_fleet_import" or tool.name not in reads.FILE_TOOLS | reads.WRITE_TOOLS | EVENT_LOCAL_TOOLS
        )
