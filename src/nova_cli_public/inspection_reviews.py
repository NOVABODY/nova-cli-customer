"""Typed inspection quality review requests shared by CLI and MCP."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from nova_cli_public.errors import ApiError

Identifier = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
UNKNOWN = 'outcome_unknown: Read the review before another attempt. / Consulta la revisión antes de otro intento.'


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    inspector_id: Identifier | None = None


class Queue(Query):
    status: Literal['unreviewed', 'all'] = 'unreviewed'
    dsp_id: Identifier | None = None
    since: str | None = None

    @model_validator(mode='after')
    def valid_since(self):
        if self.since is not None and datetime.fromisoformat(self.since).tzinfo is None:
            raise ValueError('Use a date with a time zone. / Usa una fecha con zona horaria.')
        return self


class Quality(Query):
    days: int = Field(default=90, ge=1, le=365)


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    review_id: Identifier


class Start(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    inspection_id: Identifier


class Item(Review):
    observation_id: Identifier
    verdict: Literal['confirmed', 'recategorized', 'invalid']
    expected_updated_at: str
    group_to: Literal['AMR', 'CMR', 'CNMR', 'Body', 'PM', 'Tires', 'Detailing', 'Netradyne'] | None = None
    invalid_reason: Literal['not_present', 'duplicate', 'wrong_part_or_type', 'within_spec', 'evidence_insufficient', 'other'] | None = None
    comment: Text | None = None

    @model_validator(mode='after')
    def valid_verdict(self):
        stamp = datetime.fromisoformat(self.expected_updated_at)
        if stamp.tzinfo is None or (self.verdict == 'recategorized') != (self.group_to is not None) or (self.verdict == 'invalid') != (self.invalid_reason is not None):
            raise ValueError('Use the current update time and the fields for this verdict. / Usa la hora de actualización actual y los campos para este resultado.')
        return self


MODELS = {'list_inspection_reviews': Queue, 'get_inspection_review': Review,
    'start_inspection_review': Start, 'set_inspection_review_item': Item,
    'complete_inspection_review': Review, 'get_inspector_quality': Quality, 'list_inspection_review_feedback': Query}
WRITES = {'start_inspection_review', 'set_inspection_review_item', 'complete_inspection_review'}
GRANTS = dict(zip(MODELS, ['inspection_reviews.queue.list.v1', 'inspection_reviews.get.v1',
    'inspection_reviews.start.v1', 'inspection_reviews.items.set.v1', 'inspection_reviews.complete.v1',
    'inspection_reviews.quality.get.v1', 'inspection_reviews.feedback.list.v1']))
DESCRIPTIONS = dict(zip(MODELS, ['Read the inspection review queue. / Consulta la cola de revisión de inspecciones.',
    'Read an inspection review. / Consulta una revisión de inspección.',
    'Start an inspection review. Site admin only. / Inicia una revisión de inspección. Solo para administradores del sitio.',
    'Save a verdict and an optional customer-visible comment. A closed decision window records invalid findings for scoring only. / Guarda un resultado y un comentario opcional visible para el cliente. Si el plazo de decisión terminó, los hallazgos no válidos solo afectan la puntuación.',
    'Complete a review. Untouched observations are confirmed. / Completa una revisión. Se confirman las observaciones sin cambios.',
    'Read inspector quality scores. / Consulta las puntuaciones de calidad de los inspectores.',
    'Read inspection review feedback. / Consulta los comentarios de revisión de inspecciones.']))


def request_parts(name, query):
    data = query.model_dump(exclude_none=True)
    root = '/inspection-reviews'
    if name == 'start_inspection_review':
        return 'POST', root, {'json_body': data, 'retry_auth': False}
    if name == 'set_inspection_review_item':
        return 'PUT', f'{root}/{data.pop("review_id")}/items/{data.pop("observation_id")}', {'json_body': data, 'retry_auth': False}
    if name == 'complete_inspection_review':
        return 'POST', f'{root}/{data["review_id"]}/complete', {'retry_auth': False}
    if name == 'get_inspection_review':
        return 'GET', f'{root}/{data["review_id"]}', {}
    suffix = {'list_inspection_reviews': 'queue', 'get_inspector_quality': 'quality', 'list_inspection_review_feedback': 'feedback'}[name]
    return 'GET', f'{root}/{suffix}', {'params': data}


def execute(client, name, arguments):
    method, path, options = request_parts(name, MODELS[name].model_validate(arguments))
    try:
        result = client.request(method, path, **options)
    except ApiError as exc:
        if name in WRITES and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    if not isinstance(result, dict):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name in WRITES else ApiError('Invalid review response. / Respuesta de revisión no válida.')
    return result


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.inspection_review_tool
    return execute(client_from_args(args), name, {key: getattr(args, key) for key in MODELS[name].model_fields})


def declarations():
    commands = []
    for action, name in zip(['queue', 'show', 'start', 'set', 'complete', 'quality', 'feedback'], MODELS):
        arguments = []
        for field, info in MODELS[name].model_fields.items():
            positional = field in {'review_id', 'observation_id', 'inspection_id'}
            options = {'type': 'int'} if field.endswith('_id') or field == 'days' else {}
            if not positional:
                options.update(required=info.is_required())
                if not info.is_required():
                    options['default'] = info.default
            arguments.append(([field if positional else '--' + field.replace('_', '-')], options))
        entry = {'command': 'inspection-review ' + action, 'tool': name, 'grant': GRANTS[name],
            'description': DESCRIPTIONS[name], 'arguments': arguments, 'groups': [], 'handler': command,
            'defaults': {'inspection_review_tool': name}}
        if name in WRITES:
            entry.update(scope='nova:read nova:write', effect='remote_write')
        commands.append(entry)
    return commands


COMMANDS = declarations()
