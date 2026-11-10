"""Rate one pending repair with explicit confirmation and correction authority."""
import json
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import ApiError, UsageError

INVALID = 'Check the repair, rating and tags. Use at most 1000 characters for the reason. / Comprueba la reparación, la calificación y las etiquetas. Usa un máximo de 1000 caracteres para el motivo.'
UNKNOWN = 'outcome_unknown: Read the repair before another attempt. / Consulta la reparación antes de otro intento.'
PATH = '/vendor-scorecard/feedback'


def positive(value):
    if not 1 <= int(value.split('-')[-1]) <= 2147483647:
        raise ValueError(INVALID)
    return value


WorkId = Annotated[str, Field(pattern=r'^(?:WO-)?[0-9]{1,14}$'), AfterValidator(positive)]
BodyId = Annotated[str, Field(pattern=r'^(?:BRR-)?[0-9]{1,14}$'), AfterValidator(positive)]
Reason = Annotated[str, Field(max_length=1000)]
Attribute = Literal['turnaround_time', 'communication', 'professionalism', 'work_quality', 'price']
Tag = Literal['good_repair_quality', 'good_van_condition', 'good_communication', 'good_pickup_return',
              'problem_repair_quality', 'problem_van_condition', 'problem_communication', 'problem_pickup_return']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @model_validator(mode='wrap')
    @classmethod
    def bilingual(cls, value, handler):
        try:
            return handler(value)
        except (ValidationError, ValueError):
            raise ValueError(INVALID) from None


class WorkRating(Input):
    work_order_id: WorkId = Field(description='Work order ID from the pending ratings list. / ID de la orden de trabajo de la lista de calificaciones pendientes.')
    vote: Literal['up'] = Field(default='up', description='Approve work with up; request correction with down. / Aprueba el trabajo con up; solicita una corrección con down.')
    completion_decision: Literal['approved'] = Field(default='approved', description='Approve the repair or request correction. / Aprueba la reparación o solicita una corrección.')
    reason: Reason | None = Field(default=None, description='Reason for the rating, at most 1000 characters. Required for correction. / Motivo de la calificación, máximo 1000 caracteres. Obligatorio para una corrección.')
    escalate: bool = Field(default=False, description='Count this rating toward the second-vendor trigger. This can open a SCORECARD_SECOND_VENDOR case for Nova platform staff. Get explicit user approval before setting true. Default: false. / Cuenta esta calificación para el criterio de un segundo proveedor. Puede abrir un caso SCORECARD_SECOND_VENDOR para el personal de la plataforma Nova. Obtén la aprobación explícita del usuario antes de usar true. Valor predeterminado: false.')
    impressive_attribute: Attribute | None = Field(default=None, description='Optional strong point: turnaround time, communication, professionalism, work quality or price. / Punto positivo opcional: plazo, comunicación, profesionalidad, calidad del trabajo o precio.')
    negative_attribute: Attribute | None = Field(default=None, description='Optional weak point: turnaround time, communication, professionalism, work quality or price. / Punto negativo opcional: plazo, comunicación, profesionalidad, calidad del trabajo o precio.')


class Correction(Input):
    work_order_id: WorkId = Field(description='Work order ID from the pending ratings list. / ID de la orden de trabajo de la lista de calificaciones pendientes.')
    vote: Literal['down'] = Field(default='down', description='Approve work with up; request correction with down. / Aprueba el trabajo con up; solicita una corrección con down.')
    completion_decision: Literal['correction_requested'] = Field(default='correction_requested', description='Approve the repair or request correction. / Aprueba la reparación o solicita una corrección.')
    reason: Reason = Field(description='Reason for the rating, at most 1000 characters. Required for correction. / Motivo de la calificación, máximo 1000 caracteres. Obligatorio para una corrección.')
    escalate: bool = Field(default=False, description='Count this rating toward the second-vendor trigger. This can open a SCORECARD_SECOND_VENDOR case for Nova platform staff. Get explicit user approval before setting true. Default: false. / Cuenta esta calificación para el criterio de un segundo proveedor. Puede abrir un caso SCORECARD_SECOND_VENDOR para el personal de la plataforma Nova. Obtén la aprobación explícita del usuario antes de usar true. Valor predeterminado: false.')
    impressive_attribute: Attribute | None = Field(default=None, description='Optional strong point: turnaround time, communication, professionalism, work quality or price. / Punto positivo opcional: plazo, comunicación, profesionalidad, calidad del trabajo o precio.')
    negative_attribute: Attribute | None = Field(default=None, description='Optional weak point: turnaround time, communication, professionalism, work quality or price. / Punto negativo opcional: plazo, comunicación, profesionalidad, calidad del trabajo o precio.')

    @model_validator(mode='after')
    def reason_required(self):
        if not self.reason.strip():
            raise ValueError(INVALID)
        return self


