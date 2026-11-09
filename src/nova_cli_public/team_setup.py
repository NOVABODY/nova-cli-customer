"""Closed team invitation and user-operated Roger setup contracts."""
import argparse
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Invite(Empty):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(min_length=1, max_length=80)
    org_id: int = Field(gt=0, le=2147483647)
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    language: Literal["en", "es"] | None = None
    station: str | None = Field(default=None, max_length=80)


class InvitationRef(Empty):
    invitation_id: str = Field(pattern=r"^INV-[0-9]{1,14}$")


class Channel(Empty):
    intake_channel_id: str | None = Field(default=None, max_length=80)


MODELS = {
    "list_team_invitations": Empty, "invite_team_member": Invite,
    "resend_team_invitation": InvitationRef, "revoke_team_invitation": InvitationRef,
    "get_slack_status": Empty, "start_slack_setup": Empty, "set_roger_intake_channel": Channel,
}
WRITES = set(MODELS) - {"list_team_invitations", "get_slack_status"}
OPERATIONS = dict(zip(MODELS, [
    "invitations.list.v1", "invitations.create.v1", "invitations.resend.v1",
    "invitations.revoke.v1", "slack.status.get.v1", "slack.setup.start.v1",
    "slack.channels.update.v1",
]))
DESCRIPTIONS = {
    "list_team_invitations": "List pending team invitations. The invitee gets the join link by email. / Consulta invitaciones pendientes. La persona invitada recibe el enlace por correo.",
    "invite_team_member": "Confirm the invitee email and role with the user before inviting. The invitee gets the join link by email. / Confirma el correo y el rol con el usuario antes de invitar. La persona invitada recibe el enlace por correo.",
    "resend_team_invitation": "Send the invitation again by email. This can renew an expired invitation. / Envía de nuevo la invitación por correo. Puede renovar una invitación vencida.",
    "revoke_team_invitation": "Revoke an invitation that was not accepted. / Revoca una invitación no aceptada.",
    "get_slack_status": "Read Roger setup status. / Consulta el estado de configuración de Roger.",
    "start_slack_setup": "Start Roger setup with write consent. Open authorize_url and select Allow in Slack. It expires within minutes, at most 600 seconds. Refresh or reconnect after expiry. / Inicia Roger con permiso de escritura. Abre authorize_url y selecciona Permitir en Slack. Caduca en minutos, como máximo 600 segundos. Actualiza o vuelve a conectar tras caducar.",
    "set_roger_intake_channel": "Set the Roger intake channel. Omit to keep it; null or blank clears it. / Configura el canal de entrada de Roger. Omite para conservarlo; null o vacío lo borra.",
}
MESSAGES = {
    400: "Check the role, organization or invitation status. / Comprueba el rol, la organización o el estado.",
    401: "Sign in again. / Inicia sesión de nuevo.",
    403: "Access denied. Check role, scope, binding and consent. / Acceso denegado. Comprueba rol, alcance, vínculo y permisos.",
    404: "Record missing or Slack unavailable. / No existe el registro o Slack no está disponible.",
    409: "Conflict. Read the current record before another attempt. / Conflicto. Consulta el registro antes de otro intento.",
    422: "Check invitation, Station and channel fields. / Comprueba los campos de invitación, estación y canal.",
    429: "Wait before another attempt. / Espera antes de otro intento.",
    503: "Service unavailable. Check status before another attempt. / Servicio no disponible. Consulta el estado antes de otro intento.",
}
CODES = {400: "invalid_request", 401: "authentication_required", 403: "forbidden",
         404: "not_found", 409: "conflict", 422: "invalid_arguments",
         429: "rate_limited", 503: "unavailable"}
UNKNOWN = "Check invitations or Slack status before another attempt. / Consulta las invitaciones o Slack antes de otro intento."


def error_message(status, code):
    if code == "slack_setup_reconnect_required":
        return "Refresh or reconnect to Nova Fora. Then start Slack setup again. / Actualiza o vuelve a conectar con Nova Fora. Después, inicia Slack de nuevo."
    if code == "invitation_platform_connection_denied":
        return "Use the web app to manage platform invitations. / Usa la aplicación web para gestionar invitaciones de plataforma."
    return MESSAGES.get(status, UNKNOWN)


def safe_code(code, status):
    return code if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code) else CODES.get(status, "outcome_unknown")


