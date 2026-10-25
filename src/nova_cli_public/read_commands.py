"""Pinned customer read command declarations from the legacy CLI."""

import re

from nova_cli_public import body_documents, pave_images
from nova_cli_public import legacy_reads as handlers
from nova_cli_public.errors import UsageError


def pave_read(args, field, prefix, template):
    reference = getattr(args, field)
    if not re.fullmatch(rf"(?:{prefix}-)?[0-9]+", reference):
        raise UsageError("Use a record ID. / Use un ID de registro.")
    return handlers.client_from_args(args).request("GET", template.format(reference))


def photo_references(args):
    from nova_cli_public.reads import MODELS, validate_response

    values = MODELS['list_defect_photos'].model_validate({'defect_id': args.defect_id})
    value = handlers.client_from_args(args).request('GET', f'/defects/{values.defect_id}/photos')
    validate_response('list_defect_photos', value)
    return value


def body_read(args, tool):
    # Reuse the tool contract for CLI validation before constructing a route.
    from nova_cli_public.reads import MODELS, validate_response

    model = MODELS[tool]
    values = model.model_validate(
        {key: getattr(args, key) for key in model.model_fields}
    ).model_dump(exclude_none=True)
    reference = values.pop("request_ref", None)
    path = "/body-repair/requests" + ("/" + reference if reference is not None else "")
    options = {"query": values} if reference is None else {}
    value = handlers.client_from_args(args).request("GET", path, **options)
    validate_response(tool, value)
    return value


def inspection_read(args, tool):
    from nova_cli_public.reads import MODELS, validate_response

    model = MODELS[tool]
    values = model.model_validate({key: getattr(args, key) for key in model.model_fields}).model_dump(exclude_none=True)
    reference = values.pop('inspection_id', None)
    path = '/inspections' + ('/' + reference if reference is not None else '')
    value = handlers.client_from_args(args).request('GET', path, **({'query': values} if reference is None else {}))
    validate_response(tool, value)
    return value