class BodyRating(Input):
    body_repair_request_id: BodyId = Field(description='Body repair ID from the pending ratings list. / ID de la reparación de carrocería de la lista de calificaciones pendientes.')
    stars: int = Field(ge=1, le=5, description='Rating from 1 to 5. Ratings of 1 or 2 open a case for Nova platform staff automatically. / Calificación de 1 a 5. Las calificaciones de 1 o 2 abren un caso para el personal de la plataforma Nova automáticamente.')
    tags: list[Tag] = Field(default_factory=list, description='Repair quality, van condition, communication or pickup/return tags. Use positive tags for 5 stars, either kind for 4, problem tags for 1 to 3. / Etiquetas de calidad de reparación, estado del van, comunicación o recogida/devolución. Usa etiquetas positivas con 5 estrellas, de ambos tipos con 4 y de problemas con 1 a 3.')
    reason: Reason | None = Field(default=None, description='Reason for the rating, at most 1000 characters. Required for correction. / Motivo de la calificación, máximo 1000 caracteres. Obligatorio para una corrección.')

    @model_validator(mode='after')
    def matching_tags(self):
        if len(self.tags) != len(set(self.tags)) or any(
            (self.stars == 5 and tag.startswith('problem_')) or
            (self.stars <= 3 and tag.startswith('good_')) for tag in self.tags
        ):
            raise ValueError(INVALID)
        return self


MODELS = {'rate_work_order': WorkRating, 'request_work_order_correction': Correction,
          'rate_body_repair': BodyRating}
WRITES = set(MODELS)
GRANTS = {name: 'vendor_scorecard.feedback.' + (
    'correction' if name == 'request_work_order_correction' else 'submit') + '.v1' for name in MODELS}
CONFIRM = ' Confirm the rating with the user before sending. / Confirma la calificación con el usuario antes de enviarla.'
DESCRIPTIONS = {
    'rate_work_order': 'Approve a repair from list_pending_vendor_feedback. Requires vendor_scorecard.feedback.submit.v1. / Aprueba una reparación de list_pending_vendor_feedback. Requiere vendor_scorecard.feedback.submit.v1.' + CONFIRM,
    'request_work_order_correction': 'Ask the shop to fix the work again. This reopens the work order or creates a correction work order. A reason and vendor_scorecard.feedback.correction.v1 permission are required. Confirm the rating and correction request with the user before sending. / Pide al taller que repare el trabajo de nuevo. Esto vuelve a abrir la orden de trabajo o crea una orden de corrección. Se requieren un motivo y el permiso vendor_scorecard.feedback.correction.v1. Confirma la calificación y la solicitud de corrección con el usuario antes de enviarlas.',
    'rate_body_repair': 'Rate a body repair from list_pending_vendor_feedback with 1 to 5 stars. Requires vendor_scorecard.feedback.submit.v1. Ratings of 1 or 2 stars escalate automatically. / Califica una reparación de carrocería de list_pending_vendor_feedback con 1 a 5 estrellas. Requiere vendor_scorecard.feedback.submit.v1. Las calificaciones de 1 o 2 estrellas se escalan automáticamente.' + CONFIRM,
}
for name in ('rate_work_order', 'request_work_order_correction'):
    DESCRIPTIONS[name] += ' ' + 'Count this rating toward the second-vendor trigger. This can open a SCORECARD_SECOND_VENDOR case for Nova platform staff. Get explicit user approval before setting true. Default: false. / Cuenta esta calificación para el criterio de un segundo proveedor. Puede abrir un caso SCORECARD_SECOND_VENDOR para el personal de la plataforma Nova. Obtén la aprobación explícita del usuario antes de usar true. Valor predeterminado: false.'
DESCRIPTIONS['rate_work_order'] += ' Optional fields: reason (up to 1000 characters), impressive_attribute (strong point), negative_attribute (weak point). / Campos opcionales: reason (máximo 1000 caracteres), impressive_attribute (punto positivo), negative_attribute (punto negativo).'
ERRORS = {
    400: 'Invalid rating choices. / Opciones de calificación no válidas.',
    401: 'Sign in again. / Inicia sesión de nuevo.',
    403: 'Rating denied. Check role, fleet, acting user, Station and connection permissions. Corrections need correction permission. / Calificación denegada. Comprueba el rol, la flota, el usuario vinculado, la Station y los permisos de conexión. Las correcciones requieren permiso de corrección.',
    404: 'Repair not found. / No se encontró la reparación.',
    409: 'Check repair completion, rating deadline and van custody. / Comprueba la finalización de la reparación, el plazo de calificación y la custodia del van.',
    422: INVALID,
    429: 'Wait before another attempt. / Espera antes de otro intento.',
    503: 'Body repair ratings are unavailable. / Las calificaciones de carrocería no están disponibles.',
}


