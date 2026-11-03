from __future__ import annotations

import json
import sys
from typing import Any


def emit(value: Any, *, as_json: bool = False, quiet: bool = False) -> None:
    if quiet:
        return
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
        return
    print(safe_text(humanize(value)))


def humanize(value: Any) -> str:
    if value is None:
        return "OK"
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if not value:
            return "No items."
        return "\n".join(_one_line(item) for item in value)
    if isinstance(value, dict):
        if _looks_like_page(value):
            items = value.get("items") or []
            summary = []
            if isinstance(items, list):
                summary.extend(_one_line(item) for item in items)
            total = value.get("total")
            if total is not None:
                summary.append(f"total: {total}")
            return "\n".join(summary) if summary else json.dumps(value, indent=2, sort_keys=True)
        return "\n".join(f"{k}: {format_scalar(v)}" for k, v in value.items())
    return str(value)


def warn(message: str) -> None:
    print(safe_text(message), file=sys.stderr)


def _looks_like_page(value: dict[str, Any]) -> bool:
    return isinstance(value.get("items"), list)


def _one_line(value: Any) -> str:
    if not isinstance(value, dict):
        return format_scalar(value)
    preferred = [
        "id",
        "ro_number",
        "status",
        "vehicle_fleet_id",
        "fleet_id",
        "license_plate",
        "name",
        "email",
        "title",
        "created_at",
    ]
    parts = []
    for key in preferred:
        if key in value and value[key] not in (None, ""):
            parts.append(f"{key}={format_scalar(value[key])}")
    if parts:
        return "  ".join(parts)
    return json.dumps(value, sort_keys=True)


def format_scalar(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def safe_text(text: str) -> str:
    """Render terminal control bytes visibly; retain ordinary multiline output."""
    return ''.join(f'\\x{ord(char):02x}' if (ord(char) < 32 and char not in '\n\t')
                   or 127 <= ord(char) <= 159 else char for char in text)
