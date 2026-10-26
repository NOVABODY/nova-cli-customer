"""Native cancellation retains API transitions and terminal state behavior."""
import json

from pydantic import Field, field_validator

from nova_cli_public import legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.repair_requests import STATUSES, Request


class Cancel(Request):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator('reason', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() or None if isinstance(value, str) else value

MODELS = {'cancel_repair_request': Cancel}

def run(args):
    request = Cancel.model_validate({'rr_id': args.rr_id, 'reason': args.reason})
    value = legacy_reads.client_from_args(args).request('POST', '/repair-requests/' + request.rr_id + '/cancel',
        json_body=request.model_dump(exclude={'rr_id'}, exclude_unset=True))
    try:
        if (not isinstance(value, dict) or not isinstance(value.get('id'), str)
                or not value['id'].startswith('RR-') or not value['id'][3:].isdigit()
                or int(value['id'][3:]) != int(request.rr_id.split('-')[-1])
                or value.get('status') not in STATUSES):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ApiError('The cancellation outcome is unknown. Read the repair request before another attempt. / El resultado de la cancelación es desconocido. Consulta la solicitud antes de otro intento.', code='outcome_unknown') from exc
    return value

COMMANDS = [{
    'command': 'repair-request cancel', 'tool': 'cancel_repair_request', 'grant': 'repair_requests.cancel.v1',
    'scope': 'nova:read nova:write', 'effect': 'remote_write',
    'arguments': [(['rr_id'], {}), (['--reason'], {'default': None})],
    'groups': [], 'handler': run, 'defaults': {},
}]
