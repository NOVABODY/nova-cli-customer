"""Vendor AMR defaults and new bundle generation; the API owns authorization."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Pricing(Empty):
    first_percent: int = Field(ge=0, le=100)
    second_percent: int = Field(ge=0, le=100)
    tail_percent: int = Field(ge=0, le=100)
    transport_fee: float = Field(ge=0, le=100000, multiple_of=0.01, allow_inf_nan=False)


class Defaults(Empty):
    organization_id: str = Field(pattern=r'^(?:V-)?[0-9]{1,14}$')
    pricing: Pricing | None


class Draft(Empty):
    requested_vendor_id: int | None = Field(default=None, ge=1, le=2147483647, description="Bundle destination, separate from pricing. / Destino del paquete, independiente de los precios.")
    station_code: str = Field(min_length=1, max_length=30)
    vehicle_ids: list[str] = Field(min_length=1)
    include_dcd: bool = True
    kind: Literal['pm_amr', 'cmr'] = 'pm_amr'
    pricing_vendor_id: str | None = Field(default=None, pattern=r'^(?:V-)?[0-9]{1,14}$')


class Generator(Empty):
    repair_groups: list[Literal['PM', 'AMR', 'CMR']] = Field(min_length=1, max_length=2)
    station_codes: list[str] = Field(min_length=1, max_length=100)
    dcd_filter: Literal['only', 'exclude', 'any'] = 'any'
    van_count: int = Field(ge=1, le=100)
    minimum_value: int = Field(default=0, ge=0, le=100000000)
    pricing_vendor_id: str | None = Field(default=None, pattern=r'^(?:V-)?[0-9]{1,14}$')

    @model_validator(mode='after')
    def separate_cmr(self):
        if 'CMR' in self.repair_groups and (set(self.repair_groups) != {'CMR'} or self.pricing_vendor_id is not None):
            raise ValueError('CMR requires a separate offer without AMR prices. / CMR requiere una oferta separada sin precios AMR.')
        return self


class Profile(Generator):
    name: str = Field(min_length=1, max_length=120)


class Run(Empty):
    profile_id: int = Field(gt=0)


class VendorRow(BaseModel):
    id: str
    name: str
    pricing: Pricing | None
    effective_pricing: Pricing


class Vendors(BaseModel):
    rows: list[VendorRow]


class Bundle(BaseModel):
    ref: str
    revision: int = Field(gt=0)
    status: str
    total_price_cents: int = Field(ge=0)


class Bundles(BaseModel):
    rows: list[Bundle]


class SavedProfile(BaseModel):
    id: int = Field(gt=0)
    name: str
    pricing_vendor_id: int | None = None


class Profiles(BaseModel):
    rows: list[SavedProfile]


BASE = '/defect-bundle-offers/staff'
MODELS = {'list_bundle_pricing_vendors': Empty, 'set_vendor_bundle_pricing': Defaults, 'create_admin_bundle': Draft, 'list_bundle_profiles': Empty, 'save_bundle_profile': Profile, 'propose_bundle_offers': Generator, 'run_bundle_profile': Run}
OUTPUTS = {'list_bundle_pricing_vendors': Vendors, 'set_vendor_bundle_pricing': VendorRow, 'create_admin_bundle': Bundle, 'list_bundle_profiles': Profiles, 'save_bundle_profile': SavedProfile, 'propose_bundle_offers': Bundles, 'run_bundle_profile': Bundles}
ROUTES = {'list_bundle_pricing_vendors': ('GET', '/pricing-vendors'), 'set_vendor_bundle_pricing': ('PUT', '/pricing-vendors/{organization_id}'), 'create_admin_bundle': ('POST', ''), 'list_bundle_profiles': ('GET', '/profiles'), 'save_bundle_profile': ('POST', '/profiles'), 'propose_bundle_offers': ('POST', '/propose'), 'run_bundle_profile': ('POST', '/profiles/{profile_id}/run')}
WRITES = {name for name, (method, _) in ROUTES.items() if method != 'GET'}


def wire(name, request):
    values = request.model_dump(mode='json')
    method, suffix = ROUTES[name]
    excluded = set()
    for key in ('organization_id', 'profile_id'):
        if '{' + key + '}' in suffix:
            suffix = suffix.replace('{' + key + '}', str(values[key]))
            excluded.add(key)
    return method, BASE + suffix, {key: value for key, value in values.items() if key not in excluded}


def confirmed(name, request, value):
    result = OUTPUTS[name].model_validate(value)
    if isinstance(request, Defaults) and (int(result.id.removeprefix('V-')) != int(request.organization_id.removeprefix('V-')) or result.pricing != request.pricing):
        raise ValueError('Vendor defaults not confirmed')
    return value


def execute(client, name, arguments):
    import json

    from .errors import ApiError
    request = MODELS[name].model_validate(arguments)
    method, path, payload = wire(name, request)
    try:
        value = client.request(method, path, **({'json_body': payload, 'retry_auth': False} if name in WRITES else {}))
        json.dumps(value, allow_nan=False)
        return confirmed(name, request, value)
    except ApiError as exc:
        if name in WRITES and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError('The outcome is unknown. Read the bundle or defaults before another attempt. / El resultado no se conoce. Consulta el paquete o los valores antes de intentar de nuevo.', code='outcome_unknown') from exc
        raise
    except (ValueError, TypeError):
        raise ApiError('Invalid response. Read the bundle or defaults before another attempt. / Respuesta no válida. Consulta el paquete o los valores antes de intentar de nuevo.', code='outcome_unknown' if name in WRITES else 'invalid_response') from None


def command(args):
    import json

    from .legacy_reads import client_from_args
    return execute(client_from_args(args), args.vendor_pricing_tool, json.loads(args.request) if args.request else {})


COMMANDS = [
    {'command': 'bundle pricing-vendors', 'tool': 'list_bundle_pricing_vendors', 'grant': 'capacity.vendor_pricing.list.v1', 'description': 'Read bundle vendor defaults. / Consulta los valores de paquetes de talleres.', 'arguments': [], 'groups': [], 'defaults': {'vendor_pricing_tool': 'list_bundle_pricing_vendors', 'request': None}, 'scope': 'nova:read', 'handler': command, 'effect': 'remote_read'},
    {'command': 'bundle vendor-pricing', 'tool': 'set_vendor_bundle_pricing', 'grant': 'capacity.vendor_pricing.update.v1', 'description': 'Set or clear vendor defaults for future AMR bundles. Site admin only. / Establece o borra los valores del taller para paquetes AMR futuros. Solo para administradores del sitio.', 'arguments': [(['--request'], {'required': True, 'help': 'JSON request. / Solicitud JSON.'})], 'groups': [], 'defaults': {'vendor_pricing_tool': 'set_vendor_bundle_pricing'}, 'scope': 'nova:read nova:write', 'handler': command, 'effect': 'remote_write'},
    {'command': 'bundle create', 'tool': 'create_admin_bundle', 'grant': 'capacity.offers.create.v1', 'description': 'Create a bundle draft with one pricing vendor for all recipients. / Crea un borrador de paquete con un taller de referencia de precios para todos los destinatarios.', 'arguments': [(['--request'], {'required': True, 'help': 'JSON request. / Solicitud JSON.'})], 'groups': [], 'defaults': {'vendor_pricing_tool': 'create_admin_bundle'}, 'scope': 'nova:read nova:write', 'handler': command, 'effect': 'remote_write'},
    {'command': 'bundle profiles', 'tool': 'list_bundle_profiles', 'grant': 'capacity.profiles.list.v1', 'description': 'Read saved bundle generator profiles. / Consulta los perfiles guardados del generador de paquetes.', 'arguments': [], 'groups': [], 'defaults': {'vendor_pricing_tool': 'list_bundle_profiles', 'request': None}, 'scope': 'nova:read', 'handler': command, 'effect': 'remote_read'},
    {'command': 'bundle profile-save', 'tool': 'save_bundle_profile', 'grant': 'capacity.profiles.create.v1', 'description': 'Save bundle generator choices and a pricing vendor. / Guarda las opciones del generador de paquetes y un taller de referencia para precios.', 'arguments': [(['--request'], {'required': True, 'help': 'JSON request. / Solicitud JSON.'})], 'groups': [], 'defaults': {'vendor_pricing_tool': 'save_bundle_profile'}, 'scope': 'nova:read nova:write', 'handler': command, 'effect': 'remote_write'},
    {'command': 'bundle propose', 'tool': 'propose_bundle_offers', 'grant': 'capacity.offers.propose.v1', 'description': 'Propose bundles with a pricing vendor. / Propón paquetes con un taller de referencia para precios.', 'arguments': [(['--request'], {'required': True, 'help': 'JSON request. / Solicitud JSON.'})], 'groups': [], 'defaults': {'vendor_pricing_tool': 'propose_bundle_offers'}, 'scope': 'nova:read nova:write', 'handler': command, 'effect': 'remote_write'},
    {'command': 'bundle profile-run', 'tool': 'run_bundle_profile', 'grant': 'capacity.profiles.run.v1', 'description': 'Generate bundles from a saved profile and current vendor defaults. / Genera paquetes a partir de un perfil guardado y los valores actuales del taller.', 'arguments': [(['--request'], {'required': True, 'help': 'JSON request. / Solicitud JSON.'})], 'groups': [], 'defaults': {'vendor_pricing_tool': 'run_bundle_profile'}, 'scope': 'nova:read nova:write', 'handler': command, 'effect': 'remote_write'},
]
