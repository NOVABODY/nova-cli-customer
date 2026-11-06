"""Typed workflow reads preserve the API's role-filtered response."""
import json
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from nova_cli_public.errors import ApiError


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Reference(Query):
    ref: str = Field(pattern='^[A-Za-z0-9][A-Za-z0-9-]{0,79}$')

class Record(BaseModel):
    model_config = ConfigDict(extra='allow')

class Workflow(Record):
    step: int = Field(ge=1, le=6)
    action: Literal['send_details', 'record_authorization', 'book_pickup', 'wait_review', 'update_payment', 'wait_payment', 'wait_dsp', 'change_schedule', 'wait_arrival', 'repair', 'completed', 'ended', 'contact_nova', 'confirm_no_charge']
    owner: Literal['shop', 'nova', 'done']
    group: Literal['action_required', 'awaiting_nova', 'completed']
    deadline: AwareDatetime | None

class Summary(Record):
    action_required: int = Field(ge=0)
    awaiting_nova: int = Field(ge=0)
    completed: int = Field(ge=0)
    next_deadline: AwareDatetime | None
    timezone: str

class Pricing(Record):
    rule: Literal['allocated_declines_v2', 'legacy_tiers']
    threshold: int | float | None
    high: int | float | None
    low: int | float | None

class Offer(Record):
    ref: str
    status: str
    total_price_cents: int = Field(ge=0)
    workflow_summary: Summary | None = None

class Listing(Record):
    rows: list[Offer]

class MaskedReport(Record):
    pricing: Pricing
    units: list[dict[str, Any]]

class Report(Record):
    ref: str
    status: str
    report: MaskedReport | None

class Van(Record):
    unit: int = Field(ge=1)
    state: str
    workflow: Workflow
    fleet_label: str | None = None
    accepted_price_cents: int | None = Field(default=None, ge=0)
    pricing: Pricing | None = None

class Vans(Record):
    vans: list[Van]
MODELS = {'list_bundle_offers': Query, 'get_bundle_offer_report': Reference, 'list_bought_bundle_vans': Reference}
OUTPUTS = {'list_bundle_offers': Listing, 'get_bundle_offer_report': Report, 'list_bought_bundle_vans': Vans}
PATHS = {'list_bundle_offers': '', 'get_bundle_offer_report': '/{ref}/report', 'list_bought_bundle_vans': '/{ref}/vans'}
DESCRIPTIONS = {'list_bundle_offers': 'Read bundle offers, responsibility counts and deadlines. / Consulta ofertas de paquetes, responsables y plazos.', 'get_bundle_offer_report': 'Read a masked report and frozen pricing terms. / Consulta un informe sin datos privados y los precios fijados.', 'list_bought_bundle_vans': 'Read bought van steps, prices and permitted details. / Consulta pasos, precios y datos permitidos de las vans compradas.'}

def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    value = client.request('GET', '/bundle-offers' + PATHS[name].format(**query.model_dump()))
    try:
        parsed = OUTPUTS[name].model_validate(value)
        if name == 'list_bundle_offers' and any(row.status == 'awarded' and row.workflow_summary is None for row in parsed.rows):
            raise ValueError('Missing bought summary')
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ApiError('Unsupported bundle response. / Respuesta de paquete no compatible.') from None
    return value

def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.bundle_workflow_tool
    return execute(client_from_args(args), name, {key: getattr(args, key) for key in MODELS[name].model_fields})
COMMANDS = [{'command': 'bundle-workflow ' + action, 'tool': name, 'grant': grant, 'description': DESCRIPTIONS[name], 'arguments': [] if action == 'list' else [(['ref'], {})], 'groups': [], 'handler': command, 'defaults': {'bundle_workflow_tool': name}} for action, name, grant in [('list', 'list_bundle_offers', 'capacity.offers.list.v1'), ('report', 'get_bundle_offer_report', 'capacity.offers.report.v1'), ('vans', 'list_bought_bundle_vans', 'capacity.vans.list.v1')]]
