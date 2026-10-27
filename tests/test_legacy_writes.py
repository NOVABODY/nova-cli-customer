"""Legacy customer mutation payload regressions reused from pinned tree c2298bbf."""

import json

import pytest

from nova_cli_public import legacy_writes as cli
from nova_cli_public.cli import build_parser
from nova_cli_public.config import Profile
from nova_cli_public.errors import UsageError
from nova_cli_public.legacy_writes import build_body, cmd_work_order_line_items_update, parse_pairs


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


def test_parse_pairs_json_values():
    assert parse_pairs(["a=1", "b=true", "c=null", "d=text"]) == {
        "a": 1,
        "b": True,
        "c": None,
        "d": "text",
    }


def test_build_body_data():
    assert build_body(json.dumps({"language": "es"}), None, []) == {"language": "es"}


def test_notification_read_normalizes_documented_prefixed_id(monkeypatch):
    client = FakeClient([{"id": 42, "read_at": "2026-07-13T12:00:00Z"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["notification", "read", "NOTIF-00042"])

    args.handler(args)

    assert client.requests[0]["method"] == "PATCH"
    assert client.requests[0]["path"] == "/notifications/42/read"


@pytest.mark.parametrize("notification_id", ["NOTIF-nope", "0", "NOTIF-00000"])
def test_notification_read_rejects_invalid_ids(monkeypatch, notification_id):
    client = FakeClient([])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["notification", "read", notification_id])

    with pytest.raises(UsageError):
        args._client = client
        args.handler(args)

    assert client.requests == []


def test_notification_preferences_use_current_contract(monkeypatch, tmp_path):
    payload = {
        "preferences": [
            {
                "notification_type_key": "work_order_status",
                "email": True,
                "sms": False,
                "browser_push": True,
            }
        ]
    }
    data_file = tmp_path / "preferences.json"
    data_file.write_text(json.dumps(payload))
    client = FakeClient([{"groups": []}, {"groups": []}, {"groups": []}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)

    for argv in (
        ["notification", "preferences"],
        ["notification", "update-preferences", "--data-file", str(data_file)],
        ["notification", "turn-off-optional-delivery"],
    ):
        args = build_parser().parse_args(argv)
        args._client = client
        args.handler(args)

    assert client.requests == [
        {
            "method": "GET",
            "path": "/notifications/preferences",
            "json_body": None,
            "query": None,
        },
        {
            "method": "PUT",
            "path": "/notifications/preferences",
            "json_body": payload,
            "query": None,
        },
        {
            "method": "PUT",
            "path": "/notifications/preferences",
            "json_body": {"turn_off_all": True},
            "query": None,
        },
    ]


def test_vehicle_checkout_requires_workshop():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["vehicle", "check-out", "VAN-00042"])


def test_vehicle_checkin_requires_mileage_but_allows_role_optional_photos(monkeypatch):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["vehicle", "check-in", "VAN-00042"])

    client = FakeClient([{"id": "VCO-1", "status": "checked_in"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle", "check-in", "VAN-00042", "--mileage", "12370"])

    args.handler(args)

    assert client.requests[0]["json_body"] == {"mileage": 12370}


def test_vehicle_checkout_enforces_selected_evidence_contract(monkeypatch):
    client = FakeClient([{"id": "VCO-1"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)

    missing_photos = build_parser().parse_args(
        [
            "vehicle",
            "check-out",
            "VAN-00042",
            "--vendor-workshop-id",
            "VW-3",
            "--mileage",
            "12345",
        ]
    )
    with pytest.raises(UsageError, match="photo evidence"):
        missing_photos.handler(missing_photos)

    full_inspection = build_parser().parse_args(
        [
            "vehicle",
            "check-out",
            "VAN-00042",
            "--vendor-workshop-id",
            "VW-3",
            "--evidence-mode",
            "full_inspection",
            "--inspection-id",
            "19",
        ]
    )
    full_inspection.handler(full_inspection)

    assert client.requests == [
        {
            "method": "POST",
            "path": "/vehicles/VAN-00042/check-out",
            "json_body": {
                "vendor_workshop_id": "VW-3",
                "evidence_mode": "full_inspection",
                "inspection_id": 19,
            },
            "query": None,
        }
    ]


def test_vehicle_checkin_sends_strict_backend_body(monkeypatch):
    client = FakeClient([{"id": "VCO-1", "status": "checked_in"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    photos = '[{"storage_key":"photos/vehicle_checkouts/42/a.jpg","content_type":"image/jpeg","size_bytes":10}]'
    args = build_parser().parse_args(
        [
            "vehicle",
            "check-in",
            "VAN-00042",
            "--mileage",
            "12370",
            "--field",
            f"photos={photos}",
        ]
    )

    args.handler(args)

    assert client.requests[0]["json_body"] == {
        "mileage": 12370,
        "photos": [
            {
                "storage_key": "photos/vehicle_checkouts/42/a.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 10,
            }
        ],
    }


def test_vehicle_report_create_sends_named_fields_and_file_objects(monkeypatch, tmp_path):
    reporter = tmp_path / "reporter.json"
    reporter.write_text(json.dumps({"display_name": "Driver Dana", "email": "d@example.test"}))
    raw_payload = tmp_path / "raw.json"
    raw_payload.write_text(json.dumps({"rowriter": {"ro": "12345"}}))
    client = FakeClient([{"id": "VR-00042", "status": "pending"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "vehicle-report",
            "create",
            "--external-ref",
            "rowriter:12345:line-2",
            "--vehicle-id",
            "VAN-00042",
            "--fleet-id",
            "D-42",
            "--plate",
            "ABC123",
            "--description",
            "Grinding at left front wheel",
            "--source",
            "shop_finding",
            "--reported-via",
            "api",
            "--mileage-at-report",
            "84213",
            "--reporter-file",
            str(reporter),
            "--raw-payload-file",
            str(raw_payload),
        ]
    )

    result = args.handler(args)

    assert result["id"] == "VR-00042"
    assert client.requests == [
        {
            "method": "POST",
            "path": "/vehicle-reports",
            "json_body": {
                "external_ref": "rowriter:12345:line-2",
                "vehicle_id": "VAN-00042",
                "fleet_id": "D-42",
                "plate": "ABC123",
                "description": "Grinding at left front wheel",
                "source": "shop_finding",
                "reported_via": "api",
                "mileage_at_report": 84213,
                "reporter": {"display_name": "Driver Dana", "email": "d@example.test"},
                "raw_payload": {"rowriter": {"ro": "12345"}},
            },
            "query": None,
        }
    ]


def test_vehicle_report_create_accepts_complete_json_file(monkeypatch, tmp_path):
    body_file = tmp_path / "report.json"
    body_file.write_text(
        json.dumps(
            {
                "external_ref": "rowriter:12345",
                "description": "Driver reported a vibration",
                "reporter": {"display_name": "Driver Dana"},
                "raw_payload": {"original": True},
            }
        )
    )
    client = FakeClient([{"id": "VR-00043"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle-report", "create", "--data-file", str(body_file)])

    args.handler(args)

    assert client.requests[0]["json_body"] == json.loads(body_file.read_text())


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"description": "   "},
        {"description": "x", "mileage_at_report": -1},
        {"description": "x", "mileage_at_report": True},
        {"description": "x", "reporter": []},
        {"description": "x", "reporter": {"unknown": "field"}},
        {"description": "x", "unexpected": "field"},
    ],
)
def test_vehicle_report_create_rejects_invalid_body_without_request(monkeypatch, body):
    client = FakeClient([])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(["vehicle-report", "create", "--data", json.dumps(body)])

    with pytest.raises(UsageError):
        args._client = client
        args.handler(args)

    assert client.requests == []


def test_vehicle_report_create_rejects_mixed_body_styles(monkeypatch):
    client = FakeClient([])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "vehicle-report",
            "create",
            "--data",
            '{"description":"from JSON"}',
            "--description",
            "from flag",
        ]
    )

    with pytest.raises(UsageError, match="not both"):
        args._client = client
        args.handler(args)


def test_work_order_decline_requires_backend_reason_code():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["work-order", "decline", "WO-00042"])


def test_retired_work_order_actions_are_not_exposed():
    parser = build_parser()

    for action in ("start", "ready-to-schedule"):
        with pytest.raises(SystemExit):
            parser.parse_args(["work-order", action, "WO-00042"])


def test_current_work_order_actions_send_contracted_bodies(monkeypatch):
    client = FakeClient([{"id": "WO-42"}] * 4)
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    commands = [
        ["work-order", "accept", "WO-42", "--ro-number", "RO-900"],
        [
            "work-order",
            "complete",
            "WO-42",
            "--last-mileage",
            "12345",
            "--confirmed-mileage-floor",
            "12300",
        ],
        ["work-order", "unschedule", "WO-42", "--reason", "Customer changed date"],
        ["work-order", "release", "WO-42", "--reason", "No qualified bay"],
    ]

    for argv in commands:
        args = build_parser().parse_args(argv)
        args._client = client
        args.handler(args)

    assert [request["path"] for request in client.requests] == [
        "/work-orders/WO-42/accept",
        "/work-orders/WO-42/complete",
        "/work-orders/WO-42/unschedule",
        "/work-orders/WO-42/release",
    ]
    assert client.requests[0]["json_body"] == {"ro_number": "RO-900"}
    assert client.requests[1]["json_body"] == {
        "last_mileage": 12345,
        "confirmed_mileage_floor": 12300,
    }
    assert client.requests[2]["json_body"] == {"reason": "Customer changed date"}


def test_work_order_delay_reason_uses_current_route(monkeypatch):
    client = FakeClient([{"code": "parts_backorder"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "work-order",
            "add-delay-reason",
            "WO-42",
            "FD-9",
            "--code",
            "parts_backorder",
            "--reason",
            "Part arrives Friday",
        ]
    )

    args.handler(args)

    assert client.requests[0] == {
        "method": "POST",
        "path": "/work-orders/WO-42/defects/FD-9/delay-reasons",
        "json_body": {"code": "parts_backorder", "reason": "Part arrives Friday"},
        "query": None,
    }


def test_work_order_create_posts_manual_endpoint_body(monkeypatch):
    client = FakeClient([{"id": "WO-77", "status": "reported"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "work-order",
            "create",
            "--vehicle-id",
            "VAN-00042",
            "--part",
            "brakes",
            "--defect-type",
            "worn",
            "--position",
            "front",
            "--description",
            "Grinding from front brakes",
            "--service-station-code",
            "DDC4",
            "--reason-code",
            "customer_requested",
            "--vendor-workshop-id",
            "3",
            "--rush",
        ]
    )

    result = cli.cmd_work_order_create(args)

    assert result == {"id": "WO-77", "status": "reported"}
    assert client.requests[0] == {
        "method": "POST",
        "path": "/work-orders/manual",
        "json_body": {
            "vehicle_id": "VAN-00042",
            "part": "brakes",
            "defect_type": "worn",
            "position": "front",
            "description": "Grinding from front brakes",
            "service_station_code": "DDC4",
            "reason_code": "customer_requested",
            "vendor_workshop_id": "3",
            "is_rush": True,
        },
        "query": None,
    }


def test_work_order_create_omits_optional_fields(monkeypatch):
    client = FakeClient([{"id": "WO-78"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "work-order",
            "create",
            "--vehicle-id",
            "VAN-00001",
            "--part",
            "tires",
            "--defect-type",
            "flat",
        ]
    )

    cli.cmd_work_order_create(args)

    assert client.requests[0]["json_body"] == {
        "vehicle_id": "VAN-00001",
        "part": "tires",
        "defect_type": "flat",
        "reason_code": "newly_discovered",
    }
    assert "service_station_code" not in client.requests[0]["json_body"]


def test_work_order_line_item_update_sends_only_provided_fields(monkeypatch):
    client = FakeClient([{"id": 10, "status": "done"}])
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "work-orders",
            "line-items",
            "update",
            "WO-1",
            "10",
            "--title",
            "Marker light",
            "--status",
            "done",
            "--final-price",
            "12.34",
        ]
    )

    cmd_work_order_line_items_update(args)

    assert client.requests[0]["method"] == "PATCH"
    assert client.requests[0]["path"] == "/work-orders/WO-1/line-items/10"
    assert client.requests[0]["json_body"] == {
        "title": "Marker light",
        "final_price": "12.34",
        "status": "done",
    }


def test_upload_photo_presigns_and_puts_bytes(monkeypatch, tmp_path):
    photo_file = tmp_path / "odometer.jpg"
    photo_file.write_bytes(b"jpeg-bytes")
    client = FakeClient(
        [
            {
                "upload_url": "http://storage.test/put/photos/work_orders/42/key.jpg",
                "storage_key": "photos/work_orders/42/key.jpg",
                "expires_in": 300,
            }
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        ["upload", "photo", str(photo_file), "--kind", "work_order", "--parent-id", "WO-00042"]
    )

    result = cli.cmd_upload_photo(args)

    assert client.requests[0] == {
        "method": "POST",
        "path": "/uploads/presigned",
        "json_body": {
            "kind": "work_order",
            "parent_id": "WO-00042",
            "filename": "odometer.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 10,
        },
        "query": None,
    }
    assert client.uploads == [
        {
            "url": "http://storage.test/put/photos/work_orders/42/key.jpg",
            "data": b"jpeg-bytes",
            "content_type": "image/jpeg",
        }
    ]
    assert result["storage_key"] == "photos/work_orders/42/key.jpg"
    assert result["committed"] is False


def test_upload_photo_commit_posts_defect_photo(monkeypatch, tmp_path):
    photo_file = tmp_path / "damage.png"
    photo_file.write_bytes(b"png-bytes")
    client = FakeClient(
        [
            {
                "upload_url": "http://storage.test/put/photos/defects/7/key.png",
                "storage_key": "photos/defects/7/key.png",
                "expires_in": 300,
            },
            {"id": 99, "category": "damage"},
        ]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _args: client)
    args = build_parser().parse_args(
        [
            "upload",
            "photo",
            str(photo_file),
            "--kind",
            "defect",
            "--parent-id",
            "FD-00007",
            "--commit",
            "--category",
            "damage",
        ]
    )

    result = cli.cmd_upload_photo(args)

    assert client.requests[1] == {
        "method": "POST",
        "path": "/defects/FD-00007/photos",
        "json_body": {
            "storage_key": "photos/defects/7/key.png",
            "content_type": "image/png",
            "size_bytes": 9,
            "category": "damage",
        },
        "query": None,
    }
    assert result["committed"] is True
    assert result["photo"] == {"id": 99, "category": "damage"}


def test_upload_photo_commit_rejects_unsupported_kind(tmp_path):
    photo_file = tmp_path / "photo.jpg"
    photo_file.write_bytes(b"jpeg-bytes")
    args = build_parser().parse_args(
        [
            "upload",
            "photo",
            str(photo_file),
            "--kind",
            "work_order",
            "--parent-id",
            "WO-1",
            "--commit",
        ]
    )

    with pytest.raises(cli.UsageError):
        cli.cmd_upload_photo(args)


def test_upload_photo_requires_guessable_content_type(tmp_path):
    photo_file = tmp_path / "photo.unknownext"
    photo_file.write_bytes(b"bytes")
    args = build_parser().parse_args(
        ["upload", "photo", str(photo_file), "--kind", "defect", "--parent-id", "FD-1"]
    )

    with pytest.raises(cli.UsageError):
        cli.cmd_upload_photo(args)


@pytest.mark.parametrize(
    "kind",
    [
        "grounding",
        "vehicle_report",
        "unlisted_vehicle_report",
        "body_repair_pave_preview",
        "body_repair_issue_photo_preview",
        "body_repair_message_photo",
    ],
)
def test_upload_supports_current_api_kinds(monkeypatch, tmp_path, kind):
    photo = tmp_path / ("evidence.pdf" if kind == "body_repair_pave_preview" else "photo.png")
    photo.write_bytes(b"evidence")
    client = FakeClient(
        [{"upload_url": "https://storage.test/upload", "storage_key": "key"}, {"id": "PH-1"}]
    )
    monkeypatch.setattr(cli, "client_from_args", lambda _: client)
    argv = ["upload", "photo", str(photo), "--kind", kind, "--parent-id", "1"]
    if kind == "vehicle_report":
        argv.append("--commit")
    args = build_parser().parse_args(argv)
    result = args.handler(args)
    assert client.requests[0]["json_body"]["kind"] == kind
    assert client.uploads[0]["data"] == b"evidence"
    assert result["committed"] == (kind == "vehicle_report")
    if kind == "vehicle_report":
        assert client.requests[1]["path"] == "/vehicle-reports/1/photos"
        assert client.requests[1]["json_body"]["storage_key"] == "key"
