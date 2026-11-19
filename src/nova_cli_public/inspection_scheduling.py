"""Station-scoped inspection scheduling; the API owns role and station authority."""
import json
from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[int, Field(ge=1, le=2147483647)]
Codes = Annotated[list[Annotated[str, Field(pattern=r'^[A-Z0-9][A-Z0-9_-]{0,19}$')]], Field(min_length=1, max_length=1000)]
UNKNOWN = 'The outcome is unknown. Read the schedule before trying again. / El resultado no se conoce. Consulta el programa antes de intentar de nuevo.'


def aware(value):
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError('Include a UTC offset. / Incluye un desfase UTC.')
    return value


def local_clock(value):
    if time.fromisoformat(value).tzinfo is not None:
        raise ValueError('Use local time without an offset. / Usa la hora local sin desfase.')
    return value


class Scope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workshop_id: Positive | None = None


class Stations(Scope):
    dsp_id: Positive


class Visits(Scope):
    include_past: bool = False


class Recurrences(Scope):
    include_inactive: bool = False


class Create(Stations):
    station_codes: Codes
    scheduled_at: Annotated[str, AfterValidator(aware)]
    notes: str | None = Field(default=None, max_length=500)


class Cancel(Scope):
    schedule_id: Positive
    reason: str | None = Field(default=None, max_length=200)


class CreateRecurrence(Stations):
    station_codes: Codes
    weekday: int = Field(ge=0, le=6)
    cadence: Literal['weekly', 'biweekly', 'monthly'] = 'weekly'
    anchor_date: date = Field(strict=False)
    local_time: Annotated[str, AfterValidator(local_clock)]
    notes: str | None = Field(default=None, max_length=500)


class UpdateRecurrence(Scope):
    recurrence_id: Positive
    station_codes: Codes | None = None
    is_active: bool | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    cadence: Literal['weekly', 'biweekly', 'monthly'] | None = None
    anchor_date: date | None = Field(default=None, strict=False)
    local_time: Annotated[str, AfterValidator(local_clock)] | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def explicit_change(self):
        if not self.model_dump(exclude={'workshop_id', 'recurrence_id'}, exclude_none=True):
            raise ValueError('Select a change. / Selecciona un cambio.')
        return self


class Station(BaseModel):
    model_config = ConfigDict(strict=True)
    code: str
    name: str


class Visit(BaseModel):
    model_config = ConfigDict(strict=True)
    id: Positive
    dsp_id: Positive
    vendor_workshop_id: Positive | None
    station_codes: Codes | None
    scheduled_at: Annotated[str, AfterValidator(aware)]
    cancelled_at: Annotated[str, AfterValidator(aware)] | None = None


class Recurrence(BaseModel):
    model_config = ConfigDict(strict=True)
    id: Positive
    dsp_id: Positive
    vendor_workshop_id: Positive | None
    station_codes: Codes | None
    weekday: int
    cadence: str
    anchor_date: str
    local_time: str
    is_active: bool


class StationList(BaseModel):
    items: list[Station]


class VisitList(BaseModel):
    items: list[Visit]


class RecurrenceList(BaseModel):
    items: list[Recurrence]


# Action, tool, operation suffix, input, output, method.
SPECS = [
    ('stations', 'list_inspection_stations', 'stations.list', Stations, StationList, 'GET'),
    ('list', 'list_inspection_schedules', 'list', Visits, VisitList, 'GET'),
    ('create', 'create_inspection_schedule', 'create', Create, Visit, 'POST'),
    ('cancel', 'cancel_inspection_schedule', 'cancel', Cancel, Visit, 'POST'),
    ('recurrences', 'list_inspection_recurrences', 'recurrences.list', Recurrences, RecurrenceList, 'GET'),
    ('create-recurrence', 'create_inspection_recurrence', 'recurrences.create', CreateRecurrence, Recurrence, 'POST'),
    ('update-recurrence', 'update_inspection_recurrence', 'recurrences.update', UpdateRecurrence, Recurrence, 'PATCH'),
]
MODELS = {spec[1]: spec[3] for spec in SPECS}
OUTPUTS = {spec[1]: spec[4] for spec in SPECS}
WRITES = {spec[1] for spec in SPECS if spec[5] != 'GET'}


