"""Read native inspector and DSP driver report quality."""
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.errors import ApiError


class DriverQuality(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    days: int | None = Field(default=None, ge=1, le=365)


class InspectorPerformance(DriverQuality):
    dsp_id: Annotated[str, Field(max_length=200)] | None = None


MODELS = {'list_inspector_performance': InspectorPerformance, 'list_driver_da_quality': DriverQuality}
PATHS = {'list_inspector_performance': 'inspector-performance', 'list_driver_da_quality': 'driver-da-quality'}


def run(args):
    name = args.quality_tool
    query = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields
                                       if hasattr(args, key)}).model_dump(exclude_none=True)
    value = legacy_reads.client_from_args(args).request('GET', '/dashboards/' + PATHS[name], query=query)
    try:
        if not isinstance(value, list):
            raise TypeError()
        for row in value:
            if (not isinstance(row, dict) or type(row.get('inspector_id')) is not int or row['inspector_id'] < 1
                    or not isinstance(row.get('inspector_name'), str)
                    or any(type(row.get(key)) is not int or row[key] < 0 for key in ('total_reported', 'illegitimate_count'))
                    or type(row.get('window_days')) is not int or not 1 <= row['window_days'] <= 365
                    or 'illegitimate_pct' not in row or row['illegitimate_pct'] is not None and type(row['illegitimate_pct']) not in (int, float)):
                raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ApiError('Invalid report response. / Respuesta de informe no válida.') from None
    return value


COMMANDS = []
for name, description in [('list_inspector_performance', 'Read inspector report quality. / Consulta la calidad de los informes del inspector.'),
    ('list_driver_da_quality', 'Read driver report quality. / Consulta la calidad de los informes del conductor.')]:
    COMMANDS.append({'command': 'report ' + PATHS[name], 'tool': name,
        'grant': 'reports.' + name[5:] + '.list.v1', 'description': description,
        'groups': [], 'handler': run, 'defaults': {'quality_tool': name},
        'arguments': [(['--' + key.replace('_', '-')], {'default': None} | ({'type': 'int'} if key == 'days' else {}))
                      for key in MODELS[name].model_fields]})
