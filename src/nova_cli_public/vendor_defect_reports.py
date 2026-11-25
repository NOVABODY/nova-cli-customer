"""Vendor defect report filters. The API owns authority and report calculations."""
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

GRANT = 'reports.vendor_defects.get.v1'
PATH = '/defects/report'
MIMES = {'csv': 'text/csv', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
MAX_BYTES = 2 * 1024 * 1024


def calendar_date(value):
    date.fromisoformat(value)
    return value


Date = Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$'), AfterValidator(calendar_date)]
Id = Annotated[int, Field(ge=1)]


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Filters(Empty):
    date_from: Date
    date_to: Date
    dsp_id: Id | None = None
    vendor_workshop_id: Id | None = None
    external_vendor_id: Id | None = None
    critical: bool | None = Field(default=None, description='Saved report-time criticality. Omit for all. / Criticidad guardada al reportar. Omite para incluir todas.')
    date_basis: Literal['reported', 'sent'] = Field(default='reported', description='Use sent for provider-accepted external emails. Reported uses defect report dates. / Usa sent para correos externos aceptados por el proveedor. Reported usa fechas de reporte.')
    relationship: Literal['all', 'reported', 'assigned'] = Field(default='all', description='Use assigned for enrolled-shop vendor counts. Dates remain defect report dates. / Usa assigned para cantidades por taller registrado. Las fechas son las de reporte del defecto.')
    ownership_group: Literal['branded', 'rental', 'dsp_owned'] | None = None
    search: Annotated[str, Field(max_length=200)] | None = None
    max_rows: Annotated[int, Field(ge=1, le=10000)] = Field(default=10000, description='JSON row cap. Counts and exports cover the full population. / Límite de filas JSON. Las cantidades y exportaciones incluyen toda la población.')

    @model_validator(mode='after')
    def dates_and_vendor(self):
        if self.date_to < self.date_from or (self.vendor_workshop_id and self.external_vendor_id):
            raise ValueError('Check the dates and select one vendor. / Revisa las fechas y selecciona un taller.')
        return self


class Export(Filters):
    format: Literal['csv', 'xlsx']


class VanCounts(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    total: Annotated[int, Field(ge=0)]


class Row(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    critical_at_report: bool | None


class Summary(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    vans: VanCounts
    total_rows: Annotated[int, Field(ge=0)]
    critical_defects: Annotated[int, Field(ge=0)]
    returned_rows: Annotated[int, Field(ge=0)]


class Report(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    summary: Summary
    items: list[Row]


def validate_export(raw, format):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Invalid export size')
    if format == 'xlsx':
        if not raw.startswith(b'PK\x03\x04'):
            raise ValueError('Invalid Excel file')
    else:
        raw.decode('utf-8-sig')


MODELS = {'get_vendor_defect_report': Filters, 'get_vendor_defect_report_options': Empty,
          'export_vendor_defect_report': Export}


def run(args):
    from .legacy_reads import client_from_args
    name = args.vendor_report_tool
    values = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields
                                         if hasattr(args, key)}).model_dump(exclude_none=True)
    if name == 'export_vendor_defect_report':
        format = values.pop('format')
        values.pop('max_rows', None)  # Exports always contain the full population.
        from pathlib import Path

        from .body_documents import publish
        data = client_from_args(args).request('GET', PATH + '/export.' + format, query=values,
                                              report_format=format)
        return publish(data, Path(args.out).expanduser().absolute(), MIMES[format])
    value = client_from_args(args).request('GET', PATH + ('/options' if name.endswith('_options') else ''), query=values)
    if name == 'get_vendor_defect_report':
        try:
            Report.model_validate(value)
        except ValueError:
            from .errors import ApiError
            raise ApiError('Invalid report response. / Respuesta de informe no válida.') from None
    elif not isinstance(value, dict) or not isinstance(value.get('vendors'), list) or not isinstance(value.get('external_vendors'), list):
        from .errors import ApiError
        raise ApiError('Invalid report options. / Opciones de informe no válidas.')
    return value


def arguments(model):
    output = []
    for key in model.model_fields:
        options = {'default': None}
        if key in ('date_from', 'date_to', 'format'):
            options = {'required': True}
        if key in ('dsp_id', 'vendor_workshop_id', 'external_vendor_id', 'max_rows'):
            options['type'] = 'int'
        if key == 'max_rows':
            options['default'] = 10000
        elif key == 'critical':
            options['action'] = 'BooleanOptionalAction'
        elif key == 'date_basis':
            options.update(choices=['reported', 'sent'], default='reported')
        elif key == 'relationship':
            options.update(choices=['all', 'reported', 'assigned'], default='all')
        elif key == 'format':
            options['choices'] = ['csv', 'xlsx']
        output.append((['--' + key.replace('_', '-')], options))
    if model is Export:
        output.append((['--out'], {'required': True}))
    return output


COMMANDS = [{'command': 'report vendor-defects' + suffix, 'tool': name,
    'description': description + ' Site administrators only. / Solo administradores del sitio.',
    'grant': GRANT, 'groups': [], 'handler': run, 'defaults': {'vendor_report_tool': name},
    'arguments': arguments(MODELS[name])}
    for name, suffix, description in [
        ('get_vendor_defect_report', '', 'Read vendor defect counts and rows. / Lee cantidades y filas de defectos por taller.'),
        ('get_vendor_defect_report_options', '-options', 'Read report choices. / Lee las opciones del informe.'),
        ('export_vendor_defect_report', '-export', 'Read a CSV or Excel report. Limit: 2 MiB. / Lee un informe CSV o Excel. Límite: 2 MiB.')]]
