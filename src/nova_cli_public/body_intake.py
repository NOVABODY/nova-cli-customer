"""Native Body intake and PAVE capture handoffs; the API owns all workflow gates."""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nova_cli_public.errors import ApiError, UsageError

Positive = Annotated[int, Field(ge=1, le=2147483647)]
Key = Annotated[str, Field(min_length=1, max_length=500)]
Phase = Literal['pickup', 'post']
UNKNOWN = 'The outcome is unknown. Read the van or Body request before trying again. / El resultado no se conoce. Consulta el van o la solicitud de carrocería antes de intentar de nuevo.'


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Issue(Closed):
    description: str = Field(min_length=1, max_length=2000)
    photo_storage_key: Key | None = None
    photo_storage_keys: list[Key] = Field(default_factory=list, max_length=8)
    source: str | None = Field(default=None, max_length=50)
    defect_id: Positive | None = None


class DefectItem(Closed):
    defect_id: Positive
    fix_description: str = Field(min_length=1, max_length=2000)
    photo_keys: list[Key] = Field(default_factory=list, max_length=8)


class Component(Closed):
    item_no: int = Field(ge=0)
    component_name: str | None = Field(default=None, max_length=200)


class Pave(Closed):
    storage_key: Key
    file_size_bytes: Positive | None = None
    source: str | None = Field(default='upload', max_length=20)
    source_url: str | None = Field(default=None, max_length=1000)


class Intake(Closed):
    vehicle_id: Positive
    mode: Literal['text', 'parts', 'grade', 'rental'] = 'text'
    text_description: str | None = Field(default=None, max_length=2000)
    issues: list[Issue] = Field(default_factory=list, max_length=20)
    defect_items: list[DefectItem] = Field(default_factory=list, max_length=20)
    picked_components: list[Component] = Field(default_factory=list, max_length=100)
    target_grade: int | None = Field(default=None, ge=3, le=5)
    vendor_id: Positive | None = None
    service_station_code: str | None = Field(default=None, max_length=20)
    pave: Pave | None = None
    van_pave_report_id: Positive | None = None
    rental_pickup: Pave | None = None
    rental_pickup_van_report_id: Positive | None = None
    pave_waiver_reason: str | None = Field(default=None, max_length=2000)
    inspection_links: list[Annotated[str, Field(max_length=1000)]] | None = Field(default=None, max_length=2)


class Create(Closed):
    data: Intake


class Reference(Closed):
    request_ref: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')


class Add(Reference):
    text: str = Field(min_length=1, max_length=4000)
    phase: Phase | None = None


class Replace(Reference):
    key: str = Field(min_length=1, max_length=1000)
    url: str = Field(min_length=1, max_length=1000)


class Request(Reference):
    reason: str | None = Field(default=None, max_length=500)
    reason_code: str | None = Field(default=None, max_length=40)
    phase: Phase | None = None
    create_from_launcher: bool = False
    cancel_from_launcher: bool = False

    @model_validator(mode='after')
    def one_launcher_action(self):
        if self.create_from_launcher and self.cancel_from_launcher:
            raise ValueError('Select one action. / Selecciona una acción.')
        return self


class PickupDetails(Closed):
    expected_version: int | None = Field(default=None, ge=0)
    van_location: str = Field(min_length=1, max_length=400)
    key_location: str = Field(min_length=1, max_length=400)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, max_length=40)
    access_notes: str | None = Field(default=None, max_length=1000)


class SuggestedTime(Closed):
    proposed_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    pickup_window: str = Field(min_length=1, max_length=60)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def calendar_date(self):
        from datetime import date
        date.fromisoformat(self.proposed_date)
        return self


class SelectQuote(Reference):
    quote_id: Positive | Annotated[str, Field(min_length=1, max_length=100)]
    pickup_details: PickupDetails | None = None
    suggested_time: SuggestedTime | None = None
    grade: int | None = Field(default=None, ge=3, le=5)
    scope: Literal['new_damage'] | None = None
    pickup_report_id: Positive | None = None

    @model_validator(mode='after')
    def suggested_time_needs_details(self):
        if self.suggested_time is not None and self.pickup_details is None:
            raise ValueError('Add pickup details. / Añade los datos de recogida.')
        return self


class ConfirmPickup(Reference, PickupDetails):
    expected_version: int = Field(ge=0)


class AcceptPickup(Reference):
    expected_version: int = Field(ge=0)


STEPS = {
    'select_body_repair_quote': 'select-quote',
    'confirm_body_repair_pickup': 'confirm-pickup',
    'accept_body_repair_pickup': 'accept-pickup',
}
REREAD = 'Read the order and pickup_schedule_version before another attempt. / Consulta la orden y pickup_schedule_version antes de otro intento.'


ERRORS = {
    400: ('invalid_logistics', 'Check the quote and pickup details. / Comprueba la cotización y los datos de recogida.'),
    401: ('authentication_required', 'Sign in again. / Inicia sesión de nuevo.'),
    403: ('body_repair_denied', 'Check connection consent, role and Station access. / Comprueba los permisos de la conexión, el rol y el acceso a la Station.'),
    404: ('not_found', 'This order or quote is not available. / Esta orden o cotización no está disponible.'),
    409: ('body_repair_conflict', REREAD),
    422: ('invalid_arguments', 'Check the request fields. / Comprueba los campos de la solicitud.'),
    503: ('body_repair_unavailable', 'Station policy is not available. Read before another attempt. / La política de Station no está disponible. Consulta antes de otro intento.'),
}


