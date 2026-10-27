"""Native repair-request reads preserve API projections and rental filters."""
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError

Positive = Annotated[int, Field(ge=1, le=2147483647)]
Reference = Annotated[str, Field(pattern=r'^(?:RR-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
Dsp = Positive | Annotated[str, Field(pattern=r'^(?:DSP-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
STATUSES = ('open', 'accepted', 'cancelled', 'fulfilled', 'stale')
STATES = ('awaiting_review', 'rejected', 'routing_blocked')


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal[STATUSES] | None = None
    dsp_id: Dsp | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    awaiting_rental_routing_confirmation: bool | None = None
    rental_queue: bool | None = None
    rental_approval_state: Literal[STATES] | None = None


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    rr_id: Reference


MODELS = {'list_repair_requests': Filters, 'get_repair_request': Request,
          'list_repair_request_external_vendor_options': Request}


def prepare(name, arguments):
    values = MODELS[name].model_validate(arguments).model_dump(exclude_none=True)
    if name == 'list_repair_requests':
        return '/repair-requests', values
    path = '/repair-requests/' + values['rr_id']
    return path + ('/external-vendor-options' if name.endswith('_options') else ''), {}


def validate(name, value):
    if not isinstance(value, dict) or (name == 'list_repair_requests' and (
            not isinstance(value.get('items'), list) or any(not isinstance(row, dict) for row in value['items'])
            or type(value.get('total')) is not int or value['total'] < 0)):
        raise ApiError('Invalid repair request response. / Respuesta de solicitud de reparación no válida.')
    if name.endswith('_options') and (any(not isinstance(value.get(key), list) for key in ('items', 'related_defects', 'contacts'))
            or 'default_contact_user_id' not in value or 'unavailable_reason' not in value):
        raise ApiError('Invalid repair options response. / Respuesta de opciones de reparación no válida.')
    return value


def run(args):
    name = args.repair_tool
    path, query = prepare(name, {key: getattr(args, key) for key in MODELS[name].model_fields if hasattr(args, key)})
    return validate(name, legacy_reads.client_from_args(args).request('GET', path, query=query))


COMMANDS = []
for action, tool, grant in [
    ('list', 'list_repair_requests', 'list'), ('get', 'get_repair_request', 'get'),
    ('external-vendor-options', 'list_repair_request_external_vendor_options', 'external_vendor_options.list'),
]:
    arguments = []
    for name, field in MODELS[tool].model_fields.items():
        options = {} if field.is_required() else {'default': field.default}
        if name in ('limit', 'offset'):
            options['type'] = 'int'
        if name in ('awaiting_rental_routing_confirmation', 'rental_queue'):
            options['action'] = 'BooleanOptionalAction'
        arguments.append(([name if field.is_required() else '--' + name.replace('_', '-')], options))
    COMMANDS.append({'command': 'repair-request ' + action, 'tool': tool,
        'grant': 'repair_requests.' + grant + '.v1', 'arguments': arguments, 'groups': [],
        'handler': run, 'defaults': {'repair_tool': tool}})
