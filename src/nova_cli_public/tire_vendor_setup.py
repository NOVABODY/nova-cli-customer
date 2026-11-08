"""Station tire vendor choices and setup contacts, separate from referrals."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nova_cli_public import legacy_reads
from nova_cli_public.errors import ApiError


class Scope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    dsp_id: str | None = Field(default=None, pattern=r'^(?:DSP-)?[0-9]{1,9}$')


class Add(Scope):
    station_code: str = Field(min_length=1, max_length=20)
    vendor_workshop_id: int = Field(gt=0, le=2147483647)


class Share(Scope):
    station_code: str = Field(min_length=1, max_length=20)
    vendor_name: str = Field(min_length=1, max_length=160)
    contact_name: str = Field(min_length=1, max_length=160)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=40)

    @model_validator(mode='after')
    def require_contact(self):
        if not (self.contact_email or self.contact_phone):
            raise ValueError('Enter an email or phone. / Introduce un correo o teléfono.')
        return self


class ListRequests(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: int | None = Field(default=None, gt=0, le=2147483647)


class Handle(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: int = Field(gt=0, le=2147483647)


class Vendor(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int
    name: str
    added: bool


class Saved(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int
    dsp_id: int
    station_id: int
    status: Literal['submitted', 'handled']
    vendor_name: str
    contact_name: str
    contact_email: str | None
    contact_phone: str | None


class Station(BaseModel):
    model_config = ConfigDict(strict=True)
    station_code: str
    station_name: str | None
    vendors: list[Vendor]
    request: Saved | None


class Choices(BaseModel):
    model_config = ConfigDict(strict=True)
    stations: list[Station]


class Requests(BaseModel):
    model_config = ConfigDict(strict=True)
    items: list[Saved]


class Added(BaseModel):
    model_config = ConfigDict(strict=True)
    dsp_id: int
    vendor_workshop_id: int
    repair_type: Literal['tires']
    is_active: Literal[True]


MODELS = {'list_station_tire_vendors': Scope, 'add_station_tire_vendor': Add,
          'share_tire_vendor_contact': Share, 'list_vendor_setup_requests': ListRequests,
          'handle_vendor_setup_request': Handle}
OUTPUTS = dict(zip(MODELS, [Choices, Added, Saved, Requests, Saved]))
WRITES = {'add_station_tire_vendor', 'share_tire_vendor_contact', 'handle_vendor_setup_request'}
UNKNOWN = 'outcome_unknown: Read the saved request or vendor choices before retrying. / Consulta la solicitud o los proveedores antes de reintentar.'


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    body = query.model_dump(exclude={'dsp_id', 'request_id'}, exclude_none=True)
    path = '/onboarding/dsp/tire-vendors'
    method = 'GET'
    if name == 'share_tire_vendor_contact':
        path, method = '/onboarding/dsp/tire-vendor-requests', 'POST'
    elif name == 'add_station_tire_vendor':
        method = 'POST'
    elif name == 'list_vendor_setup_requests':
        path = '/vendor-setup-requests'
    elif name == 'handle_vendor_setup_request':
        path, method, body = f'/vendor-setup-requests/{query.request_id}', 'PATCH', {'status': 'handled'}
    params = {key: value for key, value in query.model_dump(include={'dsp_id', 'request_id'}, exclude_none=True).items()
              if not (name == 'handle_vendor_setup_request' and key == 'request_id')}
    value = client.request(method, path, **({'params': params} if params else {}),
                           **({'json_body': body} if name in WRITES else {}))
    try:
        result = OUTPUTS[name].model_validate(value)
        json.dumps(value, allow_nan=False)
        if name in WRITES:
            if isinstance(query, Scope) and query.dsp_id and result.dsp_id != int(query.dsp_id.split('-')[-1]):
                raise ValueError('Wrong DSP')
            if name == 'add_station_tire_vendor' and result.vendor_workshop_id != query.vendor_workshop_id:
                raise ValueError('Wrong vendor')
            if name == 'handle_vendor_setup_request' and (result.id != query.request_id or result.status != 'handled'):
                raise ValueError('Request was not handled')
            if name == 'share_tire_vendor_contact' and result.status != 'submitted':
                raise ValueError('Request was not submitted')
    except (ValueError, TypeError, RecursionError):
        raise ApiError(UNKNOWN if name in WRITES else 'Invalid tire vendor response.', code='outcome_unknown' if name in WRITES else 'invalid_response') from None
    return value


def run(args):
    name = args.tire_tool
    return execute(legacy_reads.client_from_args(args), name, {key: getattr(args, key) for key in MODELS[name].model_fields
        if getattr(args, key, None) is not None})


COMMANDS = []
for action, name, grant, description, arguments in [
    ('list', 'list_station_tire_vendors', 'onboarding.tire_vendors.list.v1',
     'Read tire vendors for each Station. / Consulta proveedores de neumáticos por estación.', [(['--dsp-id'], {})]),
    ('add', 'add_station_tire_vendor', 'onboarding.tire_vendors.add.v1',
     'Add an eligible tire vendor. / Añade un proveedor de neumáticos disponible.',
     [(['station_code'], {}), (['vendor_workshop_id'], {'type': 'int'}), (['--dsp-id'], {})]),
    ('share-contact', 'share_tire_vendor_contact', 'vendor_setup_requests.create.v1',
     'Submit a vendor contact for admin setup. This does not add a vendor. / Envía un contacto para su alta por administradores. No añade un proveedor.',
     [(['station_code'], {}), (['--vendor-name'], {'required': True}), (['--contact-name'], {'required': True}),
      (['--contact-email'], {}), (['--contact-phone'], {}), (['--dsp-id'], {})]),
    ('requests', 'list_vendor_setup_requests', 'vendor_setup_requests.list.v1',
     'Read vendor setup requests as site admin. / Consulta solicitudes de alta como administrador del sitio.', [(['--request-id'], {'type': 'int'})]),
    ('handle', 'handle_vendor_setup_request', 'vendor_setup_requests.handle.v1',
     'Mark a request handled after vendor administration. / Marca una solicitud atendida después del alta del proveedor.', [(['request_id'], {'type': 'int'})]),
]:
    COMMANDS.append({'command': 'tire-vendor ' + action, 'tool': name, 'grant': grant,
        'description': description, 'arguments': arguments, 'groups': [], 'handler': run, 'defaults': {'tire_tool': name},
        **({'scope': 'nova:read nova:write', 'effect': 'remote_write'} if name in WRITES else {})})
