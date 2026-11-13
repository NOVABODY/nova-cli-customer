"""Typed inspection quality review requests shared by CLI and MCP.

Verdicts are drafts. Nothing reaches the DSP or shop until a completion that
carries the token of a preview the reviewer has seen.
"""
import sys
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from nova_cli_public.errors import ApiError

Identifier = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Token = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r'^\S+$')]
UNKNOWN = 'outcome_unknown: Read the review before another attempt. / Consulta la revisión antes de otro intento.'
STALE = ('inspection_review_preview_stale: The review changed after the preview. Nothing was applied. '
    'Check the new effects, then preview and complete again. / La revisión cambió después de la vista previa. '
    'No se aplicó nada. Revisa los nuevos efectos y vuelve a generar la vista previa y completar.')
UNDECIDED = ('inspection_review_undecided: Some defects have no decision. Set a verdict for each one, or use '
    'confirm_remaining to confirm the rest. Nothing was applied. / Algunos defectos no tienen decisión. Guarda un '
    'resultado para cada uno o usa confirm_remaining para confirmar el resto. No se aplicó nada.')
ALREADY_APPLIED = ('An earlier review pass already applied this correction, so this draft cannot change it. Read the '
    'review and keep that decision. / Una revisión anterior ya aplicó esta corrección y este borrador no puede '
    'cambiarla. Consulta la revisión y mantén esa decisión.')
GROUP_LOCKED = ('recategorize_not_allowed: The repair group of this defect cannot be changed now. Choose Confirm or '
    'Not valid instead. Nothing was applied. / El grupo de reparación de este defecto no se puede cambiar ahora. '
    'Elige Confirmar o No válido. No se aplicó nada.')
BLOCKED = ('inspection_review_blocked: Change the verdict of the blocked defects listed above. Nothing was applied. '
    '/ Cambia el resultado de los defectos bloqueados de la lista. No se aplicó nada.')
# 409 refusals that the caller can fix; each message says how.
REFUSALS = {'inspection_review_undecided': UNDECIDED, 'recategorize_not_allowed': GROUP_LOCKED,
    'quality_rejection_already_applied': 'quality_rejection_already_applied: ' + ALREADY_APPLIED,
    'quality_category_already_applied': 'quality_category_already_applied: ' + ALREADY_APPLIED}


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    inspector_id: Identifier | None = None


class Queue(Query):
    status: Literal['unreviewed', 'in_progress', 'completed', 'all'] = 'unreviewed'
    dsp_id: Identifier | None = None
    station_code: Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9-]{1,16}$')] | None = None
    submitted_since: str | None = None
    has_critical: bool | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def valid_since(self):
        if self.submitted_since is not None and datetime.fromisoformat(self.submitted_since).tzinfo is None:
            raise ValueError('Use a date with a time zone. / Usa una fecha con zona horaria.')
        return self


class Quality(Query):
    days: int = Field(default=30, ge=1, le=365)


class Feedback(Quality):
    verdict: Literal['corrections', 'confirmed', 'all'] = 'corrections'
    unseen: bool | None = None
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    review_id: Identifier


