"""Shop quote inputs mirror API #6374. The API owns scope, pricing and state."""

import json
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def iso_date(value):
    date.fromisoformat(value)
    return value


Day = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"), AfterValidator(iso_date)]
Cents = Annotated[int, Field(ge=0)]
Hours = Annotated[float, Field(ge=0, le=9999, allow_inf_nan=False)]
Ref = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class Line(Closed):
    description: str | None = Field(default=None, max_length=300)
    parts_cents: Cents = 0
    labor_cents: Cents = 0
    line_kind: Literal["repair", "part", "sublet", "material", "misc"] = "repair"
    operation: str | None = Field(default=None, max_length=12)
    part_number: str | None = Field(default=None, max_length=60)
    part_description: str | None = Field(default=None, max_length=120)
    pave_component: str | None = Field(default=None, max_length=120)
    pave_item_nos: list[int] | None = Field(default=None, max_length=50)
    scope_role: Literal["priority", "scoped"] | None = None
    part_type: Literal["oem", "aftermarket", "recycled", "reconditioned"] | None = None
    part_qty: int | None = Field(default=None, ge=0, le=999)
    part_unit_cents: Cents | None = None
    body_labor_hours: Hours | None = None
    paint_labor_hours: Hours | None = None
    mechanical_labor_hours: Hours | None = None
    taxable: bool = True
    linked_components: list[str] | None = Field(default=None, max_length=50)


class Answer(Closed):
    index: int = Field(ge=0, le=200)
    outcome: Literal["covered", "added", "declined"]
    line_position: int | None = Field(default=None, ge=0, le=400)
    decline_reason: (
        Literal["needs_other_trade", "beyond_capability", "not_found", "already_repaired"] | None
    ) = None
    decline_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def complete(self):
        if (
            self.outcome == "declined"
            and self.decline_reason is None
            or self.outcome != "declined"
            and self.line_position is None
        ):
            raise ValueError(
                "Supply a decline reason or line position. / Indica un motivo de rechazo o la posición de línea."
            )
        return self


class Quote(Closed):
    based_on_scope_revision: int = Field(ge=1)
    scope_mode: Literal["guided", "freeform"] = "guided"
    line_items: list[Line] = Field(default_factory=list, max_length=400)
    body_labor_rate_cents: Cents | None = None
    paint_labor_rate_cents: Cents | None = None
    mechanical_labor_rate_cents: Cents | None = None
    duration_days: int | None = Field(default=None, ge=0, le=365)
    repair_start_date: Day | None = None
    repair_end_date: Day | None = None
    repair_pickup_window: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=2000)
    issue_resolutions: list[Answer] = Field(default_factory=list, max_length=200)


class Query(Closed):
    pass


class Reference(Closed):
    request_ref: Ref


class Submit(Reference):
    data: Quote


class Confirm(Reference):
    based_on_scope_revision: int = Field(ge=1)
    confirm: Literal[True]

    @model_validator(mode="before")
    @classmethod
    def explicit_true(cls, value):
        if isinstance(value, dict) and value.get("confirm") is not True:
            raise ValueError(
                "Use confirm:true after user approval. / Usa confirm:true después de la aprobación del usuario."
            )
        return value


class Withdraw(Reference):
    quote_id: Annotated[str, Field(pattern=r"^(?:BRQ-)?[0-9]{1,100}$")]


NAMES = (
    "list_body_repair_leads",
    "list_body_repair_quotes",
    "confirm_body_repair_scope",
    "submit_body_repair_quote",
    "withdraw_body_repair_quote",
)
MODELS = dict(zip(NAMES, (Query, Reference, Confirm, Submit, Withdraw), strict=True))
WRITES = set(NAMES[2:])
GRANTS = dict(
    zip(
        NAMES,
        (
            "body_repair.repair_leads.list.v1",
            "body_repair.quotes.list.v1",
            "body_repair.scope.confirm.v1",
            "body_repair.quotes.submit.v1",
            "body_repair.quotes.withdraw.v1",
        ),
        strict=True,
    )
)
DESCRIPTIONS = dict(
    zip(
        NAMES,
        (
            "List eligible Body repair leads. / Consulta oportunidades de reparación de carrocería.",
            "Read your shop quotes. / Consulta las cotizaciones de tu taller.",
            "Show the user the current scope changes and get their go-ahead before confirming review. Confirmation records agent provenance. / Muestra al usuario los cambios actuales del alcance y obtén su aprobación antes de confirmar la revisión. La confirmación registra el uso del asistente.",
            "Submit a shop quote. Read current scope first. USD cents, rates in cents/hour, time in hours. Never confirms scope. Leads omit duration, dates, pickup window; fleet-picks leads require guided scope. Use returned totals. / Envía una cotización del taller. Consulta primero el alcance actual. Usa centavos de USD, tarifas en centavos/hora y tiempo en horas. No confirma el alcance. Omite duración, fechas, ventana de recogida en oportunidades. Usa el alcance guided para selecciones de flota y los totales devueltos.",
            "Withdraw your active quote before selection. / Retira tu cotización activa antes de la selección.",
        ),
        strict=True,
    )
)
UNKNOWN = "The outcome is unknown. Read the request and quotes before trying again. / El resultado no se conoce. Consulta la solicitud y las cotizaciones antes de intentar de nuevo."
GUIDANCE = {
    400: "Invalid business input. / Datos de negocio no válidos.",
    401: "Identity expired, revoked or invalid. / Identidad vencida, revocada o no válida.",
    403: "Check consent, write scope, shop authority and bound acting user for machine writes. / Comprueba consentimiento, permiso de escritura, autoridad del taller y usuario vinculado para escrituras de máquina.",
    404: "Request or quote missing or outside your scope. / Solicitud o cotización ausente o fuera de tu alcance.",
    409: "Read current request scope and quotes. Review changes with the user before another attempt. / Consulta el alcance actual y las cotizaciones. Revisa los cambios con el usuario antes de otro intento.",
    422: "Check schema and scope coverage. / Comprueba el esquema y la cobertura del alcance.",
    429: "Rate limit reached. Do not retry a write automatically. / Límite de solicitudes alcanzado. No repitas una escritura automáticamente.",
}


