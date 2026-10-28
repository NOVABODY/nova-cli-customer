"""Offline discovery of registered customer commands; never a permission grant."""

import argparse

from nova_cli_public import __version__
from nova_cli_public.errors import UsageError
from nova_cli_public.event_commands import EVENT_LOCAL_TOOLS
from nova_cli_public.read_routes import READ_POST_ROUTES, READ_ROUTES
from nova_cli_public.reads import BY_COMMAND, BY_TOOL, CustomerReadService, input_model
from nova_cli_public.write_routes import PHOTO_COMMIT_GRANTS, WRITE_ROUTES

# Only effect/usage information lives here. Arguments come from the real parser;
# fleet input/output contracts come from the same models used during execution.
DETAILS = {
    **{"inspection-confirmation " + action: (description, ["remote_write" if action in {"set-settings", "respond"} else "remote_read"], example)
       for action, description, example in [
           ("settings", "Read inspection confirmation settings.", "nova inspection-confirmation settings DSP-7"),
           ("set-settings", "Change selected inspection confirmation settings.", "nova inspection-confirmation set-settings DSP-7 --enabled"),
           ("get", "Read an inspection confirmation.", "nova inspection-confirmation get DVIC-7"),
           ("respond", "Confirm or decline one inspection.", "nova inspection-confirmation respond DVIC-7 --response Y --expected-scheduled-at 2026-10-28T02:00:00Z --expected-confirmation-id 17"),
       ]},
    "daily-work scheduled": ("Read scheduled fleet work.", ["remote_read"], "nova daily-work scheduled DSP-7 --service-date 2026-06-14"),
    "report inspector-performance": ("Read inspector report quality.", ["remote_read"], "nova report inspector-performance"),
    "report driver-da-quality": ("Read driver report quality.", ["remote_read"], "nova report driver-da-quality"),
    "vendor-scorecard pending-feedback": ("Read repairs that need a rating.", ["remote_read"], "nova vendor-scorecard pending-feedback"),
    "vendor-scorecard problem-reports": ("Read vendor repair problem reports.", ["remote_read"], "nova vendor-scorecard problem-reports"),
    "fmc-company list": ("Read fleet and rental companies.", ["remote_read"], "nova fmc-company list"),
    "vehicle set-fmc-company": ("Set the fleet or rental company for a van.", ["remote_write"], "nova vehicle set-fmc-company VAN-7 --company-id FMC-8"),
    "repair-request preview-external-vendor-options": ("Read external repair provider options before a request exists.", ["remote_read"], "nova repair-request preview-external-vendor-options --vehicle-id VAN-7 --repair-type mechanical"),
    "repair-request dismiss-rental-routing": ("Dismiss a rental routing reminder.", ["remote_write"], "nova repair-request dismiss-rental-routing RR-7"),

    "vendor-scorecard get": ("Read vendor repair scores.", ["remote_read"], "nova vendor-scorecard get VW-7"),
    "vendor-scorecard benchmarks": ("Read vendor repair score comparisons.", ["remote_read"], "nova vendor-scorecard benchmarks VW-7"),
    **{'report ' + name: ('Read the ' + name.replace('-', ' ') + ' report.', ['remote_read'],
        'nova report ' + name) for name in ('work-order-completion', 'repair-metrics', 'inspection-compliance')},

    "fleet-updates list": ("Read Fleet Updates.", ["remote_read"], "nova fleet-updates list --group decide"),
    "fleet-issue resolve": ("Resolve a fleet issue with a native action.", ["remote_write"], "nova fleet-issue resolve 7 keep"),

    "repair-request cancel": ("Cancel a repair request and its open work orders. Completed requests stay fulfilled.", ["remote_write"], "nova repair-request cancel RR-7 --reason Done"),
    "vehicle update-note": ("Change a van note that you can manage.", ["remote_write"], "nova vehicle update-note VAN-7 3 --body Fixed"),
    "vehicle delete-note": ("Delete a van note that you can manage.", ["remote_write"], "nova vehicle delete-note VAN-7 3"),
    "defect set-cost": ("Set the defect cost estimate.", ["remote_write"], "nova defect set-cost FD-7 --estimated-cost 12.3450"),
    "vehicle create": ("Add a van with the required identity data.", ["remote_write"], "nova vehicle create --data '{\"fleet_id\":\"NEW1\",\"vin\":\"1FTBR1C80MKA12345\",\"plate\":\"NEW123\",\"year\":2021,\"make\":\"Ford\",\"model\":\"Transit\"}'"),
    "vehicle decode-vin": ("Read van data from a VIN.", ["remote_read"], "nova vehicle decode-vin 1FTBR1C80MKA12345"),
    "vehicle update": ("Change permitted van data.", ["remote_write"], "nova vehicle update VAN-1 --data '{\"plate\":\"NEW123\"}'"),
    "defect-review queue": ("List defects that need review.", ["remote_read"], "nova defect-review queue"),
    "defect-review history": ("Read defect review history.", ["remote_read"], "nova defect-review history FD-1"),
    "defect-review approve": ("Approve a defect and select its repair destination.", ["remote_write"], "nova defect-review approve FD-1"),
    "defect-review reject": ("Reject a defect.", ["remote_write"], "nova defect-review reject FD-1 --reject-reason-code duplicate"),
    "body-repair invoice": (
        "Download the available Body repair invoice or receipt PDF.",
        ["remote_read", "local_file_write"],
        "nova body-repair invoice BRR-1 --out invoice.pdf",
    ),
    "defect create": (
        "Report a defect and optionally select a repair shop.",
        ["remote_write"],
        "nova defect create --vehicle-id VAN-0001 --source maintenance_request --part headlight --defect-type not_working",
    ),

    "fleet-import preview": ("Check reviewed rows against current fleet data. This does not import vans.",
                             ["remote_read", "local_file_read"], "nova fleet-import preview --review-file reviewed.json"),
    "fleet-import apply": ("Import the agreed reviewed rows. Inspect row results before trying again.",
                           ["remote_write", "local_file_read"], "nova fleet-import apply --review-file reviewed.json"),
    "fleet-import review": (
        "Review a Cortex source file. Resend the unchanged file with cumulative JSON corrections.",
        ["remote_read", "local_file_read"], "nova fleet-import review --file fleet.csv --options '{}'",
    ),
    "capabilities": (
        "List the commands in this client. No account access is checked.",
        ["local_read"],
        "nova capabilities --json",
    ),
    "profile set": (
        "Save an API profile and select it. Use a separate profile for each API host.",
        ["local_config_write"],
        "nova profile set personal --api https://nova.example/api",
    ),
    "profile use": ("Select a saved profile.", ["local_config_write"], "nova profile use personal"),
    "profile show": ("Read a saved profile.", ["local_read"], "nova profile show personal"),
    "profile list": ("List saved profiles.", ["local_read"], "nova profile list"),
    "profile remove": (
        "Delete a profile and its local credentials; the server connection remains.",
        ["local_config_write", "local_credentials_delete"],
        "nova profile remove personal",
    ),
    "auth login": (
        "Open browser sign-in and consent. Store the refresh token in the OS keyring.",
        ["browser_handoff", "remote_authorization", "local_credentials_write"],
        "nova auth login",
    ),
    "auth status": (
        "Check local credential presence. This does not check server authorization.",
        ["local_credentials_read"],
        "nova auth status",
    ),
    "auth refresh": (
        "Rotate the connection refresh token.",
        ["remote_authorization", "local_credentials_write"],
        "nova auth refresh",
    ),
    "auth logout": (
        "Delete local credentials and request server disconnect. Check server_revoked; use browser settings if it is false.",
        ["local_credentials_delete", "remote_authorization"],
        "nova auth logout",
    ),
    "defect list": (
        "List defects that the account can read.",
        ["remote_read"],
        "nova defect list --open-only",
    ),
    "defect get": ("Read a defect.", ["remote_read"], "nova defect get FD-0001"),
    "work-order list": (
        "List work orders that the account can read.",
        ["remote_read"],
        "nova work-order list --limit 20",
    ),
    "work-order get": ("Read a work order.", ["remote_read"], "nova work-order get WO-0001"),
    "vehicle list": (
        "List active fleet vehicles that the account can read.",
        ["remote_read"],
        "nova vehicle list --page 1 --per-page 20",
    ),
    "vehicle get": (
        "Read a vehicle from the fleet list.",
        ["remote_read"],
        "nova vehicle get VAN-0001",
    ),
}