class Start(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    inspection_id: Identifier


class Observation(Review):
    observation_id: Identifier


class Item(Observation):
    verdict: Literal['confirmed', 'recategorized', 'invalid']
    group_to: Literal['AMR', 'CMR', 'CNMR', 'Body', 'PM', 'Tires', 'Detailing', 'Netradyne'] | None = None
    invalid_reason: Literal['not_present', 'duplicate', 'wrong_part_or_type', 'within_spec', 'evidence_insufficient', 'other'] | None = None
    comment: Comment | None = Field(default=None, description='Omit to keep the saved comment; an empty string clears it.')

    @model_validator(mode='after')
    def valid_verdict(self):
        if (self.verdict == 'recategorized') != (self.group_to is not None) or (self.verdict == 'invalid') != (self.invalid_reason is not None):
            raise ValueError('Use the fields for this verdict. / Usa los campos para este resultado.')
        return self


class Summary(Quality):
    """Inspectors read their own; site admins must choose an inspector_id."""


class Seen(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    item_id: Identifier


class Preview(Review):
    confirm_remaining: bool = False


class Complete(Preview):
    preview_token: Token = Field(description='The token from preview_inspection_review, after the reviewer has seen its effects.')


class CliComplete(Preview):
    preview_token: Token | None = None


SET, UNSET, PREVIEW, COMPLETE = ('set_inspection_review_item', 'unset_inspection_review_item',
    'preview_inspection_review', 'complete_inspection_review')
SUMMARY, SEEN = 'get_inspection_review_feedback_summary', 'mark_inspection_review_feedback_seen'
MODELS = {'list_inspection_reviews': Queue, 'get_inspection_review': Review,
    'start_inspection_review': Start, SET: Item, UNSET: Observation, PREVIEW: Preview,
    COMPLETE: Complete, 'get_inspector_quality': Quality, 'list_inspection_review_feedback': Feedback,
    SUMMARY: Summary, SEEN: Seen}
CLI_MODELS = {**MODELS, COMPLETE: CliComplete}
ACTIONS = dict(zip(MODELS, ['queue', 'show', 'start', 'set', 'unset', 'preview', 'complete', 'quality', 'feedback',
    'feedback-summary', 'feedback-seen']))
WRITES = {'start_inspection_review', SET, UNSET, COMPLETE, SEEN}
GRANTS = dict(zip(MODELS, ['inspection_reviews.queue.list.v1', 'inspection_reviews.get.v1',
    'inspection_reviews.start.v1', 'inspection_reviews.items.set.v1', 'inspection_reviews.items.unset.v1',
    'inspection_reviews.completion_preview.get.v1', 'inspection_reviews.complete.v1',
    'inspection_reviews.quality.get.v1', 'inspection_reviews.feedback.list.v1',
    'inspection_reviews.feedback.summary.get.v1', 'inspection_reviews.feedback.seen.v1']))
DESCRIPTIONS = dict(zip(MODELS, ['Read the inspection review queue. / Consulta la cola de revisión de inspecciones.',
    'Read an inspection review. / Consulta una revisión de inspección.',
    'Start or resume an inspection review. Site admin only. / Inicia o retoma una revisión de inspección. Solo para administradores del sitio.',
    'Save a verdict and an optional comment as a draft. Nothing changes for the DSP or shop until you complete the review. / Guarda un resultado y un comentario opcional como borrador. Nada cambia para el DSP ni el taller hasta que completes la revisión.',
    'Clear a draft verdict so the defect is not reviewed again. / Borra un resultado en borrador para que el defecto vuelva a quedar sin revisar.',
    'List what completing the review will do: queue removals, shop request withdrawals, group changes, comments, ungrounding and the score change. Changes nothing. / Muestra lo que hará completar la revisión: retiros de la cola, solicitudes al taller retiradas, cambios de grupo, comentarios, desinmovilizaciones y el cambio de puntuación. No cambia nada.',
    'Complete the review and apply every draft at once. Requires preview_token from preview_inspection_review: show its effects to the reviewer first. If the review changed, nothing is applied and the new effects are returned; preview again and do not retry on your own. / Completa la revisión y aplica todos los borradores a la vez. Requiere preview_token de preview_inspection_review: muestra antes sus efectos al revisor. Si la revisión cambió, no se aplica nada y se devuelven los nuevos efectos; vuelve a generar la vista previa y no lo reintentes por tu cuenta.',
    'Read inspector quality scores. / Consulta las puntuaciones de calidad de los inspectores.',
    'Read inspection review feedback. / Consulta los comentarios de revisión de inspecciones.',
    'Read your review feedback summary: unseen corrections, latest review and score. / Consulta el resumen de tus comentarios de revisión: correcciones sin ver, la última revisión y la puntuación.',
    'Mark one of your own feedback items as seen (Got it). Only the inspector who owns it can do this. / Marca como visto uno de tus comentarios (Entendido). Solo puede hacerlo el inspector al que pertenece.']))
EFFECTS = {
    'reject_from_dsp_queue': 'removed from the DSP queue / se retira de la cola del DSP',
    'withdraw_shop_request': 'shop request withdrawn / se retira la solicitud al taller',
    'score_only_invalid': 'not valid, score only / no válido, solo puntuación',
    'group_change': 'repair group changes / cambia el grupo de reparación',
    'comment': 'comment posted / se publica el comentario',
    'unground': 'grounding resolved / se resuelve la inmovilización',
    'confirm': 'confirmed / confirmado',
}


def _flags(data):
    return {key: str(value).lower() if isinstance(value, bool) else value for key, value in data.items()}


def request_parts(name, query):
    data = query.model_dump(exclude_none=True)
    root = '/inspection-reviews'
    if name == 'start_inspection_review':
        return 'POST', root, {'json_body': data, 'retry_auth': False}
    if name in (SET, UNSET):
        path = f'{root}/{data.pop("review_id")}/items/{data.pop("observation_id")}'
        return ('PUT', path, {'json_body': data, 'retry_auth': False}) if name == SET else ('DELETE', path, {'retry_auth': False})
    if name == PREVIEW:
        return 'GET', f'{root}/{data["review_id"]}/completion-preview', {'query': {'confirm_remaining': str(data['confirm_remaining']).lower()}}
    if name == COMPLETE:
        return 'POST', f'{root}/{data.pop("review_id")}/complete', {'json_body': data, 'retry_auth': False}
    if name == 'get_inspection_review':
        return 'GET', f'{root}/{data["review_id"]}', {}
    if name == SUMMARY:
        return 'GET', f'{root}/feedback/summary', {'query': _flags(data)}
    if name == SEEN:
        return 'POST', f'{root}/feedback/{data["item_id"]}/seen', {'retry_auth': False}
    suffix = {'list_inspection_reviews': 'queue', 'get_inspector_quality': 'quality', 'list_inspection_review_feedback': 'feedback'}[name]
    return 'GET', f'{root}/{suffix}', {'query': _flags(data)}


def effect_lines(preview):
    """Plain lines for every effect, the blockers and the score change."""
    lines = []
    for effect in preview.get('effects') or []:
        kind = effect.get('kind')
        text = EFFECTS.get(kind, str(kind))
        if kind == 'withdraw_shop_request' and effect.get('shop_name'):
            text += f" ({effect['shop_name']})"
        if kind == 'group_change':
            text += f" ({effect.get('from')} -> {effect.get('to')})"
        if kind == 'comment' and effect.get('visibility'):
            text += f" ({effect['visibility']})"
        lines.append(f"Defect / Defecto {effect.get('observation_id')}: {text}")
    for blocker in preview.get('blocking') or []:
        lines.append(f"Defect / Defecto {blocker.get('observation_id')}: blocked / bloqueado ({blocker.get('code')})")
    score = preview.get('score') or {}
    if score:
        before, after = (('-' if score.get(key) is None else score[key]) for key in ('before', 'after'))
        lines.append(f"Score / Puntuación {score.get('inspector_name') or score.get('inspector_id')}: {before} -> {after}")
    return lines


def _fresh_preview(client, exc, query):
    fresh = exc.detail.get('preview') if isinstance(exc.detail, dict) else None
    if not isinstance(fresh, dict):
        method, path, options = request_parts(PREVIEW, Preview(review_id=query.review_id, confirm_remaining=query.confirm_remaining))
        try:
            fresh = client.request(method, path, **options)
        except ApiError:
            fresh = None
    if not isinstance(fresh, dict):
        return None
    # The token is withheld: completing again needs a new preview the reviewer has seen.
    return {key: value for key, value in fresh.items() if key != 'token'}


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    method, path, options = request_parts(name, query)
    try:
        result = client.request(method, path, **options)
    except ApiError as exc:
        if name in WRITES and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        if name == COMPLETE and exc.status == 409 and exc.code == 'inspection_review_preview_stale':
            fresh = _fresh_preview(client, exc, query)
            message = '\n'.join([STALE, *effect_lines(fresh or {})])
            raise ApiError(message, status=409, code=exc.code, detail={'preview': fresh}) from exc
        if exc.status == 409 and exc.code in REFUSALS:
            raise ApiError(REFUSALS[exc.code], status=409, code=exc.code, detail=exc.detail) from exc
        raise
    if name == UNSET and result is None:
        return {'review_id': query.review_id, 'observation_id': query.observation_id, 'verdict': None}
    if name == SEEN and result is None:
        return {'item_id': query.item_id, 'seen': True}
    if not isinstance(result, dict):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name in WRITES else ApiError('Invalid review response. / Respuesta de revisión no válida.')
    return result


def complete_command(args):
    """Preview, print the effects, then complete with that preview's token."""
    from nova_cli_public.legacy_reads import client_from_args
    client = client_from_args(args)
    base = {'review_id': args.review_id, 'confirm_remaining': args.confirm_remaining}
    token = args.preview_token
    if token is None:
        preview = execute(client, PREVIEW, base)
        for line in effect_lines(preview) or ['No effects. / Sin efectos.']:
            print(line, file=sys.stderr)
        blocking = preview.get('blocking') or []
        if blocking:
            undecided = any(blocker.get('code') == 'undecided' for blocker in blocking)
            raise ApiError(UNDECIDED if undecided else BLOCKED, status=409,
                code='inspection_review_undecided' if undecided else 'inspection_review_blocked')
        token = preview.get('token')
    return execute(client, COMPLETE, {**base, 'preview_token': token})


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.inspection_review_tool
    return execute(client_from_args(args), name, {key: getattr(args, key) for key in MODELS[name].model_fields})


def declarations():
    commands = []
    for name, action in ACTIONS.items():
        arguments = []
        for field, info in CLI_MODELS[name].model_fields.items():
            positional = field in {'review_id', 'observation_id', 'inspection_id', 'item_id'}
            flag = '--' + field.replace('_', '-')
            if info.annotation in (bool, bool | None):
                arguments.append(([flag], {'action': 'store_true', 'default': info.default}))
                continue
            options = {'type': 'int'} if field.endswith('_id') or field in {'days', 'limit', 'offset'} else {}
            if not positional:
                options.update(required=info.is_required())
                if not info.is_required():
                    options['default'] = info.default
            arguments.append(([field if positional else flag], options))
        handler = complete_command if name == COMPLETE else command
        entry = {'command': 'inspection-review ' + action, 'tool': name, 'grant': GRANTS[name],
            'description': DESCRIPTIONS[name], 'arguments': arguments, 'groups': [], 'handler': handler,
            'defaults': {'inspection_review_tool': name}}
        if name in WRITES:
            entry.update(scope='nova:read nova:write', effect='remote_write')
        commands.append(entry)
    return commands


COMMANDS = declarations()

