"""Customer behavioral regressions reused from legacy CLI tree c2298bbf."""

from __future__ import annotations

import io
import json

import pytest

from nova_cli_public import legacy_reads as cli
from nova_cli_public.cli import build_parser
from nova_cli_public.config import Profile
from nova_cli_public.errors import PollTimeout, UsageError
from nova_cli_public.legacy_reads import (
    cmd_defect_list,
    cmd_defect_pull,
    cmd_work_order_line_items_list,
    cmd_work_order_wait,
)


class FakeClient:
    profile = Profile("test", "https://nova.example/api")

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.uploads = []

    def request(self, method, path, *, json_body=None, query=None):
        self.requests.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "query": query,
            }
        )
        return self.responses.pop(0)

    def put_bytes(self, url, data, *, content_type):
        self.uploads.append({"url": url, "data": data, "content_type": content_type})


def test_defect_list_uses_page_params_and_filters_status_client_side(monkeypatch):
    client = FakeClient(
        [
            {
                "items": [
                    {"id": "FD-1", "review_status": "pending_review"},
                    {"id": "FD-2", "review_status": "approved"},
                ],
                "total": 2,
                "page": 2,
                "per_page": 25,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "defect",
            "list",
            "--vehicle-id",
            "VAN-0001",
            "--status",
            "approved",
            "--page",
            "2",
            "--per-page",
            "25",
        ]
    )

    result = cmd_defect_list(args)

    assert client.requests[0]["query"] == {
        "vehicle_id": "VAN-0001",
        "page": 2,
        "per_page": 25,
    }
    assert result["items"] == [{"id": "FD-2", "review_status": "approved"}]
    assert result["total"] == 1


def test_vehicle_list_uses_page_params(monkeypatch):
    client = FakeClient([{"items": [], "total": 0, "page": 3, "per_page": 50}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle", "list", "--page", "3", "--per-page", "50"])

    args.handler(args)

    assert client.requests[0]["query"] == {"page": 3, "per_page": 50}


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("active", {"is_active": True}),
        ("inactive", {"is_active": False}),
        ("all", {"include_inactive": True}),
        ("grounded", {"grounded": True}),
    ],
)
def test_vehicle_list_translates_status_to_supported_api_filter(monkeypatch, status, expected):
    client = FakeClient([{"items": [], "total": 0}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle", "list", "--status", status])

    args.handler(args)

    assert client.requests[0]["query"] == expected


def test_vehicle_report_list_translates_page_to_limit_offset(monkeypatch):
    client = FakeClient([{"items": [], "total": 0, "limit": 25, "offset": 50}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "vehicle-report",
            "list",
            "--status",
            "promoted",
            "--external-ref",
            "rowriter:12345",
            "--updated-since",
            "2026-07-14T08:00:00-04:00",
            "--page",
            "3",
            "--per-page",
            "25",
        ]
    )

    args.handler(args)

    assert client.requests[0] == {
        "method": "GET",
        "path": "/vehicle-reports",
        "json_body": None,
        "query": {
            "status": "promoted",
            "external_ref": "rowriter:12345",
            "updated_since": "2026-07-14T12:00:00Z",
            "limit": 25,
            "offset": 50,
        },
    }


@pytest.mark.parametrize(
    "argv",
    [
        ["vehicle-report", "list", "--page", "0"],
        ["vehicle-report", "list", "--per-page", "201"],
        ["vehicle-report", "list", "--updated-since", "2026-07-14T12:00:00"],
        ["vehicle-report", "list", "--status", "unknown"],
    ],
)
def test_vehicle_report_list_rejects_invalid_arguments(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


def test_vehicle_report_pull_uses_composite_cursor_boundary(monkeypatch, tmp_path, capsys):
    cursor = tmp_path / "reports-cursor.json"
    original = {"updated_at": "2026-07-14T10:00:00Z", "id": "VR-00002"}
    cursor.write_text(json.dumps(original))
    client = FakeClient([{"items": [
        {"id": "VR-00003", "updated_at": original["updated_at"]},
        {"id": "VR-00004", "updated_at": "2026-07-14T10:00:01Z"}],
        "total": 2, "limit": 2, "offset": 0, "keyset": True}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle-report", "pull", "--status", "promoted",
                                     "--cursor-file", str(cursor), "--per-page", "2"])
    assert args.handler(args) is None and args.quiet is True
    package = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in package["reports"]] == ["VR-00003", "VR-00004"]
    assert package["cursor_before"] == original
    assert package["cursor_after"] == {"updated_at": "2026-07-14T10:00:01Z", "id": "VR-00004"}
    assert json.loads(cursor.read_text()) == package["cursor_after"]
    assert client.requests[0]["query"] == {"status": "promoted", "updated_since": original["updated_at"],
                                            "after_id": 2, "limit": 2, "offset": 0}


def test_vehicle_report_pull_old_cursor_includes_same_timestamp_ids(monkeypatch, tmp_path, capsys):
    cursor = tmp_path / "reports-cursor.json"
    cursor.write_text(json.dumps({"updated_at": "2026-07-14T10:00:00Z"}))
    client = FakeClient(
        [
            {
                "items": [
                    {"id": "VR-00001", "updated_at": "2026-07-14T10:00:00Z"},
                ],
                "total": 1,
                "limit": 100,
                "offset": 0,
                "keyset": True,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle-report", "pull", "--cursor-file", str(cursor)])

    args.handler(args)
    package = json.loads(capsys.readouterr().out)

    assert [item["id"] for item in package["reports"]] == ["VR-00001"]
    assert package["cursor_before"]["id"] == ""
    assert json.loads(cursor.read_text()) == {
        "updated_at": "2026-07-14T10:00:00Z",
        "id": "VR-00001",
    }


def test_vehicle_report_pull_compares_numeric_ids_across_padding_boundary(
    monkeypatch, tmp_path, capsys
):
    cursor = tmp_path / "reports-cursor.json"
    cursor.write_text(json.dumps({"updated_at": "2026-07-14T10:00:00Z", "id": "VR-99999"}))
    client = FakeClient(
        [
            {
                "items": [
                    {"id": "VR-100000", "updated_at": "2026-07-14T10:00:00Z"},
                ],
                "total": 1,
                "limit": 100,
                "offset": 0,
                "keyset": True,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle-report", "pull", "--cursor-file", str(cursor)])

    args.handler(args)
    package = json.loads(capsys.readouterr().out)

    assert [item["id"] for item in package["reports"]] == ["VR-100000"]
    assert package["cursor_after"] == {
        "updated_at": "2026-07-14T10:00:00Z",
        "id": "VR-100000",
    }


def test_vehicle_report_pull_does_not_advance_cursor_when_stdout_fails(monkeypatch, tmp_path):
    cursor = tmp_path / "reports-cursor.json"
    original = {"updated_at": "2026-07-14T10:00:00Z", "id": "VR-00001"}
    cursor.write_text(json.dumps(original))
    client = FakeClient(
        [
            {
                "items": [
                    {"id": "VR-00002", "updated_at": "2026-07-14T10:00:01Z"},
                ],
                "total": 1,
                "limit": 100,
                "offset": 0,
                "keyset": True,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    monkeypatch.setattr(
        cli, "emit", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("pipe closed"))
    )
    args = build_parser().parse_args(["vehicle-report", "pull", "--cursor-file", str(cursor)])

    with pytest.raises(UsageError, match="output"):
        args.handler(args)

    assert json.loads(cursor.read_text()) == original


def test_vehicle_report_pull_writes_package_before_advancing_cursor(monkeypatch, tmp_path):
    cursor = tmp_path / "reports-cursor.json"
    out = tmp_path / "reports.json"
    client = FakeClient(
        [
            {
                "items": [
                    {"id": "VR-00002", "updated_at": "2026-07-14T10:00:01Z"},
                ],
                "total": 1,
                "limit": 100,
                "offset": 0,
                "keyset": True,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "vehicle-report",
            "pull",
            "--cursor-file",
            str(cursor),
            "--out",
            str(out),
        ]
    )

    result = args.handler(args)

    assert result == {"ok": True, "out": str(out), "count": 1}
    package = json.loads(out.read_text())
    assert package["cursor_after"] == json.loads(cursor.read_text())


@pytest.mark.parametrize(
    "cursor_body",
    [
        '{"updated_at":"not-a-date","id":"VR-1"}',
        '{"updated_at":"2026-07-14T10:00:00Z","id":"not-a-report-id"}',
    ],
)
def test_vehicle_report_pull_rejects_invalid_cursor_before_request(
    monkeypatch, tmp_path, cursor_body
):
    cursor = tmp_path / "reports-cursor.json"
    cursor.write_text(cursor_body)
    client = FakeClient([])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle-report", "pull", "--cursor-file", str(cursor)])

    with pytest.raises(UsageError):
        args.handler(args)

    assert client.requests == []


def test_vehicle_report_pull_rejects_quiet_without_output_file(monkeypatch):
    client = FakeClient([])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle-report", "pull", "--quiet"])

    with pytest.raises(UsageError, match="--out"):
        args.handler(args)

    assert client.requests == []


def test_work_order_list_does_not_send_offset(monkeypatch):
    client = FakeClient([{"items": [], "total": 0}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["work-orders", "list", "--limit", "10"])

    args.handler(args)

    assert client.requests[0]["query"] == {"limit": 10}


def test_defect_pull_vehicle_combines_pages_and_writes_out(monkeypatch, tmp_path):
    client = FakeClient(
        [
            {
                "items": [{"id": "FD-1", "reported_at": "2026-06-10T10:00:00Z"}],
                "total": 2,
                "page": 1,
                "per_page": 1,
                "keyset": True,
            },
            {
                "items": [{"id": "FD-2", "reported_at": "2026-06-11T10:00:00Z"}],
                "total": 1,
                "page": 1,
                "per_page": 1,
                "keyset": True,
            },
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    out = tmp_path / "defects.json"
    args = build_parser().parse_args(
        [
            "defects",
            "pull",
            "--vehicle",
            "VAN-0001",
            "--per-page",
            "1",
            "--out",
            str(out),
        ]
    )

    result = cmd_defect_pull(args)
    package = json.loads(out.read_text())

    assert result == {"ok": True, "out": str(out), "count": 2}
    assert package["vehicle_id"] == "VAN-0001"
    assert package["count"] == 2
    assert [item["id"] for item in package["defects"]] == ["FD-1", "FD-2"]
    assert [request["query"] for request in client.requests] == [
        {"per_page": 1, "vehicle_id": "VAN-0001", "page": 1, "reported_since": "0001-01-01T00:00:00Z", "after_id": 0},
        {"per_page": 1, "vehicle_id": "VAN-0001", "page": 1, "reported_since": "2026-06-10T10:00:00Z", "after_id": 1},
    ]


def test_defect_pull_new_missing_cursor_full_pull_and_advances(monkeypatch, tmp_path):
    client = FakeClient(
        [
            {
                "items": [
                    {"id": "FD-1", "reported_at": "2026-06-10T10:00:00Z"},
                    {"id": "FD-2", "reported_at": "2026-06-11T10:00:00Z"},
                ],
                "total": 2,
                "page": 1,
                "per_page": 50,
                "keyset": True,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    cursor = tmp_path / "cursor.json"
    args = build_parser().parse_args(["defect", "pull", "--new", "--cursor-file", str(cursor)])

    result = cmd_defect_pull(args)

    assert result["cursor_before"] is None
    assert result["cursor_after"] == {"reported_at": "2026-06-11T10:00:00Z", "id": "FD-2"}
    assert json.loads(cursor.read_text()) == {"reported_at": "2026-06-11T10:00:00Z", "id": "FD-2"}
    assert client.requests[0]["query"] == {"per_page": 50, "page": 1, "reported_since": "0001-01-01T00:00:00Z", "after_id": 0}


def test_defect_pull_new_filters_same_day_and_advances(monkeypatch, tmp_path):
    client = FakeClient(
        [
            {
                "items": [
                    {"id": "FD-1", "reported_at": "2026-06-10T10:00:00Z"},
                    {"id": "FD-2", "reported_at": "2026-06-10T10:00:01Z"},
                ],
                "total": 2,
                "page": 1,
                "per_page": 50,
                "keyset": True,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    cursor = tmp_path / "cursor.json"
    cursor.write_text(json.dumps({"reported_at": "2026-06-10T10:00:00Z"}))
    args = build_parser().parse_args(["defect", "pull", "--new", "--cursor-file", str(cursor)])

    result = cmd_defect_pull(args)

    assert [item["id"] for item in result["defects"]] == ["FD-1", "FD-2"]
    assert result["cursor_before"] == {"reported_at": "2026-06-10T10:00:00Z", "id": "FD-0"}
    assert result["cursor_after"] == {"reported_at": "2026-06-10T10:00:01Z", "id": "FD-2"}
    assert client.requests[0]["query"] == {
        "per_page": 50,
        "reported_since": "2026-06-10T10:00:00Z",
        "after_id": 0,
        "page": 1,
    }


def test_defect_pull_mode_is_required_and_mutually_exclusive():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["defect", "pull"])
    with pytest.raises(SystemExit):
        parser.parse_args(["defect", "pull", "--vehicle", "VAN-1", "--new"])


def test_work_order_wait_polls_until_target_status(monkeypatch):
    client = FakeClient(
        [
            {"id": "WO-1", "status": "in_progress"},
            {"id": "WO-1", "status": "completed"},
        ]
    )
    sleeps = []
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    monkeypatch.setattr(cli.time, "sleep", sleeps.append)
    args = build_parser().parse_args(
        ["work-order", "wait", "WO-1", "--until", "completed,canceled", "--interval", "5"]
    )

    result = cmd_work_order_wait(args)

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["polls"] == 2
    assert result["work_order"] == {"id": "WO-1", "status": "completed"}
    assert sleeps == [5.0]
    assert [request["path"] for request in client.requests] == [
        "/work-orders/WO-1",
        "/work-orders/WO-1",
    ]


def test_work_order_wait_times_out_with_exit_code_3(monkeypatch):
    client = FakeClient([{"id": "WO-1", "status": "reported"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)
    args = build_parser().parse_args(
        ["work-order", "wait", "WO-1", "--until", "completed", "--max-wait", "0"]
    )

    with pytest.raises(PollTimeout) as exc:
        cmd_work_order_wait(args)

    assert exc.value.exit_code == 3
    assert "reported" in str(exc.value)


def test_work_order_wait_rejects_empty_until():
    args = build_parser().parse_args(["work-order", "wait", "WO-1", "--until", " , "])

    with pytest.raises(cli.UsageError):
        cmd_work_order_wait(args)


def test_defect_catalog_sends_vehicle_class_and_dsp_scope(monkeypatch):
    client = FakeClient([{"parts": []}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "defect",
            "catalog",
            "--vehicle-class",
            "regular_cargo_van",
            "--dsp-id",
            "DSP-0001",
        ]
    )

    args.handler(args)

    assert client.requests[0] == {
        "method": "GET",
        "path": "/defect-catalog",
        "json_body": None,
        "query": {"vehicle_class": "regular_cargo_van", "dsp_id": "DSP-0001"},
    }


def test_defect_catalog_all_fetches_every_live_vehicle_class(monkeypatch):
    responses = [
        {"vehicle_class": vehicle_class, "parts": []}
        for vehicle_class in cli.DEFECT_CATALOG_VEHICLE_CLASSES
    ]
    client = FakeClient(responses)
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["defect", "catalog", "--all", "--dsp-id", "DSP-0001"])

    result = args.handler(args)

    assert result == {
        "source": "/v1/defect-catalog",
        "dsp_id": "DSP-0001",
        "vehicle_classes": {
            vehicle_class: {"vehicle_class": vehicle_class, "parts": []}
            for vehicle_class in cli.DEFECT_CATALOG_VEHICLE_CLASSES
        },
    }
    assert [request["query"] for request in client.requests] == [
        {"vehicle_class": vehicle_class, "dsp_id": "DSP-0001"}
        for vehicle_class in cli.DEFECT_CATALOG_VEHICLE_CLASSES
    ]


def test_defect_catalog_requires_exactly_one_scope():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["defect", "catalog"])
    with pytest.raises(SystemExit):
        parser.parse_args(["defect", "catalog", "--all", "--vehicle-class", "regular_cargo_van"])


def test_work_order_line_items_list_extracts_embedded_field(monkeypatch):
    client = FakeClient([{"id": "WO-1", "line_items": [{"id": 10}]}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["work-order", "line-items", "list", "WO-1"])

    result = cmd_work_order_line_items_list(args)

    assert result == [{"id": 10}]
    assert client.requests[0]["path"] == "/work-orders/WO-1"


def test_defect_photos_download_into_one_folder_per_defect(tmp_path):
    from nova_cli_public.legacy_reads import download_defect_photos

    class Client:
        def request(self, method, path, **kwargs):
            assert (method, path) == ("GET", "/defects/FD-8125/photos")
            return {
                "items": [
                    {
                        "id": "PH-1",
                        "url": "https://files.example.test/a.jpg?sig=x",
                        "content_type": "image/jpeg",
                    },
                    {
                        "id": "../evil",
                        "url": "https://files.example.test/b.jpg",
                        "content_type": "image/jpeg",
                    },
                ]
            }

    fetched = []
    result = download_defect_photos(
        Client(), ["FD-8125"], tmp_path, fetch=lambda url: fetched.append(url) or b"jpegbytes"
    )
    assert result["count"] == 1
    assert (tmp_path / "FD-8125" / "PH-1.jpg").read_bytes() == b"jpegbytes"
    assert fetched == ["https://files.example.test/a.jpg?sig=x"]


def test_defect_photos_refuse_plain_http():
    import pytest

    from nova_cli_public.errors import UsageError
    from nova_cli_public.legacy_reads import fetch_presigned

    with pytest.raises(UsageError):
        fetch_presigned("http://files.example.test/a.jpg")


@pytest.mark.parametrize("size", [26 * 1024 * 1024, 50 * 1024 * 1024, 50 * 1024 * 1024 + 1])
def test_photo_download_matches_api_size_limit(monkeypatch, size):
    import urllib.request

    data = b"x" * size
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        lambda *a: __import__("types").SimpleNamespace(open=lambda *a, **kw: io.BytesIO(data)),
    )
    if size > 50 * 1024 * 1024:
        with pytest.raises(UsageError, match="larger than the download limit"):
            cli.fetch_presigned("https://storage.test/photo")
    else:
        assert cli.fetch_presigned("https://storage.test/photo") == data
