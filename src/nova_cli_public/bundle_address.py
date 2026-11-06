"""Typed, all-bundle destination edits before scheduling."""
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from nova_cli_public.errors import ApiError

READ, WRITE = 'get_bundle_dropoff_address', 'update_bundle_dropoff_address'
UNKNOWN = 'The outcome is unknown. Read the bundle address before trying again. / El resultado no se conoce. Consulta la dirección del paquete antes de intentar de nuevo.'


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ref: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,79}$')


class Address(Query):
    delivery_address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    save_profile: bool = False


class Result(BaseModel):
    model_config = ConfigDict(strict=True)
    delivery_address: str | None
    van_count: int = Field(ge=1)


class View(Result):
    can_edit: bool
    can_save_profile: bool


MODELS, OUTPUTS, WRITES = {READ: Query, WRITE: Address}, {READ: View, WRITE: Result}, {WRITE}


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    path = f'/bundle-offers/{query.ref}/dropoff-address'
    try:
        value = client.request('GET', path) if name == READ else client.request('POST', path,
            json_body=query.model_dump(exclude={'ref'}), retry_auth=False)
    except ApiError as exc:
        if name == WRITE and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    try:
        result = OUTPUTS[name].model_validate(value)
        json.dumps(value, allow_nan=False)
        if name == WRITE and result.delivery_address != query.delivery_address:
            raise ValueError('Address not confirmed')
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name == WRITE else ApiError(
            'Invalid bundle address response. / Respuesta de dirección del paquete no válida.') from None
    return value


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    return execute(client_from_args(args), args.bundle_address_tool,
        {key: getattr(args, key) for key in MODELS[args.bundle_address_tool].model_fields})


COMMANDS = [
    {'command': 'bundle-address get', 'tool': READ, 'grant': 'capacity.dropoff_address.get.v1',
     'description': 'Read the bundle drop-off address. / Consulta la dirección de entrega del paquete.',
     'arguments': [(['ref'], {})], 'groups': [], 'handler': command, 'defaults': {'bundle_address_tool': READ}},
    {'command': 'bundle-address set', 'tool': WRITE, 'grant': 'capacity.dropoff_address.update.v1',
     'description': 'Change the address for all bundle vans before scheduling. Save the shop profile only with explicit choice and profile access. / Cambia la dirección de todas las vans del paquete antes de programar. Guarda el perfil del taller solo con una selección explícita y acceso al perfil.',
     'arguments': [(['ref'], {}), (['--delivery-address'], {'required': True}), (['--save-profile'], {'action': 'store_true'})],
     'groups': [], 'handler': command, 'defaults': {'bundle_address_tool': WRITE},
     'scope': 'nova:read nova:write', 'effect': 'remote_write'},
]