class Receipt(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int = Field(gt=0)
    subject_kind: Literal['work_order', 'body_repair']
    work_order_id: int | None = Field(description='Work order ID from the pending ratings list. / ID de la orden de trabajo de la lista de calificaciones pendientes.')
    body_repair_request_id: int | None = Field(description='Body repair ID from the pending ratings list. / ID de la reparación de carrocería de la lista de calificaciones pendientes.')
    vote: str | None = Field(description='Approve work with up; request correction with down. / Aprueba el trabajo con up; solicita una corrección con down.')
    stars: int | None = Field(description='Rating from 1 to 5. Ratings of 1 or 2 open a case for Nova platform staff automatically. / Calificación de 1 a 5. Las calificaciones de 1 o 2 abren un caso para el personal de la plataforma Nova automáticamente.')
    tags: list[str] = Field(description='Repair quality, van condition, communication or pickup/return tags. Use positive tags for 5 stars, either kind for 4, problem tags for 1 to 3. / Etiquetas de calidad de reparación, estado del van, comunicación o recogida/devolución. Usa etiquetas positivas con 5 estrellas, de ambos tipos con 4 y de problemas con 1 a 3.')
    completion_decision: str = Field(description='Approve the repair or request correction. / Aprueba la reparación o solicita una corrección.')
    correction_reopened: bool


def validate_receipt(value, request):
    receipt = Receipt.model_validate(value)
    body = isinstance(request, BodyRating)
    reference = request.body_repair_request_id if body else request.work_order_id
    if (receipt.subject_kind != ('body_repair' if body else 'work_order') or
        (receipt.body_repair_request_id if body else receipt.work_order_id) != int(reference.split('-')[-1]) or
        (receipt.work_order_id if body else receipt.body_repair_request_id) is not None or
        receipt.completion_decision != ('not_applicable' if body else request.completion_decision) or
        (receipt.stars != request.stars or receipt.tags != request.tags or receipt.vote is not None
         if body else receipt.vote != request.vote)):
        raise ValueError(UNKNOWN)
    json.dumps(value, allow_nan=False)
    return value



def execute(client, name, arguments):
    request = MODELS[name].model_validate(arguments)
    try:
        value = client.request('POST', PATH, json_body=request.model_dump(exclude_none=True), retry_auth=False)
    except ApiError as exc:
        message = ERRORS.get(exc.status, UNKNOWN)
        raise ApiError(message, status=exc.status,
                       code='rating_rejected' if exc.status in ERRORS else 'outcome_unknown') from None
    try:
        return validate_receipt(value, request)
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code='outcome_unknown') from None


def command(args):
    from .legacy_reads import client_from_args

    name = args.rating_tool
    values = {key: getattr(args, key) for key in MODELS[name].model_fields if getattr(args, key, None) is not None}
    try:
        return execute(client_from_args(args), name, values)
    except ValidationError:
        raise UsageError(INVALID) from None


COMMANDS = []
for action, name in [('rate-work-order', 'rate_work_order'),
                     ('request-correction', 'request_work_order_correction'), ('rate-body-repair', 'rate_body_repair')]:
    arguments = []
    for key, field in MODELS[name].model_fields.items():
        if key in ('vote', 'completion_decision'):
            continue
        options = {'help': field.description}
        if not field.is_required():
            options['default'] = None
        if key == 'stars':
            options['type'] = 'int'
        if key == 'tags':
            options['action'] = 'append'
        if key == 'escalate':
            options['action'] = 'BooleanOptionalAction'
        if field.is_required() and not key.endswith('_id'):
            options['required'] = True
        arguments.append(([key if key.endswith('_id') else '--' + key.replace('_', '-')], options))
    COMMANDS.append({'command': 'vendor-scorecard ' + action, 'tool': name, 'grant': GRANTS[name],
        'scope': 'nova:read nova:write', 'effect': 'remote_write', 'description': DESCRIPTIONS[name],
        'arguments': arguments, 'groups': [], 'handler': command, 'defaults': {'rating_tool': name}})
