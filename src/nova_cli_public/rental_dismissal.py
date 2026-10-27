"""Dismiss native rental reminders without accepting cost or routing work."""
import json

from nova_cli_public import legacy_reads
from nova_cli_public.errors import ApiError
from nova_cli_public.repair_requests import Request

MODELS = {'dismiss_rental_routing': Request}


def run(args):
    request = Request.model_validate({'rr_id': args.rr_id})
    value = legacy_reads.client_from_args(args).request('POST', '/repair-requests/' + request.rr_id + '/dismiss-rental-routing')
    try:
        if (not isinstance(value, dict) or not isinstance(value.get('id'), str)
                or not value['id'].startswith('RR-') or not value['id'][3:].isdigit()
                or int(value['id'][3:]) != int(request.rr_id.split('-')[-1]) or value.get('status') != 'open'):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ApiError('The dismissal outcome is unknown. Read the repair request before another attempt. / El resultado es desconocido. Consulta la solicitud de reparación antes de otro intento.', code='outcome_unknown') from exc
    return value


COMMANDS = [{
    'command': 'repair-request dismiss-rental-routing', 'tool': 'dismiss_rental_routing',
    'description': 'Dismiss a rental routing reminder. / Descarta un aviso de asignación de alquiler.',
    'grant': 'repair_requests.rental_routing.dismiss.v1', 'scope': 'nova:read nova:write', 'effect': 'remote_write',
    'arguments': [(['rr_id'], {})], 'groups': [], 'handler': run, 'defaults': {},
}]
