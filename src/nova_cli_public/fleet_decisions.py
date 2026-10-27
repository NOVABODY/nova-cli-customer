"""Native Fleet Updates queue and issue decisions."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nova_cli_public import legacy_reads
from nova_cli_public.errors import ApiError


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['all', 'unlisted', 'not_found', 'plate_mismatch', 'vin_elsewhere'] = 'all'
    status: Literal['pending', 'resolved'] = 'pending'
    group: Literal['all', 'confirm', 'decide'] = 'all'
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class Resolve(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    issue_id: int = Field(ge=1, le=2147483647)
    action: Literal['keep', 'inactive', 'update_plate', 'plate_correct']
    memo: str | None = Field(default=None, max_length=1000)

    @field_validator('memo')
    @classmethod
    def trim(cls, value):
        return value.strip() or None if value is not None else None


MODELS = {'list_fleet_updates': Filters, 'resolve_fleet_issue': Resolve}


def run(args):
    name = args.fleet_tool
    request = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields if hasattr(args, key)})
    client = legacy_reads.client_from_args(args)
    if name == 'list_fleet_updates':
        value = client.request('GET', '/fleet-updates', query=request.model_dump())
    else:
        value = client.request('POST', f'/fleet-issues/{request.issue_id}/resolve',
            json_body=request.model_dump(exclude={'issue_id'}))
    try:
        if not isinstance(value, dict):
            raise TypeError()
        if name == 'list_fleet_updates':
            if (not isinstance(value.get('items'), list) or any(not isinstance(row, dict) for row in value['items'])
                    or type(value.get('total')) is not int or value['total'] < 0):
                raise ValueError()
        elif (type(value.get('id')) is not int or value['id'] != request.issue_id
                or value.get('status') != 'resolved' or value.get('resolution') != request.action):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        if name == 'list_fleet_updates':
            raise ApiError('Invalid Fleet Updates response. / Respuesta de actualizaciones de flota no válida.') from exc
        raise ApiError('The change outcome is unknown. Check the record before trying again. / El resultado del cambio es desconocido. Revisa el registro antes de intentarlo de nuevo.', code='outcome_unknown') from exc
    return value


COMMANDS = []
for command, tool, grant in [('fleet-updates list', 'list_fleet_updates', 'fleet_updates.list.v1'),
                              ('fleet-issue resolve', 'resolve_fleet_issue', 'fleet_issues.resolve.v1')]:
    arguments = []
    for name, field in MODELS[tool].model_fields.items():
        options = {} if field.is_required() else {'default': field.default}
        if name in ('issue_id', 'limit', 'offset'):
            options['type'] = 'int'
        arguments.append(([name if field.is_required() else '--' + name.replace('_', '-')], options))
    COMMANDS.append({'command': command, 'tool': tool, 'grant': grant,
        'scope': 'nova:read nova:write' if tool == 'resolve_fleet_issue' else 'nova:read',
        'effect': 'remote_write' if tool == 'resolve_fleet_issue' else 'remote_read',
        'arguments': arguments, 'groups': [], 'handler': run, 'defaults': {'fleet_tool': tool}})