READ_COMMANDS = [
    {
        'command': 'defect list-photos', 'tool': 'list_defect_photos', 'grant': 'defects.photos.list.v1',
        'description': 'Read stored photo references. / Consulta las referencias de fotos guardadas.',
        'groups': [], 'arguments': [(['defect_id'], {})], 'handler': photo_references,
    },
    {
        "command": "inspection list", "tool": "list_inspections", "grant": "inspections.list.v1",
        "description": "List permitted inspections. / Consulta las inspecciones permitidas.", "groups": [],
        "arguments": [(["--dsp-id"], {}), (["--vehicle-id"], {}),
            (["--date-from"], {"type": "iso_date_arg"}), (["--date-to"], {"type": "iso_date_arg"}),
            (["--result"], {"choices": ["passed", "flagged", "conditional", "incomplete"]}),
            (["--status"], {"choices": ["draft", "submitted", "superseded", "expired"]}),
            (["--page"], {"type": "positive_int", "default": 1}),
            (["--per-page"], {"type": "bounded_report_page_size", "default": 20})],
        "handler": lambda args: inspection_read(args, "list_inspections"),
    },
    {
        "command": "inspection get", "tool": "get_inspection", "grant": "inspections.get.v1",
        "description": "Read a permitted inspection. / Consulta una inspección permitida.", "groups": [],
        "arguments": [(["inspection_id"], {})],
        "handler": lambda args: inspection_read(args, "get_inspection"),
    },
    {
        "command": "body-repair pave-image", "tool": "download_body_repair_pave_image", "image_read": True,
        "description": "Read a Body repair PAVE image. / Consulta una imagen PAVE de reparación de carrocería.",
        "grant": "body_repair.pave.images.read.v1", "groups": [],
        "arguments": [(["--storage-key"], {"required": True}),
            (["--category"], {"required": True, "choices": ["panel", "damage", "side", "vehicle"]}),
            (["--idx"], {"type": "nonnegative_int", "default": 0}), (["--out"], {"required": True})],
        "handler": pave_images.download,
    },
    {
        "command": "body-repair documentation", "tool": "download_body_repair_documentation", "document_kind": "documentation",
        "description": "Read the Body repair documentation ZIP. / Consulta el ZIP de documentación de reparación de carrocería.",
        "grant": "body_repair.documents.documentation.read.v1", "groups": [],
        "arguments": [(["request_ref"], {}), (["--out"], {"required": True}), (["--lang"], {"choices": ["en", "es"], "default": "en"})],
        "handler": lambda args: body_documents.download(args, "documentation"),
    },
    {
        "command": "body-repair invoice", "tool": "download_body_repair_invoice", "document_kind": "invoice",
        "description": "Read the available Body repair invoice or receipt PDF. / Consulta el PDF disponible de la factura o el recibo de reparación de carrocería.",
        "grant": "body_repair.documents.invoice.read.v1", "groups": [],
        "arguments": [(["request_ref"], {}), (["--out"], {"required": True})],
        "handler": lambda args: body_documents.download(args, "invoice"),
    },
    {
        "command": "body-repair quote", "tool": "download_body_repair_quote", "document_kind": "quote",
        "grant": "body_repair.documents.quote.read.v1", "groups": [],
        "arguments": [(["request_ref"], {}), (["--quote"], {}), (["--out"], {"required": True})],
        "handler": lambda args: body_documents.download(args, "quote"),
    },
    {
        "command": "body-repair scope", "tool": "download_body_repair_scope", "document_kind": "scope",
        "grant": "body_repair.documents.scope.read.v1", "groups": [],
        "arguments": [(["request_ref"], {}), (["--out"], {"required": True})],
        "handler": lambda args: body_documents.download(args, "scope"),
    },
    {
        "command": "body-repair list", "tool": "list_body_repair_requests",
        "grant": "body_repair.requests.list.v1", "groups": [],
        "arguments": [
            (["--status"], {"choices": ["pending_quotes", "quoted", "quote_selected",
                "pickup_proposed", "pickup_scheduled", "in_shop", "repair_complete",
                "pending_signoff", "awaiting_return", "completed", "cancelled",
                "no_eligible_vendor", "halted"]}),
            (["--stage"], {"choices": ["open"]}),
            (["--limit"], {"type": "int"}), (["--offset"], {"type": "int"}),
            (["--vehicle-id"], {}),
        ],
        "handler": lambda args: body_read(args, "list_body_repair_requests"),
    },
    {
        "command": "body-repair get", "tool": "get_body_repair_request",
        "grant": "body_repair.requests.get.v1", "groups": [],
        "arguments": [(["request_ref"], {})],
        "handler": lambda args: body_read(args, "get_body_repair_request"),
    },
    {
        "command": "vehicle pave-reports", "tool": "list_vehicle_pave_reports",
        "grant": "vehicles.pave_reports.list.v1",
        "arguments": [(["vehicle_id"], {})], "groups": [],
        "handler": lambda args: pave_read(args, "vehicle_id", "VAN", "/vehicles/{}/pave-reports"),
    },
    {
        "command": "body-repair pave-reports", "tool": "list_body_repair_pave_reports",
        "grant": "body_repair.pave.list.v1",
        "arguments": [(["req_id"], {})], "groups": [],
        "handler": lambda args: pave_read(args, "req_id", "BRR", "/body-repair/requests/{}/pave"),
    },
    {
        "command": "body-repair pave-comparison", "tool": "compare_body_repair_pave_reports",
        "grant": "body_repair.pave.compare.v1",
        "arguments": [(["req_id"], {})], "groups": [],
        "handler": lambda args: pave_read(args, "req_id", "BRR", "/body-repair/requests/{}/pave/comparison"),
    },
    {
        "command": "auth whoami",
        "tool": "whoami",
        "grant": "identity.get.v1",
        "arguments": [],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).whoami(),
    },
    {
        "command": "health check",
        "tool": "health_check",
        "grant": None,
        "arguments": [],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).public_request("GET", "/health"),
    },
    {
        "command": "health ready",
        "tool": "health_ready",
        "grant": None,
        "arguments": [],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).public_request(
            "GET", "/health/ready"
        ),
    },
    {
        "command": "search",
        "tool": "search",
        "grant": "search.list.v1",
        "arguments": [(["query"], {}), (["--limit"], {"type": "int"})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", "/search", query=handlers.clean_query({"q": args.query, "limit": args.limit})
        ),
    },
    {
        "command": "work-order list",
        "tool": "list_work_orders",
        "grant": "work_orders.list.v1",
        "arguments": [
            (["--limit"], {"type": "int"}),
            (["--status"], {}),
            (["--vendor-workshop-id"], {}),
            (["--dsp-id"], {}),
            (["--vehicle-id"], {}),
        ],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET",
            "/work-orders",
            query=handlers.vars_to_query(
                args,
                [
                    "status",
                    "vendor_workshop_id",
                    "dsp_id",
                    "vehicle_id",
                    "limit",
                    "offset",
                    "assigned_to_me",
                    "scheduled_within_hours",
                    "scheduled_from_now",
                    "scheduled",
                    "has_confirmed_pickup",
                    "at_shop_custody",
                    "returned_within_hours",
                    "current_relationship_only",
                ],
            ),
        ),
    },
    {
        "command": "work-order get",
        "tool": "get_work_order",
        "grant": "work_orders.get.v1",
        "arguments": [(["wo_id"], {})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/work-orders/{args.wo_id}"
        ),
    },
    {
        "command": "work-order assignment get",
        "tool": "get_work_order_assignment",
        "grant": "work_orders.assignment.get.v1",
        "arguments": [(["wo_id"], {})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/work-orders/{args.wo_id}/assignment"
        ),
    },
    {
        "command": "work-order scheduling-defaults",
        "tool": "get_work_order_scheduling_defaults",
        "grant": "work_orders.scheduling_defaults.get.v1",
        "arguments": [
            (["wo_id"], {}),
            (["--mode"], {"default": "schedule", "choices": ["schedule", "visit"]}),
        ],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/work-orders/{args.wo_id}/scheduling-defaults", query={"mode": args.mode}
        ),
    },
    {
        "command": "work-order wait",
        "tool": "wait_work_order",
        "grant": "work_orders.get.v1",
        "arguments": [
            (["wo_id"], {}),
            (
                ["--until"],
                {
                    "required": True,
                    "help": "Comma-separated target statuses, for example completed,canceled.",
                },
            ),
            (["--interval"], {"default": 15.0, "type": "float", "help": "Seconds between polls."}),
            (
                ["--max-wait"],
                {
                    "default": 900.0,
                    "type": "float",
                    "help": "Give up after this many seconds and exit 3.",
                },
            ),
        ],
        "groups": [],
        "handler": handlers.cmd_work_order_wait,
    },
    {
        "command": "work-order line-items list",
        "tool": "list_work_order_line_items",
        "grant": "work_orders.get.v1",
        "arguments": [(["wo_id"], {})],
        "groups": [],
        "handler": handlers.cmd_work_order_line_items_list,
    },
    {
        "command": "work-order list-notes",
        "tool": "list_work_order_notes",
        "grant": "work_orders.notes.list.v1",
        "arguments": [(["wo_id"], {})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/work-orders/{args.wo_id}/notes"
        ),
    },
    {
        "command": "work-order activity",
        "tool": "list_work_order_activity",
        "grant": "work_orders.activity.list.v1",
        "arguments": [(["wo_id"], {})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/work-orders/{args.wo_id}/activity"
        ),
    },
    {
        "command": "team repair-bucket-defaults",
        "tool": "get_repair_bucket_defaults",
        "grant": "teams.repair_bucket_defaults.v1",
        "arguments": [(["--vendor-workshop-id"], {"required": True, "type": "positive_id"})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET",
            "/teams/repair-bucket-defaults",
            query={"vendor_workshop_id": args.vendor_workshop_id},
        ),
    },
    {
        "command": "vehicle list",
        "tool": "list_vehicles",
        "grant": "vehicles.list_full.v1",
        "arguments": [
            (["--page"], {"type": "int"}),
            (["--per-page"], {"type": "int"}),
            (["--search"], {}),
            (["--dsp-id"], {}),
            (
                ["--status"],
                {
                    "choices": ["active", "inactive", "all", "grounded"],
                    "help": "Vehicle state filter translated to the API's is_active/grounded parameters.",
                },
            ),
        ],
        "groups": [],
        "handler": handlers.cmd_vehicle_list,
    },
    {
        "command": "vehicle get",
        "tool": "get_vehicle",
        "grant": "vehicles.get_full.v1",
        "arguments": [(["vehicle_id"], {})],
        "groups": [],
        "handler": handlers.cmd_vehicle_get,
    },
    {
        "command": "vehicle list-notes",
        "tool": "list_vehicle_notes",
        "grant": "vehicles.notes.list.v1",
        "arguments": [(["vehicle_id"], {}), (["--limit"], {"type": "int", "default": 50})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/vehicles/{args.vehicle_id}/notes", query={"limit": args.limit}
        ),
    },
    {
        "command": "vehicle list-checkouts",
        "tool": "list_vehicle_checkouts",
        "grant": "vehicles.checkouts.list.v1",
        "arguments": [(["vehicle_id"], {})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/vehicles/{args.vehicle_id}/checkouts"
        ),
    },
    {
        "command": "vehicle-report list",
        "tool": "list_vehicle_reports",
        "grant": "vehicle_reports.list.v1",
        "arguments": [
            (["--status"], {"choices": ["pending", "promoted", "handled"]}),
            (["--external-ref"], {}),
            (["--updated-since"], {"type": "iso_datetime_arg"}),
            (["--page"], {"default": 1, "type": "positive_int"}),
            (["--per-page"], {"default": 20, "type": "bounded_report_page_size"}),
        ],
        "groups": [],
        "handler": handlers.cmd_vehicle_report_list,
    },
    {
        "command": "vehicle-report get",
        "tool": "get_vehicle_report",
        "grant": "vehicle_reports.get.v1",
        "arguments": [(["report_id"], {})],
        "groups": [],
        "handler": handlers.cmd_vehicle_report_get,
    },
    {
        "command": "vehicle-report pull",
        "tool": "pull_vehicle_reports",
        "grant": "vehicle_reports.list.v1",
        "arguments": [
            (["--status"], {"choices": ["pending", "promoted", "handled"]}),
            (["--external-ref"], {}),
            (["--cursor-file"], {"help": "Default: user data dir vehicle_reports_cursor.json."}),
            (["--out"], {"help": "Write the JSON package to this file instead of stdout."}),
            (["--per-page"], {"default": 100, "type": "bounded_report_page_size"}),
        ],
        "groups": [],
        "handler": handlers.cmd_vehicle_report_pull,
    },
    {
        "command": "defect list",
        "tool": "list_defects",
        "grant": "defects.list.v1",
        "arguments": [
            (["--page"], {"type": "int"}),
            (["--per-page"], {"type": "int"}),
            (["--vehicle-id"], {}),
            (["--status"], {"help": "Client-side filter; /v1/defects does not accept status."}),
        ],
        "groups": [],
        "handler": handlers.cmd_defect_list,
    },
    {
        "command": "defect get",
        "tool": "get_defect",
        "grant": "defects.get.v1",
        "arguments": [(["defect_id"], {})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/defects/{args.defect_id}"
        ),
    },
    {
        "command": "defect list-comments",
        "tool": "list_defect_comments",
        "grant": "defects.comments.list.v1",
        "arguments": [(["defect_id"], {})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", f"/defects/{args.defect_id}/comments"
        ),
    },
    {
        "command": "defect catalog",
        "tool": "get_defect_catalog",
        "grant": "defect_catalog.get.v1",
        "arguments": [
            (
                ["--vehicle-class"],
                {
                    "choices": [
                        "custom_delivery_van",
                        "regular_cargo_van",
                        "step_van_dot",
                        "electric_vehicle",
                        "box_truck_dot",
                    ],
                    "help": "Fetch the live catalog for one vehicle class.",
                },
            ),
            (
                ["--all"],
                {
                    "nargs": 0,
                    "default": False,
                    "action": "store_true",
                    "help": "Fetch and combine the live catalogs for every vehicle class.",
                },
            ),
            (["--dsp-id"], {"help": "Optional DSP scope for fleet-specific overrides."}),
        ],
        "groups": [{"required": True, "arguments": ["vehicle_class", "all"]}],
        "handler": handlers.cmd_defect_catalog,
    },
    {
        "command": "defect photos",
        "tool": "download_defect_photos",
        "grant": "defects.photos.list.v1",
        "arguments": [
            (["defect_ids"], {"nargs": "+", "help": "Defect ids, for example FD-8125."}),
            (
                ["--out"],
                {
                    "required": True,
                    "help": "Folder to save photos into (one subfolder per defect).",
                },
            ),
        ],
        "groups": [],
        "handler": handlers.cmd_defect_photos,
    },
    {
        "command": "defect pull",
        "tool": "pull_defects",
        "grant": "defects.list.v1",
        "arguments": [
            (["--vehicle"], {"dest": "vehicle_id", "help": "Vehicle id, for example VAN-00042."}),
            (
                ["--new"],
                {
                    "nargs": 0,
                    "default": False,
                    "action": "store_true",
                    "help": "Pull defects newer than the cursor file.",
                },
            ),
            (["--out"], {"help": "Write the JSON package to this file instead of stdout."}),
            (["--cursor-file"], {"help": "Cursor file for --new. Default: user data dir."}),
            (["--per-page"], {"default": 50, "type": "int"}),
        ],
        "groups": [{"required": True, "arguments": ["vehicle_id", "new"]}],
        "handler": handlers.cmd_defect_pull,
    },
    {
        "command": "notification list",
        "tool": "list_notifications",
        "grant": "notifications.list.v1",
        "arguments": [(["--limit"], {"type": "int"}), (["--offset"], {"type": "int"})],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", "/notifications", query=handlers.vars_to_query(args, ["limit", "offset"])
        ),
    },
    {
        "command": "notification unread-count",
        "tool": "get_notification_counts",
        "grant": "notifications.counts.get.v1",
        "arguments": [],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", "/notifications/unread-count"
        ),
    },
    {
        "command": "notification preferences",
        "tool": "get_notification_preferences",
        "grant": "notifications.preferences.get.v1",
        "arguments": [],
        "groups": [],
        "handler": lambda args: handlers.client_from_args(args).request(
            "GET", "/notifications/preferences"
        ),
    },
]

