"""Read native work for one DSP-local service date."""
import json
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError


def calendar_date(value):
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError('Use YYYY-MM-DD. / Usa AAAA-MM-DD.')
    return value


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dsp_id: Annotated[str, Field(pattern=r'^(?:DSP-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
    service_date: Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$'), AfterValidator(calendar_date)]


class Summary(Query):
    service_date: Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$'), AfterValidator(calendar_date)] | None = None


MODELS = {'list_dsp_scheduled_work': Query, 'get_dsp_daily_work_summary': Summary,
    'acknowledge_dsp_daily_work_summary': Query}


def daily(args):
    write = args.daily_action == 'acknowledge'
    query = (Query if write else Summary).model_validate({'dsp_id': args.dsp_id, 'service_date': args.service_date})
    path = '/dashboards/dsp/' + query.dsp_id + '/daily-work-summary'
    client = legacy_reads.client_from_args(args)
    value = (client.request('POST', path + '/' + query.service_date + '/acknowledge') if write else
        client.request('GET', path, query={'service_date': query.service_date} if query.service_date else {}))
    try:
        if not isinstance(value, dict) or not isinstance(value.get('service_date'), str):
            raise TypeError()
        calendar_date(value['service_date'])
        if query.service_date and value['service_date'] != query.service_date:
            raise ValueError()
        if write:
            if value.get('acknowledged') is not True or datetime.fromisoformat(value['acknowledged_at']).utcoffset() is None:
                raise ValueError()
        elif (not isinstance(value.get('timezone'), str) or not value['timezone']
                or type(value.get('acknowledged')) is not bool or not isinstance(value.get('counts'), dict)
                or any(type(value['counts'].get(k)) is not int or value['counts'][k] < 0 for k in ('scheduled', 'completed', 'open', 'canceled'))
                or any(not isinstance(value.get(k), list) or any(not isinstance(row, dict) for row in value[k]) for k in ('completed', 'open', 'canceled'))):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ApiError('The acknowledgment outcome is unknown. Check the summary before trying again. / El resultado no se conoce. Consulta el resumen antes de intentar de nuevo.', code='outcome_unknown') if write else ApiError('Invalid daily work summary. / Resumen diario de trabajo no válido.') from None
    return value


def run(args):
    query = Query.model_validate({'dsp_id': args.dsp_id, 'service_date': args.service_date})
    value = legacy_reads.client_from_args(args).request('GET', '/dashboards/dsp/' + query.dsp_id + '/scheduled-work',
        query={'service_date': query.service_date})
    try:
        if (not isinstance(value, dict) or value.get('service_date') != query.service_date
                or not isinstance(value.get('timezone'), str) or not value['timezone']
                or not isinstance(value.get('items'), list) or any(not isinstance(row, dict) for row in value['items'])):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ApiError('Invalid scheduled work response. / Respuesta de trabajo programado no válida.') from None
    return value


COMMANDS = [{'command': 'daily-work scheduled', 'tool': 'list_dsp_scheduled_work',
    'grant': 'dashboards.dsp_scheduled_work.list.v1',
    'description': 'Read scheduled fleet work. / Consulta el trabajo programado de la flota.',
    'arguments': [(['dsp_id'], {}), (['--service-date'], {'required': True})],
    'groups': [], 'handler': run, 'defaults': {}}]

for action, tool, grant in [('summary', 'get_dsp_daily_work_summary', 'get'),
        ('acknowledge', 'acknowledge_dsp_daily_work_summary', 'acknowledge')]:
    COMMANDS.append({'command': 'daily-work ' + action, 'tool': tool,
        'grant': 'dashboards.dsp_daily_work_summary.' + grant + '.v1',
        'description': ('Mark a daily work summary as read. / Marca un resumen diario de trabajo como leído.' if action == 'acknowledge' else
            'Read a daily work summary. / Consulta un resumen diario de trabajo.'),
        'arguments': [(['dsp_id'], {}), (['--service-date'], {'required': action == 'acknowledge', 'default': None})],
        'groups': [], 'handler': daily, 'defaults': {'daily_action': action},
        **({'scope': 'nova:read nova:write', 'effect': 'remote_write'} if action == 'acknowledge' else {})})
