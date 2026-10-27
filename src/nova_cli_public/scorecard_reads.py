"""Fixed native scorecard reads; the API owns ratings and release rules."""
import json
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError

Reference = Annotated[str, Field(pattern=r'^(?:VW-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]


class Scorecard(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vendor_workshop_id: Reference
    days: int | None = Field(default=None, ge=1, le=365)
    subject_kind: Literal['work_order', 'body_repair'] | None = None


class Benchmarks(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vendor_workshop_id: Reference
    days: int | None = Field(default=None, ge=1, le=365)
    dsp_id: Annotated[str, Field(max_length=200)] | None = None


class PendingFeedback(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    days: int | None = Field(default=None, ge=1, le=3650)
    dsp_id: Annotated[str, Field(max_length=200)] | None = None


class ProblemReports(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vendor_workshop_id: Annotated[str, Field(max_length=200)] | None = None
    status: Annotated[str, Field(max_length=200)] | None = None


QUEUES = {'list_pending_vendor_feedback': 'pending-feedback', 'list_vendor_problem_reports': 'problem-reports'}
MODELS = {'get_vendor_scorecard': Scorecard, 'get_vendor_scorecard_benchmarks': Benchmarks,
          'list_pending_vendor_feedback': PendingFeedback, 'list_vendor_problem_reports': ProblemReports}


def run(args):
    name = args.scorecard_tool
    values = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields
                                        if hasattr(args, key)}).model_dump(exclude_none=True)
    queue = name in QUEUES
    reference = None if queue else values.pop('vendor_workshop_id')
    benchmarks = name == 'get_vendor_scorecard_benchmarks'
    path = '/vendor-scorecard/' + (QUEUES[name] if queue else reference + ('/benchmarks' if benchmarks else ''))
    value = legacy_reads.client_from_args(args).request('GET', path, query=values)
    try:
        if queue:
            if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                raise ValueError()
            json.dumps(value, allow_nan=False)
            return value
        if not isinstance(value, dict):
            raise TypeError()
        if benchmarks:
            if not all(key in value and (value[key] is None or type(value[key]) in (int, float))
                       for key in ('primary_vendor_pct', 'best_in_station_pct', 'best_in_class_pct')):
                raise ValueError()
        elif (type(value.get('vendor_workshop_id')) is not int
              or value['vendor_workshop_id'] != int(reference.split('-')[-1])
              or type(value.get('window_days')) is not int or value['window_days'] < 1
              or type(value.get('total_feedback')) is not int or value['total_feedback'] < 0
              or 'satisfaction_pct' not in value or value['satisfaction_pct'] is not None and type(value['satisfaction_pct']) not in (int, float)
              or not isinstance(value.get('recent'), list) or any(not isinstance(row, dict) for row in value['recent'])):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ApiError('Invalid vendor score response. / Respuesta de calificación del proveedor no válida.') from None
    return value


COMMANDS = []
for action, tool, grant, description in [
    ('pending-feedback', 'list_pending_vendor_feedback', 'vendor_scorecard.pending_feedback.list.v1', 'Read repairs that need a rating. / Consulta las reparaciones que necesitan una calificación.'),
    ('problem-reports', 'list_vendor_problem_reports', 'vendor_scorecard.problem_reports.list.v1', 'Read vendor repair problem reports. / Consulta los informes de problemas de reparación del proveedor.'),
    ('get', 'get_vendor_scorecard', 'vendor_scorecard.get.v1', 'Read vendor repair scores. / Consulta las calificaciones de reparación del proveedor.'),
    ('benchmarks', 'get_vendor_scorecard_benchmarks', 'vendor_scorecard.benchmarks.get.v1', 'Read vendor repair score comparisons. / Consulta las comparaciones de calificaciones de reparación de proveedores.'),
]:
    COMMANDS.append({'command': 'vendor-scorecard ' + action, 'tool': tool, 'grant': grant,
        'description': description, 'groups': [], 'handler': run, 'defaults': {'scorecard_tool': tool},
        'arguments': [([key if field.is_required() else '--' + key.replace('_', '-')],
            ({} if field.is_required() else {'default': None}) | ({'type': 'int'} if key == 'days' else {}))
            for key, field in MODELS[tool].model_fields.items()]})