# Retain the additional filters already shipped by the public client. Legacy
# defaults remain omitted so existing command output and request shapes survive.
for entry in READ_COMMANDS:
    if entry["command"] == "work-order list":
        entry["arguments"] += [
            (["--" + name.replace("_", "-")], {"type": "int"})
            for name in ("offset", "scheduled_within_hours", "returned_within_hours")
        ]
        entry["arguments"] += [
            (["--" + name.replace("_", "-")], {"action": "BooleanOptionalAction", "default": None})
            for name in (
                "assigned_to_me",
                "scheduled_from_now",
                "scheduled",
                "has_confirmed_pickup",
                "at_shop_custody",
                "current_relationship_only",
            )
        ]
    elif entry["command"] == "vehicle list":
        entry["arguments"] += [
            (["--fleet-id"], {}),
            (["--grounded"], {"action": "store_true", "default": None}),
        ]
    elif entry["command"] == "defect list":
        entry["arguments"] += [
            (["--" + name.replace("_", "-")], {}) for name in ("dsp_id", "inspection_id", "source")
        ]
        entry["arguments"] += [
            (["--" + name.replace("_", "-")], {"type": "iso_date_arg"})
            for name in ("date_from", "date_to")
        ]
        entry["arguments"] += [(["--tz-offset-minutes"], {"type": "int"})]
        entry["arguments"] += [
            (["--" + name.replace("_", "-")], {"action": "BooleanOptionalAction", "default": None})
            for name in ("open_only", "include_no_shop")
        ]
