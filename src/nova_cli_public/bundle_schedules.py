"""Version-bound DSP decisions on shop pickup and return windows."""
import json
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from nova_cli_public.errors import ApiError

READ = 'list_bundle_schedules'
WRITE = 'decide_bundle_schedule'
UNKNOWN = 'The outcome is unknown. Read the schedule before trying again. / El resultado no se conoce. Consulta el horario antes de intentar de nuevo.'


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Decision(Query):
    ref: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,79}$')
    unit: int = Field(ge=1)
    version: str = Field(min_length=1, max_length=40)
    decision: Literal['approved', 'declined']


class Schedule(BaseModel):
    version: str
    status: Literal['pending', 'approved', 'declined']
    pickup_start: AwareDatetime
    pickup_end: AwareDatetime
    return_start: AwareDatetime
    return_end: AwareDatetime
    timezone: str


class Row(BaseModel):
    ref: str
    unit: int
    vehicle: str
    schedule: Schedule


class Listing(BaseModel):
    rows: list[Row]


class Result(BaseModel):
    schedule: Schedule


MODELS = {READ: Query, WRITE: Decision}
OUTPUTS = {READ: Listing, WRITE: Result}
WRITES = {WRITE}


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    try:
        value = client.request('GET', '/bundle-offers/schedules') if name == READ else client.request(
            'POST', f'/bundle-offers/{query.ref}/vans/{query.unit}/schedule-decision',
            json_body={'version': query.version, 'decision': query.decision})
    except ApiError as exc:
        if name == WRITE and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    try:
        result = OUTPUTS[name].model_validate(value)
        json.dumps(value, allow_nan=False)
        if name == WRITE and (result.schedule.version != query.version or result.schedule.status != query.decision):
            raise ValueError('Decision not confirmed')
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name == WRITE else ApiError(
            'Invalid schedule response. / Respuesta de horario no válida.') from None
    return value


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.bundle_schedule_tool
    arguments = {key: getattr(args, key) for key in MODELS[name].model_fields}
    return execute(client_from_args(args), name, arguments)


COMMANDS = [
    {'command': 'bundle-schedules list', 'tool': READ, 'grant': 'capacity.schedules.list.v1',
     'description': 'List pickup and return schedules for your DSP. / Consulta los horarios de recogida y devolución de tu DSP.',
     'arguments': [], 'groups': [], 'handler': command, 'defaults': {'bundle_schedule_tool': READ}},
    {'command': 'bundle-schedules decide', 'tool': WRITE, 'grant': 'capacity.schedules.decide.v1',
     'description': 'Approve or decline the exact schedule version. / Aprueba o rechaza la versión exacta del horario.',
     'arguments': [(['ref'], {}), (['unit'], {'type': 'int'}), (['--version'], {'required': True}),
                   (['--decision'], {'choices': ['approved', 'declined'], 'required': True})],
     'groups': [], 'handler': command, 'defaults': {'bundle_schedule_tool': WRITE},
     'scope': 'nova:read nova:write', 'effect': 'remote_write'},
]
