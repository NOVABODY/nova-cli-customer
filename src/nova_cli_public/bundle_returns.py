"""Record a purchased bundle van's return through the dedicated custody route."""
import json

from pydantic import BaseModel, ConfigDict, Field

from nova_cli_public.errors import ApiError, UsageError

NAME = 'record_bundle_return'
UNKNOWN = 'The return outcome is unknown. Check the transport task. / El resultado se desconoce. Consulta la tarea de transporte.'


class Return(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    task_id: int = Field(ge=1, le=2147483647)
    mileage: int = Field(ge=0, le=2000000)
    photos: list[dict] = Field(min_length=1, max_length=12)
    confirmed_mileage_floor: int | None = Field(default=None, ge=0, le=2000000)


def execute(client, arguments):
    request = Return.model_validate(arguments)
    try:
        value = client.request('POST', f'/bundle-offers/transport/{request.task_id}/check-in',
            json_body=request.model_dump(exclude={'task_id'}, exclude_none=True), retry_auth=False)
    except ApiError as exc:
        if exc.status is None or exc.status >= 500 or 300 <= exc.status < 400:
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    if (not isinstance(value, dict) or value.get('status') != 'checked_in'
            or type(value.get('task_id')) is not int or value['task_id'] != request.task_id
            or type(value.get('mileage')) is not int or value['mileage'] != request.mileage):
        raise ApiError(UNKNOWN, code='outcome_unknown')
    return value


def command(args):
    from nova_cli_public.legacy_writes import client_from_args
    try:
        return execute(client_from_args(args), {'task_id': int(args.task_id), 'mileage': args.mileage,
            'photos': json.loads(args.photos), 'confirmed_mileage_floor': args.confirmed_mileage_floor})
    except (ValueError, TypeError) as exc:
        raise UsageError('Check return evidence. / Comprueba las pruebas de devolución.') from exc


COMMANDS = [{'command': 'bundle-return record', 'tool': NAME, 'grant': 'capacity.transport.check_in.v1',
    'scope': 'nova:read nova:write', 'effect': 'remote_write',
    'description': 'Record a bundle van return. / Registra la devolución de una van de paquete.',
    'arguments': [(['task_id'], {'type': 'int'}), (['--mileage'], {'type': 'int', 'required': True}),
        (['--photos'], {'required': True}), (['--confirmed-mileage-floor'], {'type': 'int'})],
    'groups': [], 'defaults': {}, 'handler': command}]
