"""Explicit overnight inspection settings and decisions; never enroll other users."""
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError

ROLES = Literal['owners', 'dispatchers', 'owners_and_dispatchers']
STATUS = Literal['not_requested', 'pending', 'confirmed', 'declined', 'expired']
UNKNOWN = 'The change outcome is unknown. Read the record before trying again. / El resultado no se conoce. Consulta el registro antes de intentar de nuevo.'


def aware_datetime(value):
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError('Use a date and time with a UTC offset. / Usa una fecha y hora con desfase UTC.')
    return value


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dsp_id: Annotated[str, Field(pattern=r'^(?:DSP-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]


class Update(Settings):
    enabled: bool | None = None
    recipient_roles: ROLES | None = None

    @model_validator(mode='after')
    def explicit_change(self):
        if self.enabled is None and self.recipient_roles is None:
            raise ValueError('Select a setting to change. / Selecciona un ajuste para cambiar.')
        return self


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schedule_id: Annotated[str, Field(pattern=r'^(?:DVIC-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]


class Respond(Confirmation):
    expected_confirmation_id: Annotated[int, Field(ge=1, le=2147483647)]
    response: Literal['Y', 'N']
    expected_scheduled_at: Annotated[str, AfterValidator(aware_datetime)]


class SettingsResult(BaseModel):
    model_config = ConfigDict(strict=True)
    enabled: bool
    recipient_roles: ROLES


class Result(BaseModel):
    model_config = ConfigDict(strict=True)
    schedule_id: int
    confirmation_id: Annotated[int, Field(ge=1)] | None
    status: STATUS
    responded_at: Annotated[str, AfterValidator(aware_datetime)] | None
    responded_by_id: int | None


MODELS = {'get_inspection_confirmation_settings': Settings,
    'update_inspection_confirmation_settings': Update,
    'get_inspection_confirmation': Confirmation, 'respond_inspection_confirmation': Respond}
OUTPUTS = {'get_inspection_confirmation_settings': SettingsResult,
    'update_inspection_confirmation_settings': SettingsResult,
    'get_inspection_confirmation': Result, 'respond_inspection_confirmation': Result}
WRITES = {'update_inspection_confirmation_settings', 'respond_inspection_confirmation'}


def run(args):
    name = args.confirmation_tool
    query = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields
        if getattr(args, key, None) is not None})
    settings = isinstance(query, Settings)
    path = '/inspection-confirmations/' + ('settings/' + query.dsp_id if settings else query.schedule_id)
    body = query.model_dump(exclude={'dsp_id', 'schedule_id'}, exclude_none=True)
    method = 'PATCH' if isinstance(query, Update) else 'POST' if isinstance(query, Respond) else 'GET'
    value = legacy_reads.client_from_args(args).request(method, path + ('/respond' if isinstance(query, Respond) else ''),
        **({'json_body': body} if name in WRITES else {}))
    try:
        result = OUTPUTS[name].model_validate(value)
        json.dumps(value, allow_nan=False)
        if not settings and result.schedule_id != int(query.schedule_id.rsplit('-', 1)[-1]):
            raise ValueError('Wrong appointment')
        if isinstance(query, Respond) and (result.confirmation_id != query.expected_confirmation_id
                or result.status != ('confirmed' if query.response == 'Y' else 'declined')):
            raise ValueError('Decision was not recorded')
        if isinstance(query, Update) and any(getattr(result, key) != val for key, val in body.items()):
            raise ValueError('Settings were not recorded')
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name in WRITES else ApiError(
            'Invalid inspection confirmation. / Confirmación de inspección no válida.') from None
    return value


COMMANDS = []
for action, name, operation, arguments in [
    ('settings', 'get_inspection_confirmation_settings', 'settings.get', [(['dsp_id'], {})]),
    ('set-settings', 'update_inspection_confirmation_settings', 'settings.update', [(['dsp_id'], {}),
        (['--enabled'], {'action': 'BooleanOptionalAction', 'default': None}),
        (['--recipient-roles'], {'choices': ['owners', 'dispatchers', 'owners_and_dispatchers'], 'default': None})]),
    ('get', 'get_inspection_confirmation', 'get', [(['schedule_id'], {})]),
    ('respond', 'respond_inspection_confirmation', 'respond', [(['schedule_id'], {}),
        (['--response'], {'required': True, 'choices': ['Y', 'N']}),
        (['--expected-scheduled-at'], {'required': True}),
        (['--expected-confirmation-id'], {'required': True, 'type': 'int'})]),
]:
    COMMANDS.append({'command': 'inspection-confirmation ' + action, 'tool': name,
        'grant': 'inspection_confirmations.' + operation + '.v1',
        'description': {
            'settings': 'Read inspection confirmation settings. / Consulta los ajustes de confirmación de inspecciones.',
            'set-settings': 'Change only selected inspection confirmation settings. / Cambia solo los ajustes de confirmación seleccionados.',
            'get': 'Read an inspection confirmation. / Consulta una confirmación de inspección.',
            'respond': 'Confirm or decline one inspection. / Confirma o rechaza una inspección.',
        }[action], 'arguments': arguments, 'groups': [], 'handler': run,
        'defaults': {'confirmation_tool': name},
        **({'scope': 'nova:read nova:write', 'effect': 'remote_write'} if name in WRITES else {})})
