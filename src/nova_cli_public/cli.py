"""Customer CLI: browser authorization and delegated customer reads."""

from __future__ import annotations

import argparse
import json
import os
import sys

from pydantic import ValidationError

from nova_cli_public import __version__, delegated
from nova_cli_public.client import ApiClient
from nova_cli_public.config import ConfigStore, require_profile_name
from nova_cli_public.errors import ApiError, NovaCliError
from nova_cli_public.fleet import DefectQuery, DelegatedService, WorkOrderQuery
from nova_cli_public.locking import profile_lock
from nova_cli_public.output import emit
from nova_cli_public.tokens import KeyringTokenStore


def globals_for(parser, *, child=False):
    default = argparse.SUPPRESS if child else None
    parser.add_argument("--profile", default=default, help="Saved public profile.")
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS if child else False
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="nova", description="Nova customer CLI. Browser sign-in and customer reads."
    )
    parser.add_argument("--version", action="version", version=f"nova-cli {__version__}")
    globals_for(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    discovery = commands.add_parser("capabilities", help="List available commands and schemas.")
    discovery.add_argument("--command", dest="selected_command", help="Inspect one command.")
    discovery.set_defaults(handler=cmd_capabilities)
    profiles = commands.add_parser("profile").add_subparsers(dest="action", required=True)
    create = profiles.add_parser("set")
    create.add_argument("name")
    create.add_argument("--api", required=True, help="Nova HTTPS URL ending in /api.")
    create.set_defaults(handler=cmd_profile_set)
    for name in ["use", "show", "remove"]:
        command = profiles.add_parser(name)
        command.add_argument("name")
        command.set_defaults(handler=cmd_profile)
    profiles.add_parser("list").set_defaults(handler=cmd_profile)
    auth = commands.add_parser("auth").add_subparsers(dest="action", required=True)
    for name in ["login", "status", "refresh", "logout"]:
        command = auth.add_parser(name)
        command.set_defaults(handler=cmd_auth)
        if name == "login":
            command.add_argument("--operations", help="Space-separated operation IDs for consent.")
    vehicles = commands.add_parser("vehicle").add_subparsers(dest="action", required=True)
    listing = vehicles.add_parser("list")
    listing.add_argument("--search")
    listing.add_argument("--fleet-id")
    listing.add_argument("--grounded", action="store_true", default=None)
    listing.add_argument("--page", type=int, default=1)
    listing.add_argument("--per-page", type=int, default=20)
    listing.set_defaults(handler=cmd_vehicle)
    detail = vehicles.add_parser("get")
    detail.add_argument("vehicle_id")
    detail.set_defaults(handler=cmd_vehicle)

    orders = commands.add_parser("work-order").add_subparsers(dest="action", required=True)
    listing = orders.add_parser("list")
    for name, field in WorkOrderQuery.model_fields.items():
        kwargs = {"default": field.default}
        if name in (
            "assigned_to_me",
            "scheduled_from_now",
            "scheduled",
            "has_confirmed_pickup",
            "at_shop_custody",
            "current_relationship_only",
        ):
            kwargs["action"] = argparse.BooleanOptionalAction
        else:
            kwargs["type"] = (
                str if name in ("status", "dsp_id", "vendor_workshop_id", "vehicle_id") else int
            )
        listing.add_argument("--" + name.replace("_", "-"), **kwargs)
    listing.set_defaults(handler=cmd_work_order)
    detail = orders.add_parser("get")
    detail.add_argument("work_order_id")
    detail.set_defaults(handler=cmd_work_order)

    defects = commands.add_parser("defect").add_subparsers(dest="action", required=True)
    listing = defects.add_parser("list")
    for name, field in DefectQuery.model_fields.items():
        kwargs = {"default": field.default}
        if name in ("open_only", "include_no_shop"):
            kwargs["action"] = argparse.BooleanOptionalAction
        else:
            kwargs["type"] = int if name in ("page", "per_page", "tz_offset_minutes") else str
        listing.add_argument("--" + name.replace("_", "-"), **kwargs)
    listing.set_defaults(handler=cmd_defect)
    detail = defects.add_parser("get")
    detail.add_argument("defect_id")
    detail.set_defaults(handler=cmd_defect)

    def walk(current):
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    globals_for(child, child=True)
                    walk(child)

    walk(parser)
    return parser


def cmd_capabilities(args):
    from nova_cli_public.capabilities import manifest, render_toc

    value = manifest(build_parser(), args.selected_command)
    return value if args.json else render_toc(value)


def profile_from_args(args):
    return ConfigStore().get_profile(args.profile or os.environ.get("NOVA_PUBLIC_PROFILE"))


def client_from_args(args):
    return ApiClient(profile_from_args(args), KeyringTokenStore())


def cmd_profile_set(args):
    with profile_lock(require_profile_name(args.name)):
        store = ConfigStore()
        # Changing the origin would orphan the old connection. Require a new profile.
        existing = store.load()["profiles"].get(args.name)
        if existing:
            store.get_profile(args.name, api_override=args.api)
        profile = store.set_profile(args.name, args.api)
    return {"profile": profile.name, "api": profile.api, "auth": "delegated"}


def cmd_profile(args):
    store = ConfigStore()
    if args.action == "list":
        current, profiles = store.list_profiles()
        return {
            "current_profile": current,
            "profiles": [{"name": p.name, "api": p.api} for p in profiles],
        }
    if args.action == "use":
        profile = store.use_profile(args.name)
    else:
        profile = store.get_profile(args.name)
    if args.action == "remove":
        with profile_lock(profile.name):
            profile = store.get_profile(profile.name)
            KeyringTokenStore().delete_refresh_token_strict(delegated.credential_profile(profile))
            store.remove_profile(profile.name)
        return {"removed": profile.name, "server_revoked": False}
    return {"profile": profile.name, "api": profile.api, "auth": "delegated"}


def cmd_auth(args):
    client = client_from_args(args)
    if args.action == "login":
        connection = (
            delegated.login(client, operations=args.operations)
            if args.operations is not None
            else delegated.login(client)
        )
        return {"ok": True, "profile": client.profile.name, "connection": connection}
    if args.action == "status":
        return delegated.status(client)
    if args.action == "refresh":
        client.refresh()
        return {"ok": True, "refreshed": True}
    client.logout()
    return {
        "ok": True,
        "local_credentials_cleared": True,
        "server_revoked": False,
        "disconnect_url": delegated.issuer(client.profile) + "/user-settings",
        "message": "Local credentials deleted. Use browser settings to disconnect the server connection.",
    }


def cmd_vehicle(args):
    values = (
        {"vehicle_id": args.vehicle_id}
        if args.action == "get"
        else {
            key: getattr(args, key)
            for key in ["search", "fleet_id", "grounded", "page", "per_page"]
        }
    )
    service = DelegatedService(client_from_args(args))
    return service.run("get_vehicle" if args.action == "get" else "list_vehicles", values)


def cmd_work_order(args):
    values = (
        {"work_order_id": args.work_order_id}
        if args.action == "get"
        else {key: getattr(args, key) for key in WorkOrderQuery.model_fields}
    )
    return DelegatedService(client_from_args(args)).run(
        "get_work_order" if args.action == "get" else "list_work_orders", values
    )


def cmd_defect(args):
    values = (
        {"defect_id": args.defect_id}
        if args.action == "get"
        else {key: getattr(args, key) for key in DefectQuery.model_fields}
    )
    return DelegatedService(client_from_args(args)).run(
        "get_defect" if args.action == "get" else "list_defects", values
    )


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        emit(args.handler(args), as_json=args.json)
        return 0
    except ValidationError:
        message = "Invalid read arguments or response."
        code = 2
    except NovaCliError as exc:
        # Never echo upstream response bodies or credentials.
        message = (
            f"Nova request failed (HTTP {exc.status})." if isinstance(exc, ApiError) else str(exc)
        )
        code = exc.exit_code
    except KeyboardInterrupt:
        message = "Interrupted."
        code = 130
    print(json.dumps({"ok": False, "error": message}) if args.json else message, file=sys.stderr)
    return code
