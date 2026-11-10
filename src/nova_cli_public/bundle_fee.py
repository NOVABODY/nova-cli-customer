"""Site-admin bundle fee waivers with explicit consent and no write replay."""
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from nova_cli_public.errors import ApiError

READ, WRITE = 'get_admin_bundle', 'waive_bundle_fee'
UNKNOWN = 'The outcome is unknown. Read the bundle before trying again. / El resultado no se conoce. Consulta el paquete antes de intentar de nuevo.'


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ref: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,39}$')


class Waiver(Query):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    revision: int | None = Field(default=None, gt=0)


class Result(BaseModel):
    model_config = ConfigDict(strict=True)
    ref: str
    revision: int = Field(ge=1)
    fee_waived: bool


MODELS, OUTPUTS, WRITES = {READ: Query, WRITE: Waiver}, {READ: Result, WRITE: Result}, {WRITE}


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    path = f'/defect-bundle-offers/staff/{query.ref}'
    try:
        value = client.request('GET', path) if name == READ else client.request('POST', path + '/waive-fee',
            json_body=query.model_dump(exclude={'ref'}, exclude_none=True), retry_auth=False)
    except ApiError as exc:
        if name == WRITE and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    try:
        result = Result.model_validate(value)
        json.dumps(value, allow_nan=False)
        if result.ref != query.ref or (name == WRITE and not result.fee_waived):
            raise ValueError('Waiver not confirmed')
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name == WRITE else ApiError(
            'Invalid bundle response. / Respuesta del paquete no válida.') from None
    return value


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    return execute(client_from_args(args), args.bundle_fee_tool,
        {key: getattr(args, key) for key in MODELS[args.bundle_fee_tool].model_fields})


COMMANDS = [
    {'command': 'bundle-fee get', 'tool': READ, 'grant': 'capacity.offers.staff.get.v1',
     'description': 'Read an admin bundle. / Consulta un paquete de administración.',
     'arguments': [(['ref'], {})], 'groups': [], 'handler': command, 'defaults': {'bundle_fee_tool': READ}},
    {'command': 'bundle-fee waive', 'tool': WRITE, 'grant': 'capacity.fee.waive.v1',
     'description': 'Waive the whole PM/AMR bundle fee before or after award. Site admin only. This cannot be undone. / Exime la tarifa completa del paquete PM/AMR antes o después de adjudicarlo. Solo para administradores del sitio. No se puede deshacer.',
     'arguments': [(['ref'], {}), (['--reason'], {'required': True}), (['--revision'], {'type': 'int'})],
     'groups': [], 'handler': command, 'defaults': {'bundle_fee_tool': WRITE},
     'scope': 'nova:read nova:write', 'effect': 'remote_write'},
]
