"""Native aggregate reports; calculations and date defaults belong to the API."""
import json
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.errors import ApiError


def calendar_date(value):
    date.fromisoformat(value)
    return value


Date = Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$'), AfterValidator(calendar_date)]
Filter = Annotated[str, Field(max_length=200)]


class Compliance(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    date_from: Date | None = None
    date_to: Date | None = None
    dsp_id: Filter | None = None


class Report(Compliance):
    vendor_workshop_id: Filter | None = None


REPORTS = ('work_order_completion', 'repair_metrics', 'inspection_compliance')
MODELS = {'get_' + name + '_report': Compliance if name == 'inspection_compliance' else Report for name in REPORTS}


def run(args):
    name = args.aggregate_tool
    query = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields
                                       if hasattr(args, key)}).model_dump(exclude_none=True)
    value = legacy_reads.client_from_args(args).request('GET', '/dashboards/reports/' + name[4:-7].replace('_', '-'), query=query)
    try:
        if not isinstance(value, dict) or any(not isinstance(value.get(key), str) for key in ('date_from', 'date_to')):
            raise ValueError()
        fields, series = {
            'get_work_order_completion_report': (('total_completed',), 'rows'),
            'get_repair_metrics_report': (('eligible_completed_count',), 'daily'),
            'get_inspection_compliance_report': (('active_vehicles', 'submitted_inspections', 'vehicles_inspected',
                'passed', 'flagged', 'conditional', 'incomplete'), None),
        }[name]
        if any(type(value.get(key)) is not int or value[key] < 0 for key in fields):
            raise ValueError()
        if series and (not isinstance(value.get(series), list) or any(not isinstance(row, dict) for row in value[series])):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ApiError('Invalid report response. / Respuesta de informe no válida.') from None
    return value


COMMANDS = [{'command': 'report ' + name.replace('_', '-'), 'tool': 'get_' + name + '_report',
    'description': 'Read the ' + name.replace('_', ' ') + ' report. / Consulta el informe ' + {'work_order_completion': 'de finalización de órdenes de trabajo', 'repair_metrics': 'de métricas de reparación', 'inspection_compliance': 'de cumplimiento de inspecciones'}[name] + '.',
    'grant': 'reports.' + name + '.get.v1', 'groups': [], 'handler': run,
    'defaults': {'aggregate_tool': 'get_' + name + '_report'},
    'arguments': [(['--' + key.replace('_', '-')], {'default': None})
                  for key in MODELS['get_' + name + '_report'].model_fields]} for name in REPORTS]
