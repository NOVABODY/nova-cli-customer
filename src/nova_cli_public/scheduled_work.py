"""Read native work for one DSP-local service date."""
import json
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError


def calendar_date(value):
    date.fromisoformat(value)
    return value


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dsp_id: Annotated[str, Field(pattern=r'^(?:DSP-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
    service_date: Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$'), AfterValidator(calendar_date)]


MODELS = {'list_dsp_scheduled_work': Query}


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
