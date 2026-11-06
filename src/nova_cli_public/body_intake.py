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


class BodyResult(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str = Field(min_length=1)
    order_number: str | None
    status: str = Field(min_length=1)


NAMES = ('create_body_repair_request', 'add_body_repair_inspection_link',
    'replace_body_repair_inspection_link', 'request_body_repair_inspection_link')
MODELS = dict(zip(NAMES, (Create, Add, Replace, Request), strict=True))
WRITES = set(MODELS)
OUTPUTS = {name: BodyResult for name in NAMES}


def execute(client, name, arguments):
    value = MODELS[name].model_validate(arguments)
    if name == NAMES[0]:
        path, body = '/body-repair/requests', value.data.model_dump(exclude_unset=True)
    else:
        suffix = 'request-inspection-link' if name == NAMES[3] else 'inspection-links'
        path = f'/body-repair/requests/{value.request_ref}/{suffix}'
        body = value.model_dump(exclude={'request_ref'}, exclude_unset=True)
    try:
        result = client.request('PATCH' if name == NAMES[2] else 'POST', path, json_body=body, retry_auth=False)
    except ApiError as exc:
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
    if name == NAMES[0]:
        try:
            if len(values['data'].encode()) > 65536:
                raise ValueError()
            values['data'] = json.loads(values['data'])
        except (ValueError, TypeError):
            raise UsageError('Use a JSON object of at most 64 KiB. / Usa un objeto JSON de 64 KiB como máximo.') from None
    return execute(client_from_args(args), name, values)


_SPECS = [
    ('body-repair create', 'body_repair.requests.create.v1', 'Submit a Body repair request. / Envía una solicitud de reparación de carrocería.', [(['--data'], {'required': True})]),
    ('body-repair add-inspection-link', 'body_repair.inspection_links.add.v1', 'Add a PAVE capture link. / Añade un enlace de captura PAVE.', [(['request_ref'], {}), (['--text'], {'required': True}), (['--phase'], {'choices': ['pickup', 'post']})]),
    ('body-repair replace-inspection-link', 'body_repair.inspection_links.replace.v1', 'Replace a PAVE capture link. / Reemplaza un enlace de captura PAVE.', [(['request_ref'], {}), (['--key'], {'required': True}), (['--url'], {'required': True})]),
    ('body-repair request-inspection-link', 'body_repair.inspection_links.request.v1', 'Request, create, or cancel a capture link. Shop roles and order state apply. / Solicita, crea o cancela un enlace de captura. Se aplican el rol del taller y el estado de la orden.', [(['request_ref'], {}), (['--phase'], {'choices': ['pickup', 'post']}), (['--reason'], {}), (['--reason-code'], {}), (['--create-from-launcher'], {'action': 'store_true'}), (['--cancel-from-launcher'], {'action': 'store_true'})]),
]
COMMANDS = [{'command': spec[0], 'tool': name, 'grant': spec[1], 'description': spec[2] + ' ' + UNKNOWN,
    'arguments': spec[3], 'groups': [], 'handler': command, 'defaults': {'body_intake_tool': name},
    'scope': 'nova:read nova:write', 'effect': 'remote_write'} for name, spec in zip(NAMES, _SPECS, strict=True)]