def prepare(name, arguments):
    fields = MODELS[name].model_validate(arguments).model_dump(mode='json', exclude_none=True)
    workshop = fields.pop('workshop_id', None)
    recurrence = 'recurrence' in name
    path = ('/dashboards/platform-inspections' + ('/recurrences' if recurrence else '') if workshop is None else
            f'/dashboards/vendor-home/{workshop}/' + ('dvic-schedule-recurrences' if recurrence else 'dvic-schedules'))
    if name == 'list_inspection_stations':
        path = '/dashboards/inspection-stations'
        if workshop is not None:
            fields['vendor_workshop_id'] = workshop
    elif name == 'cancel_inspection_schedule':
        path += f"/{fields.pop('schedule_id')}/cancel"
        if workshop is None:
            fields = {}  # Platform cancellation has no reason field.
    elif name == 'update_inspection_recurrence':
        path += f"/{fields.pop('recurrence_id')}"
    method = next(spec[5] for spec in SPECS if spec[1] == name)
    return method, path, fields


def validate_result(name, value, arguments):
    json.dumps(value, allow_nan=False)
    wrapped = {'items': value} if name not in WRITES else value
    result = OUTPUTS[name].model_validate(wrapped)
    if name not in WRITES:
        return wrapped
    expected_id = arguments.get('schedule_id', arguments.get('recurrence_id'))
    if expected_id is not None and result.id != expected_id:
        raise ValueError('Wrong schedule')
    if result.vendor_workshop_id != arguments.get('workshop_id'):
        raise ValueError('Wrong workshop')
    if 'dsp_id' in arguments and result.dsp_id != arguments['dsp_id']:
        raise ValueError('Wrong DSP')
    if arguments.get('station_codes') is not None and set(result.station_codes or []) != set(arguments['station_codes']):
        raise ValueError('Wrong stations')
    if name == 'cancel_inspection_schedule' and not result.cancelled_at:
        raise ValueError('Cancellation was not recorded')
    if 'scheduled_at' in arguments and datetime.fromisoformat(result.scheduled_at) != datetime.fromisoformat(arguments['scheduled_at']):
        raise ValueError('Wrong appointment time')
    for field in ('weekday', 'cadence', 'is_active', 'anchor_date'):
        if arguments.get(field) is not None and str(getattr(result, field)) != str(arguments[field]):
            raise ValueError('Recurring schedule was not recorded')
    if arguments.get('local_time') is not None and time.fromisoformat(result.local_time) != time.fromisoformat(arguments['local_time']):
        raise ValueError('Wrong local time')
    return value


def execute(client, name, arguments):
    from .errors import ApiError
    method, path, fields = prepare(name, arguments)
    try:
        value = client.request(method, path, **({'query': fields} if method == 'GET' else
                                               {'json_body': fields, 'retry_auth': False}))
    except ApiError as error:
        if name in WRITES and (error.status is None or error.status >= 500 or 300 <= error.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from error
        raise
    try:
        if len(json.dumps(value, allow_nan=False).encode()) > 2 * 1024 * 1024:
            raise ValueError()
        return validate_result(name, value, {**arguments, **fields})
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name in WRITES else ApiError(
            'Invalid inspection schedule. / Programa de inspecciones no válido.') from None


def command(args):
    from .legacy_reads import client_from_args
    name = args.inspection_schedule_tool
    values = {key: getattr(args, key) for key in MODELS[name].model_fields if getattr(args, key, None) is not None}
    return execute(client_from_args(args), name, values)


COMMANDS = []
for action, tool, operation, model, output, method in SPECS:
    arguments = []
    for key, field in model.model_fields.items():
        flags = ['--' + key.replace('_', '-')]
        options = {'required': True} if field.is_required() else {}
        if key.endswith('_id') or key == 'weekday':
            options['type'] = 'int'
        elif key == 'station_codes':
            flags = ['--station-code']
            options.update(action='append', dest='station_codes')
        elif key in ('is_active', 'include_past', 'include_inactive'):
            options.update(action='BooleanOptionalAction', default=None)
        arguments.append((flags, options))
    COMMANDS.append({'command': 'inspection-schedule ' + action, 'tool': tool,
        'grant': 'inspection_schedules.' + operation + '.v1',
        'description': 'Read or change inspection visits at selected DSP stations. Omit workshop_id for platform inspections. / Consulta o cambia visitas de inspección en estaciones seleccionadas del DSP. Omite workshop_id para inspecciones de plataforma. ' + UNKNOWN,
        'arguments': arguments, 'groups': [], 'handler': command,
        'defaults': {'inspection_schedule_tool': tool},
        'scope': 'nova:read nova:write' if tool in WRITES else 'nova:read',
        'effect': 'remote_write' if tool in WRITES else 'remote_read'})