class BodyResult(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str = Field(min_length=1)
    order_number: str | None
    status: str = Field(min_length=1)


NAMES = ('create_body_repair_request', 'add_body_repair_inspection_link',
    'replace_body_repair_inspection_link', 'request_body_repair_inspection_link', *STEPS)
MODELS = dict(zip(NAMES, (Create, Add, Replace, Request, SelectQuote, ConfirmPickup, AcceptPickup), strict=True))
WRITES = set(MODELS)
OUTPUTS = {name: BodyResult for name in NAMES}


def execute(client, name, arguments):
    value = MODELS[name].model_validate(arguments)
    if name == NAMES[0]:
        path, body = '/body-repair/requests', value.data.model_dump(exclude_unset=True)
    else:
        suffix = STEPS.get(name) or ('request-inspection-link' if name == NAMES[3] else 'inspection-links')
        path = f'/body-repair/requests/{value.request_ref}/{suffix}'
        body = value.model_dump(exclude={'request_ref'}, exclude_unset=True)
    try:
        result = client.request('PATCH' if name == NAMES[2] else 'POST', path, json_body=body, retry_auth=False)
    except ApiError as exc:
        if name in STEPS and exc.status == 403 and (exc.code == 'operation_requires_consent'
                or isinstance(exc.detail, dict) and exc.detail.get('code') == 'operation_requires_consent'):
            raise ApiError('Start a new connection and review its permissions. / Inicia una conexión nueva y revisa sus permisos.',
                status=403, code='connection_requires_consent') from exc
        if name in STEPS and exc.status in ERRORS:
            code, message = ERRORS[exc.status]
            raise ApiError(message, status=exc.status, code=code, detail=exc.detail) from exc
        if exc.status is None or exc.status >= 500 or 300 <= exc.status < 400:
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    try:
        OUTPUTS[name].model_validate(result)
        if len(json.dumps(result, allow_nan=False).encode()) > 2 * 1024 * 1024:
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise ApiError(UNKNOWN, code='outcome_unknown') from None
    return result


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.body_intake_tool
    values = {key: getattr(args, key) for key in MODELS[name].model_fields
        if getattr(args, key, None) is not None and getattr(args, key) is not False}
    for field in ('data', 'pickup_details', 'suggested_time'):
        if field not in values:
            continue
        try:
            if len(values[field].encode()) > 65536:
                raise ValueError()
            values[field] = json.loads(values[field])
        except (ValueError, TypeError):
            raise UsageError('Use a JSON object of at most 64 KiB. / Usa un objeto JSON de 64 KiB como máximo.') from None
    return execute(client_from_args(args), name, values)


_SPECS = [
    ('body-repair create', 'body_repair.requests.create.v1', 'Submit a Body repair request. / Envía una solicitud de reparación de carrocería.', [(['--data'], {'required': True})]),
    ('body-repair add-inspection-link', 'body_repair.inspection_links.add.v1', 'Add a PAVE capture link. / Añade un enlace de captura PAVE.', [(['request_ref'], {}), (['--text'], {'required': True}), (['--phase'], {'choices': ['pickup', 'post']})]),
    ('body-repair replace-inspection-link', 'body_repair.inspection_links.replace.v1', 'Replace a PAVE capture link. / Reemplaza un enlace de captura PAVE.', [(['request_ref'], {}), (['--key'], {'required': True}), (['--url'], {'required': True})]),
    ('body-repair request-inspection-link', 'body_repair.inspection_links.request.v1', 'Request, create, or cancel a capture link. Shop roles and order state apply. / Solicita, crea o cancela un enlace de captura. Se aplican el rol del taller y el estado de la orden.', [(['request_ref'], {}), (['--phase'], {'choices': ['pickup', 'post']}), (['--reason'], {}), (['--reason-code'], {}), (['--create-from-launcher'], {'action': 'store_true'}), (['--cancel-from-launcher'], {'action': 'store_true'})]),
    ('body-repair select-quote', 'body_repair.quotes.select.v1', 'Select a quote. Referral credit requires the browser. / Selecciona una cotización. El crédito por recomendación requiere el navegador.', [(['request_ref'], {}), (['--quote-id'], {'required': True}), (['--pickup-details'], {}), (['--suggested-time'], {}), (['--grade'], {'type': 'int', 'choices': [3, 4, 5]}), (['--scope'], {'choices': ['new_damage']}), (['--pickup-report-id'], {'type': 'int'})]),
    ('body-repair confirm-pickup', 'body_repair.pickup.confirm.v1', 'Confirm pickup locations. Use pickup_schedule_version as expected_version. / Confirma las ubicaciones de recogida. Usa pickup_schedule_version como expected_version.', [(['request_ref'], {}), (['--expected-version'], {'required': True, 'type': 'int'}), (['--van-location'], {'required': True}), (['--key-location'], {'required': True})] + [(['--' + field.replace('_', '-')], {}) for field in ('address', 'contact_name', 'contact_phone', 'access_notes')]),
    ('body-repair accept-pickup', 'body_repair.pickup.accept.v1', 'Accept the shop pickup offer. Use pickup_schedule_version as expected_version. / Acepta la propuesta de recogida del taller. Usa pickup_schedule_version como expected_version.', [(['request_ref'], {}), (['--expected-version'], {'required': True, 'type': 'int'})]),
]
COMMANDS = [{'command': spec[0], 'tool': name, 'grant': spec[1], 'description': spec[2] + ' ' + UNKNOWN,
    'arguments': spec[3], 'groups': [], 'handler': command, 'defaults': {'body_intake_tool': name},
    'scope': 'nova:read nova:write', 'effect': 'remote_write'} for name, spec in zip(NAMES, _SPECS, strict=True)]
