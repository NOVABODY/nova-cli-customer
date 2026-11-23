"""Open quote report contract. The API owns authorization and quote state."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

TOOL = 'get_open_quotes_report'
PATH = '/dashboards/reports/open-quotes'
GRANT = 'reports.open_quotes.get.v1'
DESCRIPTION = ('Read open body and CMR quotes. Site administrators only. / '
               'Lee las cotizaciones abiertas de carrocería y CMR. Solo administradores del sitio.')
Kind = Literal['body', 'body_revision', 'cmr']
Count = Annotated[int, Field(ge=0)]


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Kind | None = None
    stage: Literal['awaiting_decision', 'approved_work'] | None = None
    search: Annotated[str, Field(max_length=200)] = ''
    offset: Count = 0
    limit: Annotated[int, Field(ge=1, le=200)] = 25


class Row(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    kind: Kind
    stage: Literal['awaiting_decision', 'approved_work', 'mixed', 'revision_pending']
    reference: str
    dsp_name: str
    shop_name: str
    fleet_id: str
    station_code: str | None
    submitted_at: str
    expires_at: str | None
    amount_cents: Count
    pending_amount_cents: Count
    approved_amount_cents: Count
    proposed_amount_cents: Count | None
    pending_lines: Count | None
    href: str


class Report(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    as_of: str
    total: Count
    amount_cents: Count
    pending_amount_cents: Count
    approved_amount_cents: Count
    currency: Literal['USD']
    items: list[Row]


def run(args):
    from nova_cli_public.legacy_reads import client_from_args
    values = Filters.model_validate({key: getattr(args, key) for key in Filters.model_fields
                                    if hasattr(args, key)}).model_dump(exclude_none=True)
    value = client_from_args(args).request('GET', PATH, query=values)
    Report.model_validate(value)
    return value


COMMANDS = [{'command': 'report open-quotes', 'tool': TOOL, 'description': DESCRIPTION,
    'grant': GRANT, 'groups': [], 'handler': run,
    'arguments': [(['--kind'], {'choices': ['body', 'body_revision', 'cmr'], 'default': None}),
                  (['--stage'], {'choices': ['awaiting_decision', 'approved_work'], 'default': None}),
                  (['--search'], {'default': ''}), (['--offset'], {'type': 'int', 'default': 0}),
                  (['--limit'], {'type': 'int', 'default': 25})]}]
