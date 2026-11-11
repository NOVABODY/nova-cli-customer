"""Typed workflow reads preserve the API's role-filtered response."""
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

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
    rule: Literal['value_allocations_v4', 'sliding_allocations_v3', 'allocated_declines_v2', 'legacy_tiers']
    threshold: int | float | None = None
    high: int | float | None = None
    low: int | float | None = None
    line_base_price: int | float | None = None
    first_limit: int | float | None = None
    second_limit: int | float | None = None
    first_percent: int | float | None = None
    second_percent: int | float | None = None
    tail_percent: int | float | None = None

class Offer(Record):
    browser_url: str | None = None
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
    browser_url: str | None = None
    ref: str
    status: str
    report: MaskedReport | None

class Van(Record):
    browser_url: str | None = None
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
DESCRIPTIONS = {'list_bundle_offers': 'Read bundle offers, responsibility counts and deadlines. Open browser_url to buy in the browser. / Consulta ofertas de paquetes, responsables y plazos. Abre browser_url para comprar en el navegador.', 'get_bundle_offer_report': 'Read a masked report and frozen pricing terms. / Consulta un informe sin datos privados y los precios fijados.', 'list_bought_bundle_vans': 'Read bought van steps, prices and permitted details. Open browser_url for initial pickup or payment changes. / Consulta pasos, precios y datos permitidos de las vans compradas. Abre browser_url para la recogida inicial o cambios de pago.'}

def web_origin(client):
    return urlsplit(getattr(getattr(client, 'profile', None), 'api', ''))._replace(path='', query='', fragment='').geturl()


def safe_browser_urls(value, origin, ref=None):
    """Keep only bundle links on the configured Nova HTTPS origin."""
    if isinstance(value, list):
        return [safe_browser_urls(row, origin, ref) for row in value]
    if not isinstance(value, dict):
        return value
    ref = value.get('ref', ref)
    result = {key: safe_browser_urls(item, origin, ref) for key, item in value.items()}
    link = result.get('browser_url')
    if link is None:
        return result
    try:
        target, configured = urlsplit(link), urlsplit(origin)
        allowed = (isinstance(ref, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,79}', ref)
            and target.scheme == configured.scheme == 'https' and configured.hostname
            and (target.hostname, target.port if target.port is not None else 443)
            == (configured.hostname, configured.port if configured.port is not None else 443)
            and target.username is None and target.password is None
            and configured.username is None and configured.password is None
            and target.path == '/bundle-offers/' + ref
            and not any(char.isspace() or ord(char) < 32 or char == chr(92) for char in link))
    except (ValueError, TypeError):
        allowed = False
    if not allowed:
        result.pop('browser_url')
        result['browser_url_note'] = 'Browser link removed. Read the vans. / Se quitó el enlace del navegador. Consulta las vans.'
    return result


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
    return safe_browser_urls(value, web_origin(client), getattr(query, 'ref', None))

def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.bundle_workflow_tool
    return execute(client_from_args(args), name, {key: getattr(args, key) for key in MODELS[name].model_fields})
COMMANDS = [{'command': 'bundle-workflow ' + action, 'tool': name, 'grant': grant, 'description': DESCRIPTIONS[name], 'arguments': [] if action == 'list' else [(['ref'], {})], 'groups': [], 'handler': command, 'defaults': {'bundle_workflow_tool': name}} for action, name, grant in [('list', 'list_bundle_offers', 'capacity.offers.list.v1'), ('report', 'get_bundle_offer_report', 'capacity.offers.report.v1'), ('vans', 'list_bought_bundle_vans', 'capacity.vans.list.v1')]]
