"""Read or change the DSP's one shared bundle setting."""
import json
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError

UNKNOWN = 'The change outcome is unknown. Read the setting before trying again. / El resultado no se conoce. Consulta el ajuste antes de intentar de nuevo.'
READ = 'get_bundle_sharing'
WRITE = 'set_bundle_sharing'


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dsp_id: Annotated[str, Field(pattern=r'^(?:DSP-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]


class Change(Query):
    enabled: bool


class Result(BaseModel):
    model_config = ConfigDict(strict=True)
    enabled: bool


MODELS = {READ: Query, WRITE: Change}
OUTPUTS = {READ: Result, WRITE: Result}
WRITES = {WRITE}


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    try:
        value = client.request('PATCH' if name == WRITE else 'GET',
            f'/dsp-settings/{query.dsp_id}/defect-data-sharing',
            **({'json_body': {'enabled': query.enabled}} if name == WRITE else {}))
    except ApiError as exc:
        if name == WRITE and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    try:
        result = Result.model_validate(value)
        json.dumps(value, allow_nan=False)
        if name == WRITE and result.enabled != query.enabled:
            raise ValueError('Setting was not recorded')
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name == WRITE else ApiError(
            'Invalid bundle setting. / Ajuste de paquetes no válido.') from None
    return value


def run(args):
    from nova_cli_public.legacy_reads import client_from_args

    name = args.bundle_sharing_tool
    arguments = {key: getattr(args, key) for key in MODELS[name].model_fields}
    MODELS[name].model_validate(arguments)
    return execute(client_from_args(args), name, arguments)


COMMANDS = [
    {'command': 'bundle-sharing ' + action, 'tool': name,
     'grant': 'dsp.bundle_sharing.' + operation + '.v1',
     'description': description, 'arguments': [(['dsp_id'], {})] + (
         [(['--enabled'], {'action': 'BooleanOptionalAction', 'required': True})] if name == WRITE else []),
     'groups': [], 'handler': run, 'defaults': {'bundle_sharing_tool': name},
     **({'scope': 'nova:read nova:write', 'effect': 'remote_write'} if name == WRITE else {})}
    for action, name, operation, description in [
        ('get', READ, 'get', 'Read bundle sharing. / Consulta el ajuste de paquetes.'),
        ('set', WRITE, 'update', 'Set bundle sharing. Turning it off withdraws open offers. / Cambia el ajuste de paquetes. Si lo desactivas, se retiran las ofertas abiertas.'),
    ]
]