def target(name, arguments):
    query = MODELS[name].model_validate(arguments)
    body = query.model_dump(exclude_unset=True, exclude={"invitation_id"})
    routes = {
        "list_team_invitations": ("GET", "/auth/invitations"),
        "invite_team_member": ("POST", "/auth/invitations"),
        "get_slack_status": ("GET", "/slack/installation/status"),
        "start_slack_setup": ("GET", "/slack/oauth/initiate"),
        "set_roger_intake_channel": ("POST", "/slack/channels"),
    }
    if isinstance(query, InvitationRef):
        return ("POST" if name == "resend_team_invitation" else "DELETE",
                "/auth/invitations/" + query.invitation_id + ("/resend" if name == "resend_team_invitation" else ""), None)
    method, path = routes[name]
    return method, path, body if method == "POST" else None


def strip_links(value):
    if isinstance(value, dict):
        return {key: strip_links(item) for key, item in value.items() if key != "accept_url"}
    if isinstance(value, list):
        return [strip_links(item) for item in value]
    return value


def result(name, value):
    if name == "revoke_team_invitation":
        if value is not None:
            raise ValueError("Expected empty receipt")
        return {"revoked": True}
    if not isinstance(value, dict):
        raise TypeError("Expected object")
    if name == "start_slack_setup":
        if not isinstance(value.get("authorize_url"), str) or not value["authorize_url"]:
            raise ValueError("Missing authorization URL")
        return {"authorize_url": value["authorize_url"]}
    if name == "get_slack_status":
        if not isinstance(value.get("installed"), bool):
            raise ValueError("Missing installation status")
        return {key: value[key] for key in ("installed", "team_name", "installed_at", "intake_channel_id", "can_edit") if key in value}
    if name == "set_roger_intake_channel":
        if "intake_channel_id" not in value:
            raise ValueError("Missing channel")
        return {"intake_channel_id": value["intake_channel_id"]}
    if name == "list_team_invitations":
        if not isinstance(value.get("items"), list) or type(value.get("total")) is not int:
            raise ValueError("Missing invitation page")
    elif not isinstance(value.get("id"), str) or not re.fullmatch(r"INV-[0-9]{1,14}", value["id"]):
        raise ValueError("Missing invitation receipt")
    return strip_links(value)


def execute(client, name, arguments):
    from .errors import ApiError

    method, path, body = target(name, arguments)
    kwargs = {"retry_auth": False} if name in WRITES else {}
    if body is not None:
        kwargs["json_body"] = body
    if name == "list_team_invitations":
        kwargs["params"] = {"status": "pending"}
    try:
        value = client.request(method, path, **kwargs)
    except ApiError as exc:
        code = safe_code(exc.code, exc.status)
        raise ApiError(error_message(exc.status, code), status=exc.status, code=code) from None
    try:
        return result(name, value)
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code="outcome_unknown" if name in WRITES else "invalid_response") from None


def run(args):
    from pydantic import ValidationError

    from .cli import client_from_args
    from .errors import UsageError

    try:
        return execute(args._client if hasattr(args, "_client") else client_from_args(args),
                       args.setup_tool, {key: getattr(args, key) for key in MODELS[args.setup_tool].model_fields
                                         if hasattr(args, key)})
    except ValidationError:
        raise UsageError("Check the setup fields. / Comprueba los campos de configuración.") from None


COMMANDS = []
for command, name, arguments in [
    ("team-invitation list", "list_team_invitations", []),
    ("team-invitation invite", "invite_team_member",
     [(["--email"], {"required": True}), (["--role"], {"required": True}),
      (["--org-id"], {"required": True, "type": "int"})] +
     [(["--" + field.replace("_", "-")], {}) for field in ("full_name", "phone", "language", "station")]),
    ("team-invitation resend", "resend_team_invitation", [(["invitation_id"], {})]),
    ("team-invitation revoke", "revoke_team_invitation", [(["invitation_id"], {})]),
    ("roger status", "get_slack_status", []),
    ("roger start", "start_slack_setup", []),
    ("roger channel", "set_roger_intake_channel",
     [(["--intake-channel-id"], {"default": argparse.SUPPRESS})]),
]:
    COMMANDS.append({"command": command, "tool": name, "grant": OPERATIONS[name],
        "description": DESCRIPTIONS[name], "arguments": arguments, "groups": [],
        "handler": run, "defaults": {"setup_tool": name},
        **({"scope": "nova:read nova:write", "effect": "remote_write"} if name in WRITES else {})})


def add_commands(sub):
    roots = {}
    for entry in COMMANDS:
        root, action = entry["command"].split()
        if root not in roots:
            roots[root] = sub.add_parser(root).add_subparsers(dest=root + "_command", required=True)
        parser = roots[root].add_parser(action, description=entry["description"])
        for flags, options in entry["arguments"]:
            options = dict(options)
            if options.get("type") == "int":
                options["type"] = int
            if flags[0].startswith("--") and "default" not in options:
                options["default"] = argparse.SUPPRESS
            parser.add_argument(*flags, **options)
        parser.set_defaults(handler=run, setup_tool=entry["tool"])
