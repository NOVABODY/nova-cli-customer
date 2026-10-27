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
from nova_cli_public.events import cursor_reset_detail
from nova_cli_public.locking import profile_lock
from nova_cli_public.output import emit
from nova_cli_public.reads import register_commands
from nova_cli_public.tokens import KeyringTokenStore


def globals_for(parser, *, child=False):
    default = argparse.SUPPRESS if child else None
    parser.add_argument("--profile", default=default, help="Saved public profile.")
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS if child else False
    )

    for flag in ("quiet", "plain", "no-input"):
        options = ["--" + flag, "-q"] if flag == "quiet" else ["--" + flag]
        parser.add_argument(
            *options, action="store_true", default=argparse.SUPPRESS if child else False
        )
    parser.add_argument(
        "--verbose", "-v", action="count", default=argparse.SUPPRESS if child else 0
    )
    parser.add_argument("--timeout", type=float, default=argparse.SUPPRESS if child else 30.0)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="nova", description="Nova Fora customer CLI. Use browser sign-in and permitted customer workflows."
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
            command.add_argument(
                "--scope", choices=["nova:read", "nova:read nova:write"], default="nova:read"
            )
            command.add_argument("--operations", help="Space-separated operation IDs for consent.")
    register_commands(commands)

    seen = set()

    def walk(current):
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    if id(child) in seen:
                        continue
                    seen.add(id(child))
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
    return ApiClient(
        profile_from_args(args), KeyringTokenStore(), timeout=getattr(args, "timeout", 30)
    )


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
            delegated.login(
                client,
                operations=args.operations,
                **({"scope": args.scope} if args.scope != "nova:read" else {}),
            )
            if args.operations is not None or args.scope != "nova:read"
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


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        value = args.handler(args)
        emit(value, as_json=args.json, quiet=args.quiet)
        if getattr(args, 'read_command', '') in ('fleet-import preview', 'fleet-import apply') and value.get('ok') is False:
            return 1
        return 0
    except ValidationError:
        message = "Invalid read arguments or response."
        code = 2
    except NovaCliError as exc:
        # Read/auth errors stay redacted; mutation business rejections retain actionable data.
        from nova_cli_public.reads import BY_COMMAND, WRITE_TOOLS

        operation = BY_COMMAND.get(getattr(args, "read_command", ""), {})
        mutation = operation.get("tool") in WRITE_TOOLS
        reset = (
            cursor_reset_detail(exc) if operation.get("tool", "").startswith("events_") else None
        )
        if reset:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "cursor_expired",
                        "detail": reset,
                        "message": "Reconcile a snapshot, then run events init --reset.",
                    }
                ),
                file=sys.stderr,
            )
            return exc.exit_code
        if (
            mutation
            and isinstance(exc, ApiError)
            and (exc.status in (400, 409, 422) or exc.code == "outcome_unknown")
        ):
            value = {
                "ok": False,
                "error": {"code": exc.code or "business_error", "status": exc.status},
            }
            if exc.code == "outcome_unknown":
                value["error"]["message"] = (
                    "The change outcome is unknown. Check the record before trying again."
                )
            else:
                value["error"]["detail"] = exc.detail
            print(json.dumps(value), file=sys.stderr)
            return exc.exit_code
        message = (
            f"Nova request failed (HTTP {exc.status})." if isinstance(exc, ApiError) else str(exc)
        )
        if isinstance(exc, ApiError) and exc.status == 403 and getattr(args, "read_command", None):
            from nova_cli_public.reads import BY_COMMAND

            grant = BY_COMMAND[args.read_command]["grant"]
            scope = BY_COMMAND[args.read_command].get("scope", "nova:read")
            message += f' Check account access and approved operations. Request a new connection with nova auth login --scope "{scope}" --operations "{grant}".'
        code = exc.exit_code
    except KeyboardInterrupt:
        message = "Interrupted."
        code = 130
    print(json.dumps({"ok": False, "error": message}) if args.json else message, file=sys.stderr)
    return code
