"""Named CMR/CNMR quote adapters. The API owns authorization and payment gates."""
import json
import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from nova_cli_public.errors import ApiError, UsageError

KEY = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
CODE = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')
SOURCES = {'capacity', 'service_writer'}
STATUSES = {'submitted', 'decided', 'expired', 'withdrawn'}
LINE_DECISIONS = {'approved', 'rejected'}
Cents = Annotated[int, Field(ge=0, le=99999999)]
Record = Annotated[int, Field(ge=1, le=2147483647)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


def _id(prefix):
    def parse(value):
        if type(value) is bool:
            raise ValueError('Use a record ID. / Usa un ID de registro.')
        if type(value) is int:
            number = value
        elif isinstance(value, str) and re.fullmatch(rf'(?:{prefix}-)?[0-9]{{1,14}}', value):
            number = int(value.split('-')[-1])
        else:
            raise ValueError('Use a record ID. / Usa un ID de registro.')
        if not 1 <= number <= 2147483647:
            raise ValueError('Use a record ID. / Usa un ID de registro.')
        return number
    return parse


class Line(Closed):
    defect_id: Record
    amount_cents: Cents
    note: Note | None = None

    @field_validator('defect_id', mode='before')
    @classmethod
    def numeric_defect(cls, value):
        return _id('FD')(value)


class Submit(Closed):
    source: Literal['capacity', 'service_writer'] = 'service_writer'
    vehicle_id: Record
    capacity_award_van_id: Record | None = None
    work_order_id: Record | None = None
    lines: Annotated[list[Line], Field(min_length=1, max_length=200)]
    idempotency_key: Annotated[str, Field(pattern=KEY.pattern)] | None = None

    @field_validator('vehicle_id', mode='before')
    @classmethod
    def numeric_vehicle(cls, value):
        return _id('VAN')(value)

    @field_validator('work_order_id', mode='before')
    @classmethod
    def numeric_work_order(cls, value):
        if value is None:
            return None
        return _id('WO')(value)


class QuoteQuery(Closed):
    quote_id: Record


class QuoteList(Closed):
    vehicle_id: Record | None = None
    inspection_id: Record | None = None
    defect_ids: Annotated[list[Record], Field(max_length=200)] | None = None
    status: Literal['pending', 'all'] = 'pending'
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=200)] = 50

    @field_validator('vehicle_id', 'inspection_id', mode='before')
    @classmethod
    def numeric_filter(cls, value, info):
        if value is None:
            return None
        return _id('VAN' if info.field_name == 'vehicle_id' else 'INS')(value)

    @field_validator('defect_ids', mode='before')
    @classmethod
    def numeric_defects(cls, value):
        if value is None:
            return None
        return [_id('FD')(item) for item in value]


class Withdraw(QuoteQuery):
    idempotency_key: Annotated[str, Field(pattern=KEY.pattern)] | None = None


class Dismiss(QuoteQuery):
    defect_id: Record
    idempotency_key: Annotated[str, Field(pattern=KEY.pattern)] | None = None

    @field_validator('defect_id', mode='before')
    @classmethod
    def numeric_defect(cls, value):
        return _id('FD')(value)


class Decision(Dismiss):
    decision: Literal['approved', 'rejected']
    expected_amount_cents: Cents


def line_ok(line) -> bool:
    return (isinstance(line, dict) and type(line.get('defect_id')) is int and 1 <= line['defect_id'] <= 2147483647
            and type(line.get('amount_cents')) is int and 0 <= line['amount_cents'] <= 99999999
            and (line.get('decision') is None or line.get('decision') in LINE_DECISIONS))


def quote_ok(value, quote_id=None) -> bool:
    if not isinstance(value, dict) or type(value.get('id')) is not int or not 1 <= value['id'] <= 2147483647:
        return False
    if quote_id is not None and value['id'] != quote_id:
        return False
    lines = value.get('lines')
    return (value.get('source') in SOURCES and value.get('status') in STATUSES
            and isinstance(lines, list) and all(line_ok(line) for line in lines))


def page_ok(value, limit) -> bool:
    if not isinstance(value, dict):
        return False
    rows, count = value.get('rows'), value.get('count')
    return (type(count) is int and count >= 0 and isinstance(rows, list) and len(rows) <= limit
            and count >= len(rows) and all(quote_ok(row) for row in rows))



MODELS = {'list_cmr_quotes': QuoteList, 'get_cmr_quote': QuoteQuery, 'submit_cmr_quote': Submit,
    'withdraw_cmr_quote': Withdraw, 'dismiss_cmr_quote_line': Dismiss, 'decide_cmr_quote_line': Decision}
WRITES = {'submit_cmr_quote', 'withdraw_cmr_quote', 'dismiss_cmr_quote_line', 'decide_cmr_quote_line'}
UNKNOWN = 'The outcome is unknown. Read the quote before another attempt. / El resultado no se conoce. Consulta la cotización antes de intentar de nuevo.'