FAILURE = "The request failed. / La solicitud falló."


def error_info(name, exc):
    uncertain = name in WRITES and exc.code == "outcome_unknown" and (
        exc.status is None or exc.status >= 500 or 300 <= exc.status < 400
    )
    code = exc.code
    if not (
        isinstance(code, str)
        and code.isascii()
        and code.replace("_", "").isalnum()
        and len(code) <= 80
    ):
        code = f"quote_http_{exc.status}" if exc.status is not None else "quote_unavailable"
    return {"code": code, "status": exc.status}, (
        UNKNOWN if uncertain else GUIDANCE.get(exc.status, FAILURE)
    )


def prepare(name, value):
    if name == NAMES[0]:
        return "GET", "/body-repair/repair-leads", None
    path = f"/body-repair/requests/{value.request_ref}"
    if name == NAMES[2]:
        return "POST", path + "/scope/read", value.model_dump(exclude={"request_ref"})
    if name == NAMES[4]:
        return "POST", path + f"/quotes/{value.quote_id}/withdraw", None
    return (
        ("POST", path + "/quotes", value.data.model_dump(exclude_unset=True))
        if name == NAMES[3]
        else ("GET", path + "/quotes", None)
    )


def valid(name, result):
    if not isinstance(result, dict):
        return False
    if name == NAMES[0]:
        return isinstance(result.get("items"), list)
    if name == NAMES[1]:
        return isinstance(result.get("request_id"), str) and isinstance(result.get("quotes"), list)
    if name == NAMES[2]:
        return type(result.get("scope_revision")) is int and isinstance(
            result.get("last_viewed_at"), str
        )
    if name == NAMES[3]:
        quote = result.get("quote")
        return (
            isinstance(quote, dict)
            and isinstance(quote.get("id"), str)
            and isinstance(quote.get("request_id"), str)
            and isinstance(quote.get("status"), str)
        )
    return isinstance(result.get("request"), dict) and isinstance(result.get("quote_id"), str)


def execute(client, name, arguments):
    from nova_cli_public.errors import ApiError

    value = MODELS[name].model_validate(arguments)
    method, path, body = prepare(name, value)
    try:
        result = client.request(
            method, path, **({"json_body": body, "retry_auth": False} if name in WRITES else {})
        )
    except ApiError as exc:
        if name in WRITES and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code="outcome_unknown") from exc
        error, message = error_info(name, exc)
        raise ApiError(message, status=exc.status, code=error["code"]) from None

    try:
        if (
            not valid(name, result)
            or len(json.dumps(result, allow_nan=False).encode()) > 2 * 1024 * 1024
        ):
            raise ValueError()
        if name == NAMES[2] and result["scope_revision"] != value.based_on_scope_revision:
            raise ValueError()
        if name == NAMES[4] and int(result["quote_id"].removeprefix("BRQ-")) != int(
            value.quote_id.removeprefix("BRQ-")
        ):
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise ApiError(
            UNKNOWN
            if name in WRITES
            else "Invalid quote response. / Respuesta de cotización no válida.",
            code="outcome_unknown" if name in WRITES else "invalid_response",
        ) from None
    return result


def command(args):
    from nova_cli_public.errors import UsageError
    from nova_cli_public.legacy_reads import client_from_args

    name = args.body_quotes_tool
    values = {
        key: getattr(args, key)
        for key in MODELS[name].model_fields
        if getattr(args, key, None) is not None
    }
    if "data" in values:
        try:
            if len(values["data"].encode()) > 1024 * 1024:
                raise ValueError()
            values["data"] = json.loads(values["data"])
        except (ValueError, TypeError):
            raise UsageError(
                "Use JSON of at most 1 MiB. / Usa JSON de 1 MiB como máximo."
            ) from None
    return execute(client_from_args(args), name, values)


_ARGUMENTS = [
    [],
    [(["request_ref"], {})],
    [
        (["request_ref"], {}),
        (["--based-on-scope-revision"], {"type": "int", "required": True}),
        (["--confirm"], {"action": "store_true", "required": True}),
    ],
    [(["request_ref"], {}), (["--data"], {"required": True})],
    [(["request_ref"], {}), (["quote_id"], {})],
]
COMMANDS = [
    {
        "command": "body-repair " + action,
        "tool": name,
        "grant": GRANTS[name],
        "description": DESCRIPTIONS[name] + (" " + UNKNOWN if name in WRITES else ""),
        "arguments": arguments,
        "groups": [],
        "handler": command,
        "defaults": {"body_quotes_tool": name},
        **({"scope": "nova:read nova:write", "effect": "remote_write"} if name in WRITES else {}),
    }
    for name, action, arguments in zip(
        NAMES,
        ("repair-leads", "quotes", "confirm-scope", "submit-quote", "withdraw-quote"),
        _ARGUMENTS,
        strict=True,
    )
]


def add_commands(sub):
    import argparse

    actions = next(
        item
        for item in sub.choices["body-repair"]._actions
        if isinstance(item, argparse._SubParsersAction)
    )
    for entry in COMMANDS:
        leaf = actions.add_parser(entry["command"].split()[1], help=entry["description"])
        for flags, options in entry["arguments"]:
            leaf.add_argument(*flags, **options)
        leaf.set_defaults(handler=command, **entry["defaults"])
