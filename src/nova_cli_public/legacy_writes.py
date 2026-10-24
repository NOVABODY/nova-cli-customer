"""Customer mutation handlers extracted from legacy tree c2298bbf.

Existing payload and workflow validation is retained. The public client admits
only named customer operations and never retries a mutation automatically.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.legacy_reads import (
    clean_query,
    client_from_args,
    vars_to_query,
)

PHOTO_COMMIT_PATHS = {
    "vehicle_report": "/vehicle-reports/{parent_id}/photos",
    "defect": "/defects/{parent_id}/photos",
    "inspection": "/inspections/{parent_id}/photos",
}

VEHICLE_REPORT_CREATE_FIELDS = {
    "external_ref",
    "vehicle_id",
    "fleet_id",
    "plate",
    "description",
    "source",
    "reported_via",
    "mileage_at_report",
    "reporter",
    "raw_payload",
}

VEHICLE_REPORT_PROMOTE_FIELDS = {"part", "position", "defect_type", "details", "notes"}

VEHICLE_REPORT_REPORTED_VIA = ("slack", "web", "api")

VEHICLE_REPORT_REPORTER_FIELDS = {"slack_team_id", "slack_user_id", "email", "display_name"}


def cmd_upload_photo(args: argparse.Namespace) -> Any:
    path = Path(args.file).expanduser()
    if not path.is_file():
        raise UsageError(f"File not found: {path}")
    if args.commit and args.kind not in PHOTO_COMMIT_PATHS:
        supported = ", ".join(sorted(PHOTO_COMMIT_PATHS))
        raise UsageError(
            f"--commit supports kinds: {supported}. For other kinds, pass the returned storage_key to the relevant endpoint, for example `work-order complete --field odometer_photo_path=KEY`."
        )
    content_type = args.content_type or mimetypes.guess_type(path.name)[0]
    if not content_type:
        raise UsageError(f"Could not guess a MIME type for {path.name}; pass --content-type.")
    if path.stat().st_size > 50 * 1024 * 1024:
        raise UsageError("Photo exceeds 50 MiB.")
    with path.open("rb") as stream:
        data = stream.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise UsageError("Photo exceeds 50 MiB.")
    if not data:
        raise UsageError(f"File is empty: {path}")
    client = client_from_args(args)
    presign = client.request(
        "POST",
        "/uploads/presigned",
        json_body={
            "kind": args.kind,
            "parent_id": args.parent_id,
            "filename": path.name,
            "content_type": content_type,
            "size_bytes": len(data),
        },
    )
    if not isinstance(presign, dict):
        raise ApiError("API response did not include a presigned upload object")
    upload_url = presign.get("upload_url")
    storage_key = presign.get("storage_key")
    if not isinstance(upload_url, str) or not upload_url:
        raise ApiError("API response did not include upload_url")
    if not isinstance(storage_key, str) or not storage_key:
        raise ApiError("API response did not include storage_key")
    client.put_bytes(upload_url, data, content_type=content_type)
    result: dict[str, Any] = {
        "ok": True,
        "kind": args.kind,
        "parent_id": args.parent_id,
        "storage_key": storage_key,
        "content_type": content_type,
        "size_bytes": len(data),
        "committed": False,
    }
    if args.commit:
        commit_path = PHOTO_COMMIT_PATHS[args.kind].format(parent_id=args.parent_id)
        commit_body = clean_query(
            {
                "storage_key": storage_key,
                "content_type": content_type,
                "size_bytes": len(data),
                "category": args.category,
            }
        )
        result["photo"] = client.request("POST", commit_path, json_body=commit_body)
        result["committed"] = True
    return result


def post_work_order_action(args: argparse.Namespace) -> Any:
    body = parse_pairs(args.field)
    named_fields = {
        "accept": ["ro_number"],
        "complete": [
            "last_mileage",
            "odometer_photo_path",
            "work_photo_path",
            "override_reason",
            "confirmed_mileage_floor",
        ],
        "cancel": ["reason"],
    }[args.action_name]
    body.update(vars_to_query(args, named_fields))
    if args.action_name == "complete" and "last_mileage" not in body:
        raise UsageError("Work-order completion requires --last-mileage.")
    return client_from_args(args).request(
        "POST", f"/work-orders/{args.wo_id}/{args.action_name}", json_body=body
    )


def assignment_body(args: argparse.Namespace) -> dict[str, Any]:
    body = {}
    for name in ("team", "technician"):
        value = getattr(args, f"{name}_id")
        if getattr(args, f"clear_{name}"):
            body[f"{name}_id"] = None
        elif value is not None:
            body[f"{name}_id"] = value
    return body


def cmd_work_order_assignment(args: argparse.Namespace) -> Any:
    body = assignment_body(args)
    if not body:
        raise UsageError(
            "Provide an assignment field or an explicit --clear-team/--clear-technician."
        )
    return client_from_args(args).request(
        "POST", f"/work-orders/{args.wo_id}/assignment", json_body=body
    )


def cmd_work_order_schedule(args: argparse.Namespace) -> Any:
    body = assignment_body(args)
    if args.scheduled_at is not None:
        try:
            slot = datetime.fromisoformat(args.scheduled_at)
        except ValueError as exc:
            raise UsageError(
                "--scheduled-at must be ISO 8601 with an explicit UTC offset."
            ) from exc
        if slot.tzinfo is None or slot.utcoffset() is None:
            raise UsageError("--scheduled-at requires an explicit UTC offset (organization DST).")
        body["scheduled_at"] = args.scheduled_at
    if args.clear_repair_bucket:
        body["repair_bucket"] = None
    elif args.repair_bucket is not None:
        body["repair_bucket"] = args.repair_bucket
    if args.ro_number is not None:
        if not args.ro_number.strip() or len(args.ro_number) > 60:
            raise UsageError("--ro-number must be nonblank and at most 60 characters.")
        body["ro_number"] = args.ro_number.strip()
    selected = {}
    for kind in ("include", "exclude"):
        values = getattr(args, f"{kind}_defect_id", None) or []
        if (
            len(values) > 100
            or any(type(value) is not int or not 1 <= value <= 2147483647 for value in values)
            or len(set(values)) != len(values)
        ):
            raise UsageError("Use 100 or fewer different positive numeric defect IDs in each list. / Usa hasta 100 ID numéricos positivos diferentes por lista.")
        selected[kind] = values
        if values:
            body[f"{kind}_defect_ids"] = values
    if set(selected["include"]) & set(selected["exclude"]):
        raise UsageError("Do not add and remove the same defect. / No añadas y elimines el mismo defecto.")
    if not body:
        raise UsageError("Provide a schedule field; omitted fields are preserved.")
    return client_from_args(args).request(
        "POST", f"/work-orders/{args.wo_id}/schedule", json_body=body
    )


def cmd_work_order_reason_action(args: argparse.Namespace) -> Any:
    reason = require_cli_text(args.reason, "--reason")
    if len(reason) < 3:
        raise UsageError("--reason must contain at least 3 characters.")
    return client_from_args(args).request(
        "POST", f"/work-orders/{args.wo_id}/{args.action_name}", json_body={"reason": reason}
    )


def cmd_work_order_add_delay_reason(args: argparse.Namespace) -> Any:
    return client_from_args(args).request(
        "POST",
        f"/work-orders/{args.wo_id}/defects/{args.defect_id}/delay-reasons",
        json_body={"code": args.code, "reason": require_cli_text(args.reason, "--reason")},
    )


def cmd_work_order_decline(args: argparse.Namespace) -> Any:
    body = {
        "decline_reason_code": args.decline_reason_code,
        "reason": args.reason,
        "reroute": not args.no_reroute,
    }
    return client_from_args(args).request(
        "POST", f"/work-orders/{args.wo_id}/decline", json_body=clean_query(body)
    )


def cmd_work_order_create(args: argparse.Namespace) -> Any:
    body = clean_query(
        {
            "vehicle_id": args.vehicle_id,
            "service_station_code": args.service_station_code,
            "part": args.part,
            "defect_type": args.defect_type,
            "position": args.position,
            "description": args.description,
            "reason_code": args.reason_code,
            "vendor_workshop_id": args.vendor_workshop_id,
            "ro_number": args.ro_number,
            "is_rush": args.rush or None,
        }
    )
    return client_from_args(args).request("POST", "/work-orders/manual", json_body=body)


def cmd_work_order_line_items_update(args: argparse.Namespace) -> Any:
    body = clean_query(
        {
            "title": args.title,
            "description": args.description,
            "estimated_price": args.estimated_price,
            "final_price": args.final_price,
            "billing_type": args.billing_type,
            "ro_id": args.ro_id,
            "status": args.status,
            "status_reason": args.status_reason,
            "decline_reason_code": args.decline_reason_code,
        }
    )
    if not body:
        raise UsageError("Provide at least one line-item field to update.")
    return client_from_args(args).request(
        "PATCH", f"/work-orders/{args.wo_id}/line-items/{args.line_item_id}", json_body=body
    )


def cmd_notification_read(args: argparse.Namespace) -> Any:
    notification_id = parse_notification_id(args.notification_id)
    return client_from_args(args).request("PATCH", f"/notifications/{notification_id}/read")


def cmd_notification_update_preferences(args: argparse.Namespace) -> Any:
    body = build_body(args.data, args.data_file, [])
    if not body:
        raise UsageError("Provide --data or --data-file with notification preferences.")
    validate_exact_fields(body, {"preferences", "turn_off_all"}, "notification update-preferences")
    return client_from_args(args).request("PUT", "/notifications/preferences", json_body=body)


def cmd_defect_create(args: argparse.Namespace) -> Any:
    fields = (
        "vehicle_id",
        "source",
        "part",
        "defect_type",
        "position",
        "inspection_id",
        "notes",
        "reported_at",
        "vendor_workshop_id",
        "external_vendor_id",
        "dsp_contact_user_id",
        "service_station_code",
    )
    body = clean_query({key: getattr(args, key) for key in fields})
    for field, limit in (
        ("part", 40),
        ("defect_type", 40),
        ("position", 30),
        ("notes", 2000),
        ("service_station_code", 20),
    ):
        if field in body and len(require_nonblank_string(body, field, "Reporting")) > limit:
            raise UsageError(f"{field} exceeds {limit} characters.")
    if (args.source == "inspection") != bool(args.inspection_id):
        raise UsageError("Use inspection_id only with source inspection.")
    if args.dsp_contact_user_id is not None and args.external_vendor_id is None:
        raise UsageError("DSP contact requires an external vendor.")
    if args.details is not None:
        if len(args.details.encode("utf-8")) > 65536:
            raise UsageError("Defect details exceed 64 KiB.")
        try:
            details = json.loads(args.details)
            json.dumps(details, allow_nan=False)
        except ValueError as exc:
            raise UsageError("Defect details must be a JSON object.") from exc
        if not isinstance(details, dict):
            raise UsageError("Defect details must be a JSON object.")
        body["details"] = details
    value = client_from_args(args).request("POST", "/defects", json_body=body)
    if (not isinstance(value, dict)
            or not re.fullmatch(r"FD-[0-9]{1,100}", str(value.get("id", ""))) or int(value["id"][3:]) < 1
            or not re.fullmatch(r"VAN-[0-9]{1,100}", str(value.get("vehicle_id", "")))
            or int(value["vehicle_id"][4:]) != int(body["vehicle_id"].split("-")[-1])
            or value.get("part") != body["part"].lower() or value.get("defect_type") != body["defect_type"].lower()):
        raise ApiError("The report outcome is unknown. Read the vehicle defects before another attempt.",
                       code="outcome_unknown")
    return value


def cmd_defect_update(args: argparse.Namespace) -> Any:
    if not args.title.strip() or len(args.title) > 120:
        raise UsageError("--title must be nonblank and at most 120 characters.")
    body = {"display_title": args.title.strip()}
    if args.expected_updated_at is not None:
        try:
            expected = datetime.fromisoformat(args.expected_updated_at)
        except ValueError as exc:
            raise UsageError("--expected-updated-at must be an aware ISO 8601 timestamp.") from exc
        if expected.tzinfo is None or expected.utcoffset() is None:
            raise UsageError("--expected-updated-at must include an explicit UTC offset.")
        body["expected_updated_at"] = args.expected_updated_at
    return client_from_args(args).request("PATCH", f"/defects/{args.defect_id}", json_body=body)


def cmd_vehicle_add_note(args: argparse.Namespace) -> Any:
    body = {"body": args.body, "vendor_workshop_id": args.vendor_workshop_id}
    return client_from_args(args).request(
        "POST", f"/vehicles/{args.vehicle_id}/notes", json_body=clean_query(body)
    )


def cmd_vehicle_custody(args: argparse.Namespace) -> Any:
    body = parse_pairs(args.field)
    body.update(
        clean_query(
            {
                "mileage": args.mileage,
                "vendor_workshop_id": getattr(args, "vendor_workshop_id", None),
                "evidence_mode": getattr(args, "evidence_mode", None),
                "inspection_id": getattr(args, "inspection_id", None),
                "confirmed_mileage_floor": getattr(args, "confirmed_mileage_floor", None),
            }
        )
    )
    if args.action_name == "check-out":
        if body["evidence_mode"] == "mileage_and_photos":
            if "mileage" not in body:
                raise UsageError("Mileage-and-photos check-out requires --mileage.")
            if not (isinstance(body.get("photos"), list) and body["photos"]):
                raise UsageError(
                    "Mileage-and-photos check-out requires photo evidence; pass `--field 'photos=[{...}]'` using the metadata from `nova upload photo`."
                )
        elif "inspection_id" not in body:
            raise UsageError("Full-inspection check-out requires --inspection-id.")
    return client_from_args(args).request(
        "POST", f"/vehicles/{args.vehicle_id}/{args.action_name}", json_body=body
    )


def cmd_vehicle_report_create(args: argparse.Namespace) -> Any:
    direct_fields = clean_query(
        {
            "external_ref": args.external_ref,
            "vehicle_id": args.vehicle_id,
            "fleet_id": args.fleet_id,
            "plate": args.plate,
            "description": args.description,
            "source": args.source,
            "reported_via": args.reported_via,
            "mileage_at_report": args.mileage_at_report,
        }
    )
    file_fields = [args.reporter_file, args.raw_payload_file]
    if (args.data or args.data_file) and (direct_fields or any(file_fields)):
        raise UsageError(
            "Use either --data/--data-file or the named vehicle-report fields, not both."
        )
    if sum(value == "-" for value in [args.data_file, *file_fields]) > 1:
        raise UsageError("Only one vehicle-report input may read from stdin.")
    body = build_body(args.data, args.data_file, [])
    if not (args.data or args.data_file):
        body = direct_fields
        if args.reporter_file:
            body["reporter"] = read_json_object_file(args.reporter_file, "reporter")
        if args.raw_payload_file:
            body["raw_payload"] = read_json_object_file(args.raw_payload_file, "raw payload")
    validate_exact_fields(body, VEHICLE_REPORT_CREATE_FIELDS, "vehicle-report create")
    require_nonblank_string(body, "description", "Vehicle report")
    reported_via = body.get("reported_via")
    if reported_via is not None and reported_via not in VEHICLE_REPORT_REPORTED_VIA:
        raise UsageError(f"reported_via must be one of: {', '.join(VEHICLE_REPORT_REPORTED_VIA)}")
    mileage = body.get("mileage_at_report")
    if mileage is not None and (
        not isinstance(mileage, int)
        or isinstance(mileage, bool)
        or mileage < 0
        or (mileage > 2000000)
    ):
        raise UsageError("mileage_at_report must be an integer from 0 through 2000000.")
    for field in ("reporter", "raw_payload"):
        if body.get(field) is not None and (not isinstance(body[field], dict)):
            raise UsageError(f"{field} must be a JSON object.")
    if isinstance(body.get("reporter"), dict):
        validate_exact_fields(body["reporter"], VEHICLE_REPORT_REPORTER_FIELDS, "reporter")
    return client_from_args(args).request("POST", "/vehicle-reports", json_body=body)


def cmd_vehicle_report_resolve_vehicle(args: argparse.Namespace) -> Any:
    return client_from_args(args).request(
        "POST",
        f"/vehicle-reports/{args.report_id}/resolve-vehicle",
        json_body={"vehicle_id": require_cli_text(args.vehicle_id, "vehicle_id")},
    )


def cmd_vehicle_report_promote(args: argparse.Namespace) -> Any:
    direct_fields = clean_query(
        {
            "part": args.part,
            "position": args.position,
            "defect_type": args.defect_type,
            "notes": args.notes,
        }
    )
    if (args.data or args.data_file) and (direct_fields or args.details_file):
        raise UsageError("Use either --data/--data-file or the named promotion fields, not both.")
    if args.data_file == "-" and args.details_file == "-":
        raise UsageError("Only one promotion input may read from stdin.")
    body = build_body(args.data, args.data_file, [])
    if not (args.data or args.data_file):
        body = direct_fields
        if args.details_file:
            body["details"] = read_json_object_file(args.details_file, "details")
    validate_exact_fields(body, VEHICLE_REPORT_PROMOTE_FIELDS, "vehicle-report promote")
    require_nonblank_string(body, "part", "Promotion")
    require_nonblank_string(body, "defect_type", "Promotion")
    if body.get("details") is not None and (not isinstance(body["details"], dict)):
        raise UsageError("details must be a JSON object.")
    return client_from_args(args).request(
        "POST", f"/vehicle-reports/{args.report_id}/promote", json_body=body
    )


def cmd_vehicle_report_dismiss(args: argparse.Namespace) -> Any:
    return client_from_args(args).request(
        "POST",
        f"/vehicle-reports/{args.report_id}/dismiss",
        json_body={"reason": require_cli_text(args.reason, "reason")},
    )


def build_body(data: str | None, data_file: str | None, fields: list[str]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    sources = [bool(data), bool(data_file), bool(fields)]
    if sum(1 for present in sources if present) > 1:
        raise UsageError("Use only one of --data, --data-file, or --field.")
    if data:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise UsageError(f"--data is not valid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise UsageError("--data must decode to a JSON object")
        return parsed
    if data_file:
        try:
            text = (
                sys.stdin.read()
                if data_file == "-"
                else Path(data_file).read_text(encoding="utf-8")
            )
        except OSError as exc:
            raise UsageError(f"Could not read JSON body from {data_file}: {exc}") from exc
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UsageError(f"--data-file is not valid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise UsageError("--data-file must decode to a JSON object")
        return parsed
    if fields:
        return parse_pairs(fields)
    return body


def parse_pairs(values: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise UsageError(f"Expected key=value, got {value!r}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise UsageError("Field key cannot be empty")
        parsed[key] = parse_value(raw)
    return parsed


def parse_value(value: str) -> Any:
    raw = value.strip()
    if raw in {"true", "false"}:
        return raw == "true"
    if raw == "null":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return value


def parse_decimal_arg(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise argparse.ArgumentTypeError("value cannot be empty")
    try:
        float(stripped)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be numeric") from exc
    return stripped


def read_json_object_file(path: str, label: str) -> dict[str, Any]:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"Could not read {label} JSON from {path}: {exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(f"{label} file is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise UsageError(f"{label} file must contain a JSON object.")
    return value


def validate_exact_fields(body: dict[str, Any], allowed: set[str], command: str) -> None:
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise UsageError(f"Unknown {command} field(s): {', '.join(unknown)}")


def require_nonblank_string(body: dict[str, Any], field: str, label: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise UsageError(f"{label} requires a non-empty {field}.")
    body[field] = value.strip()
    return body[field]


def require_cli_text(value: str, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise UsageError(f"{label} cannot be empty.")
    return stripped


def parse_notification_id(value: str) -> int:
    match = re.fullmatch("(?:NOTIF-)?(\\d+)", value.strip(), flags=re.IGNORECASE)
    if match is None or int(match.group(1)) < 1:
        raise UsageError("Notification ID must be a positive integer or NOTIF-XXXXX.")
    return int(match.group(1))
