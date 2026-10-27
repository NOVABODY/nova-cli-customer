"""Customer read handlers extracted from legacy tree c2298bbf.

Keep CLI business behavior here; authentication and admitted routes live in the
public client. No private CLI package is imported or shipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from nova_cli_public.client import ApiClient, NoRedirects
from nova_cli_public.config import data_dir
from nova_cli_public.errors import ApiError, PollTimeout, UsageError
from nova_cli_public.output import emit


def client_from_args(args):
    if hasattr(args, "_client"):
        return args._client
    from nova_cli_public.cli import client_from_args as resolve

    return resolve(args)


DEFECT_CATALOG_VEHICLE_CLASSES = (
    "custom_delivery_van",
    "regular_cargo_van",
    "step_van_dot",
    "electric_vehicle",
    "box_truck_dot",
)

PHOTO_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/webp": ".webp",
}

PHOTO_MAX_BYTES = 50 * 1024 * 1024


def positive_id(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def cmd_work_order_wait(args: argparse.Namespace) -> Any:
    targets = {status.strip().lower() for status in args.until.split(",") if status.strip()}
    if not targets:
        raise UsageError("Provide at least one status in --until.")
    if args.interval <= 0:
        raise UsageError("--interval must be positive.")
    if args.max_wait < 0:
        raise UsageError("--max-wait cannot be negative.")
    client = client_from_args(args)
    started = time.monotonic()
    polls = 0
    while True:
        work_order = client.request("GET", f"/work-orders/{args.wo_id}")
        polls += 1
        status = work_order.get("status") if isinstance(work_order, dict) else None
        if isinstance(status, str) and status.lower() in targets:
            return {
                "ok": True,
                "wo_id": args.wo_id,
                "status": status,
                "polls": polls,
                "waited_seconds": round(time.monotonic() - started, 3),
                "work_order": work_order,
            }
        elapsed = time.monotonic() - started
        if elapsed + args.interval > args.max_wait:
            raise PollTimeout(
                f"work order {args.wo_id} did not reach {sorted(targets)} within {args.max_wait}s; last status: {status!r}"
            )
        time.sleep(args.interval)


def cmd_work_order_line_items_list(args: argparse.Namespace) -> Any:
    detail = client_from_args(args).request("GET", f"/work-orders/{args.wo_id}")
    if not isinstance(detail, dict):
        raise ApiError("API response did not include a work-order object")
    line_items = detail.get("line_items")
    if not isinstance(line_items, list):
        raise ApiError("API response did not include line_items")
    return line_items


def cmd_vehicle_get(args: argparse.Namespace) -> Any:
    client = client_from_args(args)
    return client.request("GET", f"/vehicles/{args.vehicle_id}")


def cmd_vehicle_list(args: argparse.Namespace) -> Any:
    client = client_from_args(args)
    query = vars_to_query(args, ["search", "dsp_id", "page", "per_page", "fleet_id", "grounded"])
    if args.status == "active":
        query["is_active"] = True
    elif args.status == "inactive":
        query["is_active"] = False
    elif args.status == "all":
        query["include_inactive"] = True
    elif args.status == "grounded":
        query["grounded"] = True
    return client.request("GET", "/vehicles", query=query)


def cmd_defect_catalog(args: argparse.Namespace) -> Any:
    client = client_from_args(args)
    if not args.all:
        return client.request(
            "GET",
            "/defect-catalog",
            query=clean_query({"vehicle_class": args.vehicle_class, "dsp_id": args.dsp_id}),
        )
    catalogs = {
        vehicle_class: client.request(
            "GET",
            "/defect-catalog",
            query=clean_query({"vehicle_class": vehicle_class, "dsp_id": args.dsp_id}),
        )
        for vehicle_class in DEFECT_CATALOG_VEHICLE_CLASSES
    }
    return {"source": "/v1/defect-catalog", "dsp_id": args.dsp_id, "vehicle_classes": catalogs}


def cmd_defect_list(args: argparse.Namespace) -> Any:
    response = client_from_args(args).request(
        "GET",
        "/defects",
        query=vars_to_query(
            args,
            [
                "vehicle_id",
                "page",
                "per_page",
                "dsp_id",
                "inspection_id",
                "source",
                "date_from",
                "date_to",
                "tz_offset_minutes",
                "open_only",
                "include_no_shop",
            ],
        ),
    )
    if args.status and isinstance(response, dict) and isinstance(response.get("items"), list):
        items = [item for item in response["items"] if defect_matches_status(item, args.status)]
        filtered = dict(response)
        filtered["items"] = items
        filtered["total"] = len(items)
        return filtered
    return response


def cmd_defect_pull(args: argparse.Namespace) -> Any:
    if args.new and args.quiet and not args.out:
        raise UsageError("defect pull requires stdout or --out; do not use --quiet alone.")
    cursor_path = (
        Path(args.cursor_file).expanduser() if args.cursor_file else default_defects_cursor_path()
    )
    cursor_before = read_defects_cursor(cursor_path) if args.new else None
    query: dict[str, Any] = {"per_page": args.per_page}
    if args.vehicle_id:
        query["vehicle_id"] = args.vehicle_id
    if args.new and cursor_before:
        query.update(reported_since=cursor_before["reported_at"], after_id=defect_key(cursor_before)[1])
    defects = fetch_all_defects(client_from_args(args), query)
    cursor_after = cursor_before
    if args.new and defects:
        last = max(defects, key=defect_key)
        cursor_after = {"reported_at": last["reported_at"], "id": last["id"]}
    package = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "vehicle_id": args.vehicle_id,
        "count": len(defects),
        "defects": defects,
    }
    if args.new:
        package["cursor_before"] = cursor_before
        package["cursor_after"] = cursor_after
    if args.out:
        write_json_file(Path(args.out), package)
        if args.new and cursor_after != cursor_before and cursor_after is not None:
            write_defects_cursor(cursor_path, cursor_after)
        return {"ok": True, "out": args.out, "count": len(defects)}
    args.json = True
    if args.new:
        try:
            emit(package, as_json=True, quiet=False)
            sys.stdout.flush()
        except OSError as exc:
            raise UsageError("Could not write defect output; cursor unchanged.") from exc
        if cursor_after != cursor_before and cursor_after is not None:
            write_defects_cursor(cursor_path, cursor_after)
        args.quiet = True
    return package


def fetch_presigned(url: str, max_bytes: int = PHOTO_MAX_BYTES) -> bytes:
    """GET a presigned HTTPS URL. It carries its own authorization, so no bearer header is sent."""
    import urllib.request

    if not url.startswith("https://"):
        raise UsageError(f"Refusing to download a photo over a non-HTTPS URL: {url.split('?')[0]}")
    with urllib.request.build_opener(NoRedirects()).open(url, timeout=30) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UsageError("Photo is larger than the download limit")
    return data


def download_defect_photos(
    client: Any, defect_ids: list[str], out: Path, fetch=fetch_presigned
) -> dict[str, Any]:
    manifest: dict[str, list[dict[str, Any]]] = {}
    if any(not re.fullmatch(r"(?:FD-)?[0-9]+", defect_id) for defect_id in defect_ids):
        raise UsageError("Use numeric or FD-prefixed defect IDs.")
    for defect_id in defect_ids:
        listing = client.request("GET", f"/defects/{defect_id}/photos")
        items = listing.get("items", []) if isinstance(listing, dict) else []
        folder = out / defect_id
        saved = []
        for item in items:
            photo_id = str(item.get("id") or "").strip()
            if not photo_id or "/" in photo_id or photo_id.startswith("."):
                continue
            ext = PHOTO_EXTENSIONS.get(str(item.get("content_type") or "").lower(), ".bin")
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{photo_id}{ext}"
            path.write_bytes(fetch(resolve_photo_url(str(item.get("url") or ""), client)))
            saved.append(
                {
                    "photo_id": photo_id,
                    "path": str(path),
                    "content_type": item.get("content_type"),
                    "uploaded_at": item.get("uploaded_at"),
                    "category": item.get("category"),
                }
            )
        manifest[defect_id] = saved
    return {
        "ok": True,
        "out": str(out),
        "photos": manifest,
        "count": sum(len(v) for v in manifest.values()),
    }


def cmd_defect_photos(args: argparse.Namespace) -> Any:
    args.json = True
    return download_defect_photos(
        client_from_args(args), args.defect_ids, Path(args.out).expanduser()
    )


def cmd_vehicle_report_list(args: argparse.Namespace) -> Any:
    query = vars_to_query(args, ["status", "external_ref", "updated_since"])
    query.update({"limit": args.per_page, "offset": (args.page - 1) * args.per_page})
    return client_from_args(args).request("GET", "/vehicle-reports", query=query)


def cmd_vehicle_report_get(args: argparse.Namespace) -> Any:
    return client_from_args(args).request("GET", f"/vehicle-reports/{args.report_id}")


def cmd_vehicle_report_pull(args: argparse.Namespace) -> Any:
    if args.quiet and (not args.out):
        raise UsageError("vehicle-report pull requires stdout or --out; do not use --quiet alone.")
    cursor_path = (
        Path(args.cursor_file).expanduser()
        if args.cursor_file
        else default_vehicle_reports_cursor_path()
    )
    cursor_before = read_vehicle_reports_cursor(cursor_path)
    cursor_boundary = vehicle_report_cursor_key(cursor_before) if cursor_before else None
    query = clean_query(
        {
            "status": args.status,
            "external_ref": args.external_ref,
            "updated_since": cursor_before["updated_at"] if cursor_before else None,
            "after_id": max(0, cursor_boundary[1]) if cursor_boundary else 0,
            "limit": args.per_page,
        }
    )
    reports = fetch_all_vehicle_reports(client_from_args(args), query)
    if cursor_boundary:
        reports = [report for report in reports if vehicle_report_key(report) > cursor_boundary]
    reports.sort(key=vehicle_report_key)
    cursor_after = cursor_before
    if reports:
        last = max(reports, key=vehicle_report_key)
        cursor_after = {"updated_at": str(last["updated_at"]), "id": str(last["id"])}
    package = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "count": len(reports),
        "reports": reports,
        "cursor_before": cursor_before,
        "cursor_after": cursor_after,
    }
    if args.out:
        write_json_file(Path(args.out), package)
        if cursor_after != cursor_before and cursor_after is not None:
            write_vehicle_reports_cursor(
                cursor_path, cursor_after["updated_at"], cursor_after["id"]
            )
        return {"ok": True, "out": args.out, "count": len(reports)}
    try:
        emit(package, as_json=True, quiet=False)
        sys.stdout.flush()
    except OSError as exc:
        raise UsageError(f"Could not write vehicle-report output: {exc}") from exc
    if cursor_after != cursor_before and cursor_after is not None:
        write_vehicle_reports_cursor(cursor_path, cursor_after["updated_at"], cursor_after["id"])
    args.quiet = True
    return None


def nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return parsed


def positive_int(value: str) -> int:
    parsed = nonnegative_int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def bounded_report_page_size(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 200:
        raise argparse.ArgumentTypeError("value must not exceed 200")
    return parsed


def iso_datetime_arg(value: str) -> str:
    normalized = value.strip()
    candidate = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def vars_to_query(args: argparse.Namespace, names: list[str]) -> dict[str, Any]:
    return clean_query({name: getattr(args, name, None) for name in names})


def clean_query(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None and v != ""}


def defect_matches_status(defect: Any, status: str) -> bool:
    if not isinstance(defect, dict):
        return False
    wanted = status.strip().lower()
    if not wanted:
        return True
    for key in ("status", "review_status", "work_order_status", "work_order_display_status"):
        value = defect.get(key)
        if isinstance(value, str) and value.lower() == wanted:
            return True
    return False


def fetch_all_defects(client: ApiClient, query: dict[str, Any]) -> list[dict[str, Any]]:
    per_page = query.get("per_page") or 50
    since = query.get("reported_since") or "0001-01-01T00:00:00Z"
    after_id = query.get("after_id", 0)
    defects: dict[int, dict[str, Any]] = {}
    while True:
        response = client.request("GET", "/defects", query={**query,
            "reported_since": since, "after_id": after_id, "per_page": per_page, "page": 1})
        if not isinstance(response, dict) or response.get("keyset") is not True:
            raise ApiError("API does not confirm keyset pagination; cursor unchanged.")
        items, total = response.get("items"), response.get("total")
        if (not isinstance(items, list) or type(total) is not int or total < 0
                or len(items) != min(per_page, total) or response.get("page") != 1
                or response.get("per_page") != per_page):
            raise ApiError("Invalid defect page; cursor unchanged.")
        boundary = (parse_iso_datetime(since), after_id)
        for item in items:
            key = defect_key(item)
            if key <= boundary:
                raise ApiError("Defect pagination made no progress; cursor unchanged.")
            defects[key[1]] = item
            boundary = key
            since, after_id = item["reported_at"], key[1]
        if total <= per_page:
            return sorted(defects.values(), key=defect_key)


def fetch_all_vehicle_reports(client: ApiClient, query: dict[str, Any]) -> list[dict[str, Any]]:
    limit = query.get("limit") or 100
    since = query.get("updated_since") or "0001-01-01T00:00:00Z"
    after_id = query.get("after_id", 0)
    reports: dict[int, dict[str, Any]] = {}
    while True:
        response = client.request("GET", "/vehicle-reports", query={**query,
            "updated_since": since, "after_id": after_id, "limit": limit, "offset": 0})
        if not isinstance(response, dict) or response.get("keyset") is not True:
            raise ApiError("API does not confirm keyset pagination; cursor unchanged.")
        items, total = response.get("items"), response.get("total")
        if (not isinstance(items, list) or type(total) is not int or total < 0
                or len(items) != min(limit, total) or response.get("offset") != 0
                or response.get("limit") != limit):
            raise ApiError("Invalid vehicle-report page; cursor unchanged.")
        boundary = (parse_iso_datetime(since), after_id)
        for item in items:
            if not isinstance(item, dict):
                raise ApiError("Invalid vehicle-report item; cursor unchanged.")
            key = vehicle_report_key(item)
            if key <= boundary:
                raise ApiError("Vehicle-report pagination made no progress; cursor unchanged.")
            reports[key[1]] = item
            boundary = key
            since, after_id = item["updated_at"], key[1]
        if total <= limit:
            return sorted(reports.values(), key=vehicle_report_key)


def default_defects_cursor_path() -> Path:
    return data_dir() / "defects_cursor.json"


def read_defects_cursor(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UsageError(f"Invalid defects cursor JSON at {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("reported_at"), str):
        raise UsageError(f"Invalid defects cursor shape at {path}")
    cursor = {"reported_at": data["reported_at"], "id": data.get("id", "FD-0")}
    try:
        defect_key(cursor)
    except ApiError as exc:
        raise UsageError(f"Invalid defects cursor at {path}") from exc
    return cursor


def write_defects_cursor(path: Path, cursor: dict[str, str]) -> None:
    write_json_file(path, cursor)


def defect_key(record: dict[str, Any]) -> tuple[datetime, int]:
    if not isinstance(record, dict):
        raise ApiError("Invalid defect record; cursor unchanged.")
    match = re.fullmatch(r"FD-([0-9]+)", str(record.get("id", "")), flags=re.IGNORECASE)
    instant = record.get("reported_at")
    if match is None or not isinstance(instant, str):
        raise ApiError("Invalid defect cursor; cursor unchanged.")
    try:
        parsed = parse_iso_datetime(iso_datetime_arg(instant))
        numeric_id = int(match.group(1))
        if numeric_id > 2_147_483_647:
            raise ValueError()
    except (ValueError, argparse.ArgumentTypeError) as exc:
        raise ApiError("Invalid defect boundary; cursor unchanged.") from exc
    return parsed, numeric_id


def default_vehicle_reports_cursor_path() -> Path:
    return data_dir() / "vehicle_reports_cursor.json"


def read_vehicle_reports_cursor(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"Invalid vehicle-report cursor JSON at {path}") from exc
    updated_at = data.get("updated_at") if isinstance(data, dict) else None
    report_id = data.get("id", "") if isinstance(data, dict) else None
    if (
        not isinstance(updated_at, str)
        or not updated_at.strip()
        or (not isinstance(report_id, str))
    ):
        raise UsageError(f"Invalid vehicle-report cursor shape at {path}")
    parse_iso_datetime(updated_at)
    return {"updated_at": updated_at, "id": report_id}


def write_vehicle_reports_cursor(path: Path, updated_at: str, report_id: str) -> None:
    write_json_file(path, {"updated_at": updated_at, "id": report_id})


def vehicle_report_cursor_key(cursor: dict[str, str]) -> tuple[datetime, int]:
    report_id = cursor["id"]
    if not report_id:
        numeric_id = -1
    else:
        match = re.fullmatch("VR-(\\d+)", report_id, flags=re.IGNORECASE)
        if match is None:
            raise UsageError("Vehicle-report cursor id must use the VR-NNNNN format.")
        numeric_id = int(match.group(1))
    return (parse_iso_datetime(cursor["updated_at"]), numeric_id)


def vehicle_report_key(report: dict[str, Any]) -> tuple[datetime, int]:
    updated_at = report.get("updated_at")
    report_id = report.get("id")
    if not isinstance(updated_at, str) or not updated_at:
        raise ApiError("Vehicle-report response item did not include updated_at")
    if not isinstance(report_id, str) or not report_id:
        raise ApiError("Vehicle-report response item did not include id")
    match = re.fullmatch("VR-(\\d+)", report_id, flags=re.IGNORECASE)
    if match is None:
        raise ApiError("Vehicle-report response item had an invalid id")
    return (parse_iso_datetime(updated_at), int(match.group(1)))


def write_json_file(path: Path, value: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        raise UsageError(f"Could not write JSON file {path}: {exc}") from exc


def iso_datetime_gt(value: str, cursor: str) -> bool:
    return parse_iso_datetime(value) > parse_iso_datetime(cursor)


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise UsageError(f"Invalid ISO 8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_date_arg(value):
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("Use a valid date in YYYY-MM-DD form.") from None
    return value


def resolve_photo_url(url, client):
    # Same-origin storage proxy URLs are API-relative, as in the web apiAssetUrl
    # helper. Never accept scheme-relative URLs or arbitrary relative targets.
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
        return url
    if (
        not parsed.scheme
        and not parsed.netloc
        and parsed.path.startswith(("/uploads/object/", "/uploads/local/"))
        and not any(part in (".", "..") for part in parsed.path.split("/"))
    ):
        return client.profile.api.rstrip("/") + url
    raise UsageError("Invalid photo download URL.")