def execute(client, name, arguments):
    request = MODELS[name].model_validate(arguments)
    values = request.model_dump(exclude_none=True, exclude={'idempotency_key'})
    write = name in WRITES
    key = str(uuid.UUID(request.idempotency_key)) if write and request.idempotency_key else str(uuid.uuid4()) if write else None
    path, body, query = '/cmr-quotes', None, None
    if name == 'list_cmr_quotes':
        query = values
    elif name == 'submit_cmr_quote':
        body = values
    else:
        path += '/' + str(values.pop('quote_id'))
        if name == 'withdraw_cmr_quote':
            path += '/withdraw'
        elif name in ('dismiss_cmr_quote_line', 'decide_cmr_quote_line'):
            path += '/lines/' + str(values.pop('defect_id')) + ('/dismiss' if name == 'dismiss_cmr_quote_line' else '/decision')
            if name == 'decide_cmr_quote_line':
                body = values
    try:
        value = client.request('POST' if write else 'GET', path, json_body=body, query=query,
            max_bytes=2 * 1024 * 1024, retry_auth=not write, expected_statuses=(201 if name == 'submit_cmr_quote' else 200,), **({'idempotency_key': key} if write else {}))
    except ApiError as exc:
        if write and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400 or exc.code == 'outcome_unknown'):
            raise ApiError(UNKNOWN + ' idempotency_key=' + key, code='outcome_unknown') from None
        code = exc.code if isinstance(exc.code, str) and CODE.fullmatch(exc.code) else 'quote_rejected'
        message = 'Check the quote and account permissions. / Comprueba la cotización y los permisos de la cuenta.'
        if code in ('payout_account_required', 'payment_method_required'):
            message = 'Finish payment setup in Nova. / Termina la configuración del pago en Nova.'
        raise ApiError(message, status=exc.status, code=code) from None
    try:
        json.dumps(value, allow_nan=False)
        valid = page_ok(value, request.limit) if name == 'list_cmr_quotes' else quote_ok(value, getattr(request, 'quote_id', None))
        if valid and name == 'submit_cmr_quote':
            found = {(line['defect_id'], line['amount_cents']) for line in value['lines']}
            valid = value.get('source') == request.source and value.get('vehicle_id') == request.vehicle_id and all(
                (line.defect_id, line.amount_cents) in found for line in request.lines)
        if valid and name == 'withdraw_cmr_quote':
            valid = value['status'] == 'withdrawn'
        if valid and name in ('dismiss_cmr_quote_line', 'decide_cmr_quote_line'):
            valid = any(line['defect_id'] == request.defect_id and (
                isinstance(line.get('dismissed_at'), str) and bool(line['dismissed_at']) if name == 'dismiss_cmr_quote_line' else
                line.get('decision') == request.decision and line['amount_cents'] == request.expected_amount_cents) for line in value['lines'])
        if not valid:
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise ApiError(UNKNOWN + ' idempotency_key=' + key, code='outcome_unknown') if write else ApiError(
            'Invalid quote response. / Respuesta de cotización no válida.', code='invalid_response') from None
    return value


def command(args):
    from nova_cli_public.cli import client_from_args
    try:
        if args.quote_tool == 'submit_cmr_quote':
            if len(args.data) > 2 * 1024 * 1024:
                raise ValueError()
            values = json.loads(args.data)
            if not isinstance(values, dict):
                raise ValueError()
            if args.idempotency_key is not None:
                values['idempotency_key'] = args.idempotency_key
        else:
            values = {key: getattr(args, key) for key in MODELS[args.quote_tool].model_fields if hasattr(args, key)}
        return execute(client_from_args(args), args.quote_tool, values)
    except (ValueError, TypeError, RecursionError):
        raise UsageError('Check the quote data. / Comprueba los datos de la cotización.') from None


SPECS = [
    ('list', 'list_cmr_quotes', 'list', [(['--vehicle-id'], {}), (['--inspection-id'], {}), (['--defect-ids'], {'type': 'int', 'action': 'append'}),
        (['--status'], {'default': 'pending', 'choices': ['pending', 'all']}), (['--limit'], {'type': 'int', 'default': 50}), (['--offset'], {'type': 'int', 'default': 0})]),
    ('get', 'get_cmr_quote', 'get', [(['quote_id'], {'type': 'int'})]),
    ('submit', 'submit_cmr_quote', 'submit', [(['--data'], {'required': True})]),
    ('withdraw', 'withdraw_cmr_quote', 'withdraw', [(['quote_id'], {'type': 'int'})]),
    ('dismiss', 'dismiss_cmr_quote_line', 'dismiss', [(['quote_id'], {'type': 'int'}), (['--defect-id'], {'required': True})]),
    ('decide', 'decide_cmr_quote_line', 'decide', [(['quote_id'], {'type': 'int'}), (['--defect-id'], {'required': True}),
        (['--decision'], {'required': True, 'choices': ['approved', 'rejected']}), (['--expected-amount-cents'], {'type': 'int', 'required': True})]),
]
DESCRIPTIONS = {name: 'Read or change a CMR/CNMR quote. Amounts are integer cents. Payment setup stays in Nova. After an unknown outcome, read the quote; reuse the same idempotency key for the same request. / Consulta o cambia una cotización CMR/CNMR. Los importes son centavos enteros. El pago se configura en Nova. Tras un resultado desconocido, consulta la cotización; reutiliza la misma clave de idempotencia para la misma solicitud.' for name in MODELS}


COMMANDS = [
    {'command': 'cmr-quote ' + action, 'tool': name, 'grant': 'cmr_quotes.' + grant + '.v1',
     'description': DESCRIPTIONS[name], 'arguments': arguments + ([(['--idempotency-key'], {})] if name in WRITES else []),
     'groups': [], 'handler': command, 'defaults': {'quote_tool': name},
     'scope': 'nova:read nova:write' if name in WRITES else 'nova:read', 'effect': 'remote_write' if name in WRITES else 'remote_read'}
    for action, name, grant, arguments in SPECS
]
