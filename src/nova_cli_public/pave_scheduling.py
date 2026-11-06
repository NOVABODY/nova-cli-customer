"""Scan-team requests and scheduling use native role and fleet/workshop scope."""
import json
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nova_cli_public.errors import ApiError


def positive_reference(value):
    if not 1 <= int(value.rsplit('-', 1)[-1]) <= 2147483647:
        raise ValueError('Use a positive record ID. / Usa un ID de registro positivo.')
    return value


Vehicle = Annotated[str, Field(pattern=r'^(?:VAN-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
Workshop = Annotated[str, Field(pattern=r'^(?:VW-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
Dsp = Annotated[str, Field(pattern=r'^(?:DSP-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
Positive = Annotated[int, Field(ge=1, le=2147483647)]
Inspection = Literal['fleet_improvement_fund', 'redeployment_retirement', 'rental_baseline', 'rental_return']
UNKNOWN = 'The outcome is unknown. Read the scan schedule before trying again. / El resultado no se conoce. Consulta el programa de escaneos antes de intentar de nuevo.'


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class RequestScan(Closed):
    vehicle_id: Vehicle
    inspection_type: Inspection = 'fleet_improvement_fund'


class CancelRequest(Closed):
    vehicle_id: Vehicle
    booking_id: Positive


class Upcoming(Closed):
    dsp_id: Dsp
    window_hours: int = Field(default=24, ge=1, le=1440)


class Change(Closed):
    dsp_id: Dsp
    booking_id: Positive
    preferred_at: AwareDatetime = Field(strict=False)
    reason: str | None = Field(default=None, max_length=500)


class Calendar(Closed):
    start: date | None = Field(default=None, strict=False)
    end: date | None = Field(default=None, strict=False)

    @model_validator(mode='after')
    def ordered(self):
        if self.start and self.end and self.end < self.start:
            raise ValueError('Use an end date after the start. / Usa una fecha final posterior a la inicial.')
        return self


class ShopCalendar(Calendar):
    workshop_id: Workshop


class Booking(Closed):
    booking_id: Positive


class ShopBooking(Booking):
    workshop_id: Workshop


class Schedule(Booking):
    scheduled_at: AwareDatetime = Field(strict=False)


class ShopSchedule(Schedule):
    workshop_id: Workshop


# Command, tool, operation, model, method, path. Canonical routes only.
SPECS = [
    ('request', 'request_vehicle_pave_scan', 'vehicles.pave_scan_requests.create.v1', RequestScan, 'POST', '/vehicles/{vehicle_id}/pave-scan-requests'),
    ('cancel-request', 'cancel_vehicle_pave_scan_request', 'vehicles.pave_scan_requests.cancel.v1', CancelRequest, 'POST', '/vehicles/{vehicle_id}/pave-scan-requests/{booking_id}/cancel'),
    ('upcoming', 'list_dsp_pave_scans', 'pave_scans.dsp.list.v1', Upcoming, 'GET', '/dashboards/dsp/{dsp_id}/upcoming-pave-scans'),
    ('request-change', 'request_pave_scan_schedule_change', 'pave_scans.dsp.change.v1', Change, 'POST', '/dashboards/dsp/{dsp_id}/pave-scans/{booking_id}/change-request'),
    ('platform-list', 'list_platform_pave_scans', 'pave_scans.platform.list.v1', Calendar, 'GET', '/dashboards/platform-pave-scans'),
    ('workshop-list', 'list_workshop_pave_scans', 'pave_scans.workshop.list.v1', ShopCalendar, 'GET', '/dashboards/vendor-workshops/{workshop_id}/pave-scans'),
    ('platform-schedule', 'set_platform_pave_scan_schedule', 'pave_scans.platform.schedule.v1', Schedule, 'POST', '/dashboards/platform-pave-scans/{booking_id}/schedule'),
    ('workshop-schedule', 'set_workshop_pave_scan_schedule', 'pave_scans.workshop.schedule.v1', ShopSchedule, 'POST', '/dashboards/vendor-workshops/{workshop_id}/pave-scans/{booking_id}/schedule'),
    ('platform-cancel', 'cancel_platform_pave_scan', 'pave_scans.platform.cancel.v1', Booking, 'POST', '/dashboards/platform-pave-scans/{booking_id}/cancel'),
    ('workshop-cancel', 'cancel_workshop_pave_scan', 'pave_scans.workshop.cancel.v1', ShopBooking, 'POST', '/dashboards/vendor-workshops/{workshop_id}/pave-scans/{booking_id}/cancel'),
]
BY_TOOL = {row[1]: row for row in SPECS}
MODELS = {row[1]: row[3] for row in SPECS}
WRITES = {row[1] for row in SPECS if row[4] != 'GET'}


def prepare(name, arguments):
    spec = BY_TOOL[name]
    values = spec[3].model_validate(arguments).model_dump(mode='json', exclude_none=True, exclude_unset=True)
    path = spec[5].format(**values)
    fields = {key: value for key, value in values.items() if '{' + key + '}' not in spec[5]}
    return spec[4], path, fields


def validate_result(name, value, arguments=None):
    json.dumps(value, allow_nan=False)
    if name == 'list_dsp_pave_scans':
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError()
        return {'items': value}
    if name == 'cancel_vehicle_pave_scan_request':
        if value is not None and not isinstance(value, dict):
            raise ValueError()
        return {'scan_booking': value}
    if not isinstance(value, dict):
        raise TypeError()
    if name in WRITES and (type(value.get('id')) is not int or value['id'] <= 0):
        raise ValueError()
    if name == 'request_vehicle_pave_scan' and value.get('state') not in ('requested', 'scheduled', 'unavailable'):
        raise ValueError()
    if name in WRITES and arguments and 'booking_id' in arguments and value['id'] != arguments['booking_id']:
        raise ValueError()
    field = ('scheduled_at' if name.startswith('set_') else 'cancelled_at' if name.startswith('cancel_')
        else 'change_requested_for' if name == 'request_pave_scan_schedule_change' else None)
    if field and not (field == 'scheduled_at' and value.get('cancelled_at')):
        at = datetime.fromisoformat(value[field])
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError()
        requested = (arguments or {}).get('scheduled_at' if field == 'scheduled_at' else 'preferred_at')
        if requested and field != 'cancelled_at' and at != datetime.fromisoformat(requested):
            raise ValueError()
    if name in {'list_platform_pave_scans', 'list_workshop_pave_scans'} and not isinstance(value.get('requests'), list):
        raise ValueError()
    return value


def execute(client, name, arguments):
    method, path, fields = prepare(name, arguments)
    try:
        value = client.request(method, path, **({'query': fields} if method == 'GET' else {'json_body': fields, 'retry_auth': False}))
    except ApiError as exc:
        if name in WRITES and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    try:
        if len(json.dumps(value, allow_nan=False).encode()) > 2 * 1024 * 1024:
            raise ValueError()
        return validate_result(name, value, {**arguments, **fields})
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name in WRITES else ApiError('Invalid scan schedule. / Programa de escaneos no válido.') from None


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.pave_schedule_tool
    values = {key: getattr(args, key) for key in MODELS[name].model_fields if getattr(args, key, None) is not None}
    return execute(client_from_args(args), name, values)


COMMANDS = []
for action, tool, grant, model, method, _path in SPECS:
    arguments = []
    for key, field in model.model_fields.items():
        options = {}
        flags = [key] if key.endswith('_id') else ['--' + key.replace('_', '-')]
        if key == 'booking_id' or key == 'window_hours':
            options['type'] = 'int'
        if not key.endswith('_id') and field.is_required():
            options['required'] = True
        arguments.append((flags, options))
    COMMANDS.append({'command': 'pave-scan ' + action, 'tool': tool, 'grant': grant,
        'description': 'Read or change the PAVE scan schedule within your role. A request has no date until staff or the shop schedules it. / Consulta o cambia el programa de escaneos PAVE dentro de tu rol. Una solicitud no tiene fecha hasta que el personal o el taller la programe. ' + UNKNOWN,
        'arguments': arguments, 'groups': [], 'handler': command, 'defaults': {'pave_schedule_tool': tool},
        'scope': 'nova:read nova:write' if tool in WRITES else 'nova:read',
        'effect': 'remote_write' if tool in WRITES else 'remote_read'})
