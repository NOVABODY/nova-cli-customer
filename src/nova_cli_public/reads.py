"""One customer read registry for CLI, MCP, and offline discovery."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AfterValidator, ConfigDict, Field, create_model

from nova_cli_public import (
    aggregate_reports,
    body_documents,
    defect_cost,
    defect_reviews,
    external_preview,
    fleet_decisions,
    fmc_choice,
    inspection_confirmations,
    pave_images,
    quality_reports,
    rental_dismissal,
    repair_cancel,
    repair_requests,
    scheduled_work,
    scorecard_reads,
    vehicle_metadata,
    vehicle_note_edit,
    vendor_agreement,
)
from nova_cli_public import legacy_reads as handlers
from nova_cli_public import legacy_writes as write_handlers
from nova_cli_public.config import data_dir
from nova_cli_public.cortex import CORTEX_COMMANDS, CORTEX_IMPORT_COMMANDS
from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.event_commands import EVENT_COMMANDS, EVENT_MODELS
from nova_cli_public.events import run_event_tool
from nova_cli_public.read_commands import READ_COMMANDS
from nova_cli_public.write_commands import WRITE_COMMANDS

ALL_COMMANDS = vendor_agreement.COMMANDS + inspection_confirmations.COMMANDS + scheduled_work.COMMANDS + fleet_decisions.COMMANDS + READ_COMMANDS + WRITE_COMMANDS + EVENT_COMMANDS + CORTEX_COMMANDS + CORTEX_IMPORT_COMMANDS + defect_reviews.COMMANDS + vehicle_metadata.COMMANDS + vehicle_note_edit.COMMANDS + defect_cost.COMMANDS + repair_requests.COMMANDS + repair_cancel.COMMANDS + aggregate_reports.COMMANDS + scorecard_reads.COMMANDS + rental_dismissal.COMMANDS + quality_reports.COMMANDS + fmc_choice.COMMANDS + external_preview.COMMANDS
WRITE_TOOLS = inspection_confirmations.WRITES | {"acknowledge_dsp_daily_work_summary"} | {entry["tool"] for entry in WRITE_COMMANDS + CORTEX_IMPORT_COMMANDS} | {"approve_defect_review", "reject_defect_review", "update_vehicle", "create_vehicle", "update_vehicle_note", "delete_vehicle_note", "set_defect_cost", "resolve_fleet_issue", "cancel_repair_request", "dismiss_rental_routing", "set_vehicle_fmc_company"}

BY_COMMAND = {entry["command"]: entry for entry in ALL_COMMANDS}
BY_TOOL = {entry["tool"]: entry for entry in ALL_COMMANDS if entry.get("mcp", True)}
ALIASES = {
    "work-order": ["work-orders", "wo"],
    "defect": ["defects"],
    "notification": ["notifications"],
}
FILE_TOOLS = {"download_defect_photos", "pull_defects", "pull_vehicle_reports"}


def argument_type(name):
    return (
        {"int": int, "float": float}.get(name)
        or getattr(handlers, name, None)
        or getattr(write_handlers, name)
    )


def add_arguments(parser, entry):
    groups = {
        dest: parser.add_mutually_exclusive_group(required=group["required"])
        for group in entry["groups"]
        for dest in [tuple(group["arguments"])]
    }
    for flags, original in entry["arguments"]:
        options = dict(original)
        if options.get("nargs") == 0:
            options.pop("nargs")
        if options.get("action") == "BooleanOptionalAction":
            options["action"] = argparse.BooleanOptionalAction
        if "type" in options:
            options["type"] = argument_type(options["type"])
        dest = options.get("dest", flags[0].lstrip("-").replace("-", "_"))
        group = next((g for members, g in groups.items() if dest in members), parser)
        group.add_argument(*flags, **options)


def register_commands(root_subparsers):
    parsers = {}
    subparsers = {(): root_subparsers}
    for entry in ALL_COMMANDS:
        parts = tuple(entry["command"].split())
        for depth, part in enumerate(parts):
            prefix = parts[: depth + 1]
            if prefix in parsers:
                continue
            parent = parts[:depth]
            sub = subparsers[parent]
            parser = sub.choices.get(part)
            if parser is None:
                parser = sub.add_parser(part, aliases=ALIASES.get(part, []))
            parsers[prefix] = parser
            if depth < len(parts) - 1:
                existing = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
                subparsers[prefix] = (
                    existing[0]
                    if existing
                    else parser.add_subparsers(
                        dest=part.replace("-", "_") + "_command", required=True
                    )
                )
        leaf = parsers[parts]
        add_arguments(leaf, entry)
        leaf.set_defaults(
            handler=entry["handler"], read_command=entry["command"], **entry.get("defaults", {})
        )


def _inspection_reference(value):
    if not 1 <= int(value.rsplit('-', 1)[-1]) <= 2147483647:
        raise ValueError('Use a positive record ID. / Usa un ID de registro positivo.')
    return value


def _inspection_date_order(value, info):
    if info.data.get('date_from') and value < info.data['date_from']:
        raise ValueError('Use an end date on or after the start date. / Usa una fecha final igual o posterior a la fecha inicial.')
    return value


def input_model(entry, *, mcp=False):
    if entry["tool"] in inspection_confirmations.MODELS:
        return inspection_confirmations.MODELS[entry["tool"]]

    if entry["tool"] in scheduled_work.MODELS:
        return scheduled_work.MODELS[entry["tool"]]

    if entry["tool"] in quality_reports.MODELS:
        return quality_reports.MODELS[entry["tool"]]

    if entry["tool"] in fmc_choice.MODELS:
        return fmc_choice.MODELS[entry["tool"]]
    if entry["tool"] in scorecard_reads.MODELS:
        return scorecard_reads.MODELS[entry["tool"]]
    if entry["tool"] in aggregate_reports.MODELS:
        return aggregate_reports.MODELS[entry["tool"]]

    if entry["tool"] in fleet_decisions.MODELS:
        return fleet_decisions.MODELS[entry["tool"]]

    if entry["tool"] in external_preview.MODELS:
        return external_preview.MODELS[entry["tool"]]
    if entry["tool"] in rental_dismissal.MODELS:
        return rental_dismissal.MODELS[entry["tool"]]
    if entry["tool"] in repair_cancel.MODELS:
        return repair_cancel.MODELS[entry["tool"]]
    if entry["tool"] in vehicle_note_edit.MODELS:
        return vehicle_note_edit.MODELS[entry["tool"]]
    if entry["tool"] in repair_requests.MODELS:
        return repair_requests.MODELS[entry["tool"]]
    if entry["tool"] in defect_cost.MODELS:
        return defect_cost.MODELS[entry["tool"]]
    if entry["tool"] in vehicle_metadata.MODELS:
        return vehicle_metadata.MODELS[entry["tool"]]
    if entry["tool"] in defect_reviews.MODELS:
        return defect_reviews.MODELS[entry["tool"]]
    if mcp and entry["tool"] in EVENT_MODELS:
        return EVENT_MODELS[entry["tool"]]
    fields = {}
    for flags, options in entry["arguments"]:
        name = options.get("dest", flags[0].lstrip("-").replace("-", "_"))
        if mcp and name in ("out", "cursor_file"):
            continue
        kind = options.get("type")
        value_type = (
            int
            if kind
            in ("int", "positive_id", "positive_int", "nonnegative_int", "bounded_report_page_size")
            else float
            if kind == "float"
            else str
        )
        if options.get("action") in ("store_true", "store_false", "BooleanOptionalAction"):
            value_type = bool
        if options.get("choices"):
            value_type = Literal[tuple(options["choices"])]
        if options.get("nargs") == "+" or options.get("action") == "append":
            value_type = (
                list[Annotated[str, Field(pattern=r"^(?:FD-)?[0-9]+$")]]
                if name == "defect_ids"
                else list[value_type]
            )
        required = options.get("required") or (
            not flags[0].startswith("-") and options.get("nargs") != "?"
        )
        default = ... if required else options.get("default", False if value_type is bool else None)
        constraints = {}
        if name == 'storage_key' and entry.get('image_read'):
            constraints = {'min_length': 1, 'max_length': 500}
        if name == 'idx' and entry.get('image_read'):
            constraints = {'ge': 0, 'le': 999}
        if name in ("page", "per_page", "limit"):
            constraints["ge"] = 1
        if name == "per_page":
            constraints["le"] = 100 if entry["command"] in ("vehicle list", "inspection list") else 200
        if name == "limit":
            constraints["le"] = 200 if entry["command"] in ("body-repair list", "vehicle list-notes") else 500
        if name == "offset":
            constraints["ge"] = 0
        if name in ("scheduled_within_hours", "returned_within_hours"):
            constraints = {"ge": 1, "le": 720}
        if name == "tz_offset_minutes":
            constraints = {"ge": -840, "le": 840}
        if name in ("date_from", "date_to"):
            value_type = Annotated[str, AfterValidator(handlers.iso_date_arg)]
            constraints["pattern"] = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
        if name in (
            "vehicle_id",
            "req_id",
            "wo_id",
            "defect_id",
            "report_id",
            "inspection_id",
            "dsp_id",
            "vendor_workshop_id",
        ):
            prefixes = {
                "vehicle_id": "VAN",
                "req_id": "BRR",
                "wo_id": "WO",
                "defect_id": "FD",
                "report_id": "VR",
                "inspection_id": "INS",
                "dsp_id": "DSP",
                "vendor_workshop_id": "VW",
            }
            if value_type is str:
                constraints["pattern"] = rf"^(?:{prefixes[name]}-)?[0-9]+$"
        if entry['tool'] in ('list_inspections', 'get_inspection'):
            if name in ('inspection_id', 'dsp_id', 'vehicle_id'):
                value_type = Annotated[str, AfterValidator(_inspection_reference)]
                constraints['max_length'] = 14
            if name == 'page':
                constraints['le'] = 2147483647
            if name == 'date_to':
                value_type = Annotated[str, AfterValidator(handlers.iso_date_arg), AfterValidator(_inspection_date_order)]
        if entry['tool'] == 'list_defect_photos' and name == 'defect_id':
            value_type = Annotated[str, AfterValidator(_inspection_reference)]
            constraints['max_length'] = 100
        if name == "quote":
            constraints = {"pattern": r"^(?:BRQ-)?[0-9]+$"}
        if name == "request_ref":
            constraints = {"pattern": r"^[A-Za-z0-9_-]{1,64}$"}
        if mcp and name == "max_wait":
            default = 25.0
            constraints = {"ge": 0, "le": 25}
        if mcp and name == "interval":
            constraints = {"gt": 0, "le": 25}
        fields[name] = (
            value_type if required or default is not None else value_type | None,
            Field(default=default, description=options.get("help"), **constraints),
        )
    return create_model(
        entry["tool"] + "Input", __config__=ConfigDict(extra="forbid", strict=True), **fields
    )


MODELS = {name: input_model(entry, mcp=True) for name, entry in BY_TOOL.items()}


class BoundedReader:
    def __init__(self, client):
        self.client, self.calls = client, 0
        self.profile = getattr(client, "profile", None)
        self.expected_identity = None
        self.bytes_read = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        if self.calls > 100:
            raise UsageError("Read limit reached. Use a smaller filter.")
        value = self.client.request(*args, **kwargs)
        if (
            self.expected_identity is not None
            and self.client.connection_identity() != self.expected_identity
        ):
            raise UsageError("Connection changed during the read. Try again; cursor unchanged.")
        size = len(json.dumps(value).encode())
        self.bytes_read += size
        if size > 2 * 1024 * 1024 or self.bytes_read > 10 * 1024 * 1024:
            raise UsageError("Response is too large. Use a smaller page.")
        return value

    def whoami(self):
        return self.request("GET", "/auth/me")

    def public_request(self, method, path):
        return self.client.public_request(method, path)


class CustomerReadService:
    def __init__(self, client):
        self.client = client

    def tool_schemas(self):
        return {name: model.model_json_schema() for name, model in MODELS.items()}

    def output_schema(self, name):
        if name == "get_vendor_agreement_status":
            return vendor_agreement.Status.model_json_schema()

        if name in inspection_confirmations.OUTPUTS:
            return inspection_confirmations.OUTPUTS[name].model_json_schema()

        if BY_TOOL[name].get('image_read'):
            return {**body_documents.DOCUMENT_SCHEMA, 'description': 'Descriptor for original image bytes. No local file is written.',
                'properties': {**body_documents.DOCUMENT_SCHEMA['properties'], 'mime_type': {'enum': list(pave_images.MIMES)}}}
        if BY_TOOL[name].get("document_kind"):
            return body_documents.document_schema(BY_TOOL[name]["document_kind"])
        return {
            "type": "object",
            "additionalProperties": True,
            "description": "Server-authorized fields; array results use items. File tools return local references.",
        }

    def run(self, name, arguments):
        if name not in BY_TOOL:
            raise ValueError("Unknown tool")
        entry = BY_TOOL[name]
        if name == "get_work_order" and "work_order_id" in arguments and "wo_id" not in arguments:
            arguments = {
                ("wo_id" if key == "work_order_id" else key): value
                for key, value in arguments.items()
            }
        values = MODELS[name].model_validate(arguments).model_dump(exclude_unset=name in vehicle_metadata.MODELS)
        if entry.get('image_read'):
            return pave_images.embedded(self.client, values)
        if entry.get('document_kind'):
            return body_documents.embedded(self.client, values['request_ref'], entry['document_kind'], values.get('quote'), values.get('lang', 'en'))
        if name in EVENT_MODELS:
            return run_event_tool(name, values, self.client)
        for group in entry["groups"]:
            chosen = [key for key in group["arguments"] if values.get(key) not in (None, False)]
            if len(chosen) > 1 or (group["required"] and not chosen):
                raise ValueError("Select one argument from the required group")
        for flags, options in entry["arguments"]:
            key = options.get("dest", flags[0].lstrip("-").replace("-", "_"))
            if (
                key in values
                and values[key] is not None
                and options.get("type") not in (None, "int", "float")
            ):
                values[key] = argument_type(options["type"])(str(values[key]))
        if name in WRITE_TOOLS and any(
            value == "-" for key, value in values.items() if key.endswith("_file")
        ):
            raise UsageError("MCP file arguments cannot read stdin.")
        args = argparse.Namespace(
            **values,
            **entry.get("defaults", {}),
            _client=self.client if name in WRITE_TOOLS else BoundedReader(self.client),
            quiet=False,
            json=True,
            no_input=True,
        )
        if name in FILE_TOOLS:
            return self._file_result(entry, args)
        value = entry["handler"](args)
        if name not in WRITE_TOOLS:
            validate_response(name, value)
        return value if isinstance(value, dict) else {"items": value}

    def _file_result(self, entry, args):
        self.client.refresh()
        identity = self.client.connection_identity()
        args._client.expected_identity = identity
        destination = data_dir() / "mcp-artifacts" / uuid4().hex
        destination.mkdir(parents=True, mode=0o700)
        args.out = str(
            destination
            if entry["tool"] == "download_defect_photos"
            else destination / "records.json"
        )
        profile = self.client.profile
        binding = hashlib.sha256(
            json.dumps([profile.api, profile.name, identity, entry["tool"]]).encode()
        ).hexdigest()
        args.cursor_file = str(data_dir() / "mcp-cursors" / (binding + ".json"))
        if entry["tool"] == "download_defect_photos":
            if len(args.defect_ids) > 10:
                raise UsageError("Use at most 10 defect IDs per download.")
            remaining, count = 100 * 1024 * 1024, 0

            def fetch(url):
                nonlocal remaining, count
                if count >= 20:
                    raise UsageError("Use fewer defects. Photo count limit reached.")
                data = handlers.fetch_presigned(
                    url, max_bytes=min(handlers.PHOTO_MAX_BYTES, remaining)
                )
                remaining -= len(data)
                count += 1
                return data

            result = handlers.download_defect_photos(
                args._client, args.defect_ids, destination, fetch=fetch
            )
        else:
            result = entry["handler"](args)
        files = [
            {"path": str(path), "uri": path.as_uri(), "size_bytes": path.stat().st_size}
            for path in destination.rglob("*")
            if path.is_file()
        ]
        return {"result": result, "files": files}


def validate_response(name, value):
    if not isinstance(value, (dict, list)):
        raise ApiError("Invalid read response")
    if name in ("list_body_repair_requests", "get_body_repair_request", "list_inspections", "get_inspection"):
        if not isinstance(value, dict):
            raise ApiError("Invalid read response")
        if name in ("list_body_repair_requests", "list_inspections") and (
            not isinstance(value.get("items"), list)
            or any(not isinstance(row, dict) for row in value["items"])
            or type(value.get("total")) is not int or value["total"] < 0
        ):
            raise ApiError("Invalid read response")
    if name == 'list_inspections' and (
        type(value.get('page')) is not int or value['page'] < 1
        or type(value.get('per_page')) is not int or not 1 <= value['per_page'] <= 100
    ):
        raise ApiError('Invalid inspection page. / Página de inspecciones no válida.')
    if name == 'list_defect_photos' and (
        not isinstance(value, dict) or not isinstance(value.get('items'), list)
        or any(not isinstance(row, dict) for row in value['items'])
        or type(value.get('total')) is not int or value['total'] < 0
    ):
        raise ApiError('Invalid photo response. / Respuesta de fotos no válida.')
    core = {
        "list_vehicles": ("id",),
        "get_vehicle": ("id",),
        "list_work_orders": ("id", "status", "vehicle_id"),
        "get_work_order": ("id", "status", "vehicle_id"),
        "list_defects": ("id", "vehicle_id", "source", "part", "defect_type"),
        "get_defect": ("id", "vehicle_id", "source", "part", "defect_type"),
    }.get(name)
    if core:
        listing = name.startswith("list_")
        if listing and (
            not isinstance(value, dict)
            or not isinstance(value.get("items"), list)
            or type(value.get("total")) is not int
        ):
            raise ApiError("Invalid read response")
        rows = value["items"] if listing else [value]
        if any(not isinstance(row, dict) or any(key not in row for key in core) for row in rows):
            raise ApiError("Invalid read response")