def command_parsers(parser, prefix=()):
    children = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not children:
        yield " ".join(prefix), parser
    for action in children:
        for name, child in action.choices.items():
            yield from command_parsers(child, (*prefix, name))


def argument_schema(parser):
    properties, required, arguments = {}, [], []
    for action in parser._actions:
        if action.dest == "help":
            continue
        positional = not action.option_strings
        schema = {"type": "integer" if action.type is int else "string"}
        if isinstance(
            action,
            (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse.BooleanOptionalAction),
        ):
            schema = {"type": "boolean"}
        if action.choices is not None:
            schema["enum"] = list(action.choices)
        if action.default not in (None, argparse.SUPPRESS):
            schema["default"] = action.default
        properties[action.dest] = schema
        if action.required:
            required.append(action.dest)
        arguments.append(
            {
                "name": action.dest,
                "flags": action.option_strings,
                "positional": positional,
                "required": action.required,
                **schema,
            }
        )
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }, arguments


def manifest(parser, selected=None):
    commands = []
    seen = set()
    for name, leaf in command_parsers(parser):
        if id(leaf) in seen:
            continue
        seen.add(id(leaf))
        description, effects, example = DETAILS.get(name, (name + ".", ["remote_read"], None))
        schema, arguments = argument_schema(leaf)
        entry = {
            "id": name.replace(" ", "."),
            "command": name,
            "description": description,
            "effects": effects,
            "examples": [example] if example else [],
            "arguments": arguments,
            "input_schema": schema,
            "availability": "implemented",
            "authorization": "not_checked",
            "required_scope": None,
        }
        if name in BY_COMMAND:
            operation = BY_COMMAND[name]
            tool = operation["tool"]
            entry.update(
                tool_input_schema=input_model(operation, mcp=True).model_json_schema(),
                output_schema=CustomerReadService(None).output_schema(tool),
                mcp_tool=tool,
                required_scope=operation.get("scope", "nova:read") if operation["grant"] else None,
                required_operation=operation["grant"],
                api_routes=[
                    {"method": "POST", "path_pattern": path}
                    for path, grant in READ_POST_ROUTES.items()
                    if grant == operation["grant"]
                ] + [
                    {"method": "GET", "path_pattern": path}
                    for path, grant in READ_ROUTES.items()
                    if grant == operation["grant"]
                ]
                + [
                    {"method": method, "path_pattern": path}
                    for (method, path), grant in WRITE_ROUTES.items()
                    if grant == operation["grant"]
                ],
            )
            if not operation.get("mcp", True):
                entry.update(mcp_tool=None, tool_input_schema=None, output_schema=None)
            if operation.get("document_kind") or operation.get("image_read"):
                entry['mcp_effects'] = ['remote_read']
            entry["input_schema"] = input_model(operation).model_json_schema()
            entry["effects"] = [operation.get("effect", "remote_read")] + (
                ["local_file_write"]
                if tool in ("download_defect_photos", "pull_defects", "pull_vehicle_reports", "download_body_repair_quote", "download_body_repair_scope", "download_body_repair_invoice", "download_body_repair_documentation", "download_body_repair_pave_image")
                else []
            )
        if name.startswith("events "):
            entry["effects"] = ["remote_read"] + (
                ["local_file_write"] if entry["mcp_tool"] in EVENT_LOCAL_TOOLS else []
            )
            entry["mcp_execution"] = (
                "One page per call; managed local inbox; explicit acknowledgment."
            )
        if name in ("fleet-import review", "fleet-import preview", "fleet-import apply"):
            entry["effects"].append("local_file_read")
        if name == "upload photo":
            entry["effects"].append("local_file_read")
            entry["conditional_operations"] = PHOTO_COMMIT_GRANTS
        if name in ("auth login", "auth refresh"):
            entry["required_scope"] = "nova:read"
        if selected is None or selected == name:
            commands.append(entry)
    if not commands:
        raise UsageError("Unknown customer command. Run nova capabilities for the full list.")
    return {
        "schema_version": 1,
        "client_version": __version__,
        "executables": ["nova", "nova-cli", "nova-mcp"],
        "authorization": "not_checked",
        "full_customer_parity": False,
        "legacy_customer_parity": True,
        "legacy_coverage_document": "docs/LegacyCliParity.md",
        "help_command": "nova --help",
        "version_command": "nova --version",
        "authorization_note": "Offline discovery does not check the deployment, connection, role, "
        "tenant, or record permissions. The API checks each request.",
        "coverage_document": "docs/CustomerParity.md",
        "mcp": {
            "command": "nova-mcp --profile PROFILE",
            "transport": "stdio",
            "install_extra": "nova-cli[mcp]",
            "requires": "Saved profile and browser login",
            "tools": list(BY_TOOL),
            "authorization": "not_checked",
        },
        "commands": commands,
    }


def render_toc(value):
    lines = [
        f"Nova CLI {value['client_version']} — available commands",
        "Account authorization: not checked. Full DSP/vendor parity: not yet available.",
        "",
    ]
    lines.extend(f"nova {c['command']} — {c['description']}" for c in value["commands"])
    lines.extend(
        [
            "",
            "Use --json for argument schemas, effects, scopes, and examples.",
            'Use --command "vehicle get" to inspect one command.',
            "See docs/CustomerParity.md for workflow coverage and remaining work.",
        ]
    )
    return "\n".join(lines)
