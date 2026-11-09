"""Evidence adapters share validation and transport across CLI and MCP."""
import base64
import binascii
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nova_cli_public.errors import ApiError, UsageError

BASE = '/defect-bundle-offers/staff/evidence'
UNKNOWN = 'The outcome is unknown. Read the evidence before another attempt. / El resultado no se conoce. Consulta la evidencia antes de otro intento.'


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class File(Query):
    evidence_id: int = Field(ge=1)


class Review(File):
    decision: Literal['accepted', 'rejected']
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def rejection_note(self):
        if self.decision == 'rejected' and not self.note.strip():
            raise ValueError('Enter a note to reject the evidence. / Escribe una nota para rechazar la evidencia.')
        return self


class Upload(Query):
    ref: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,79}$')
    unit: int = Field(ge=1)
    kind: Literal['decline', 'pending', 'authorization']
    content_type: Literal['image/png', 'image/jpeg', 'image/webp', 'application/pdf']
    content_base64: str = Field(min_length=4, max_length=13981016)
    lines: list[int] = Field(default_factory=list, max_length=200)
    authorization_number: str = Field(default='', max_length=200)

    @model_validator(mode='after')
    def valid_upload(self):
        try:
            content = base64.b64decode(self.content_base64, validate=True)
        except binascii.Error:
            raise ValueError('Invalid file. / Archivo no válido.') from None
        if not content or len(content) > 10 * 1024 * 1024:
            raise ValueError('Invalid file size. / Tamaño de archivo no válido.')
        if self.kind == 'decline' and (not self.lines or any(number < 1 for number in self.lines)):
            raise ValueError('Select defects. / Selecciona defectos.')
        if self.kind == 'authorization' and not self.authorization_number.strip():
            raise ValueError('Enter the FMC authorization number. / Escribe el número de autorización de la FMC.')
        return self


MODELS = {'list_capacity_evidence': Query, 'get_capacity_evidence': File,
          'read_capacity_evidence_file': File, 'review_capacity_evidence': Review,
          'upload_capacity_evidence': Upload}
WRITES = {'review_capacity_evidence', 'upload_capacity_evidence'}


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    method, target, options = 'GET', BASE, {}
    if isinstance(query, File):
        target += f'/{query.evidence_id}'
    if name == 'read_capacity_evidence_file':
        target += '/content'
    if isinstance(query, Review):
        method, target = 'POST', target + '/review'
        options = {'json_body': {'decision': query.decision, 'note': query.note}, 'retry_auth': False}
    if isinstance(query, Upload):
        method, target = 'POST', f'/bundle-offers/{query.ref}/vans/{query.unit}/evidence-content'
        options = {'json_body': query.model_dump(exclude={'ref', 'unit'}), 'retry_auth': False}
    try:
        value = client.request(method, target, **options)
        valid = isinstance(value, dict)
        if name == 'list_capacity_evidence':
            valid = valid and isinstance(value.get('rows'), list)
        elif name == 'read_capacity_evidence_file':
            valid = valid and isinstance(value.get('content_base64'), str) and isinstance(value.get('content_type'), str)
        else:
            valid = valid and type(value.get('id')) is int and value.get('review_state') in ('unreviewed', 'accepted', 'rejected')
            if isinstance(query, Review):
                valid = valid and value['id'] == query.evidence_id and value['review_state'] == query.decision
        if not valid:
            raise ApiError('Invalid evidence response. / Respuesta de evidencia no válida.')
        json.dumps(value, allow_nan=False)
        if isinstance(query, Upload):
            from .bundle_shop_steps import refresh
            return refresh(client, query.ref, value)
        return value
    except (ApiError, ValueError, TypeError) as exc:
        if name in WRITES and (not isinstance(exc, ApiError) or exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        if isinstance(exc, ApiError) and isinstance(query, Upload):
            from .bundle_shop_steps import mapped_error
            raise mapped_error(exc) from exc
        raise


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.evidence_tool
    try:
        return execute(client_from_args(args), name, {key: getattr(args, key) for key in MODELS[name].model_fields})
    except ValidationError as exc:
        raise UsageError('Check evidence arguments. / Comprueba los argumentos de evidencia.') from exc



COMMANDS = []
for action, name, operation in [('list', 'list_capacity_evidence', 'list'), ('get', 'get_capacity_evidence', 'get'),
        ('file', 'read_capacity_evidence_file', 'content'), ('review', 'review_capacity_evidence', 'review'),
        ('upload', 'upload_capacity_evidence', 'upload')]:
    arguments = []
    for key, field in MODELS[name].model_fields.items():
        options = {'type': 'int'} if key in ('unit', 'evidence_id') else {}
        if key == 'lines':
            options = {'nargs': '+', 'type': 'int'}
        options['required'] = field.is_required()
        options['default'] = [] if key == 'lines' else field.default if not field.is_required() else None
        arguments.append((['--' + key.replace('_', '-')], options))
    COMMANDS.append({'command': 'capacity-evidence ' + action, 'tool': name,
        'grant': 'capacity.evidence.' + operation + '.v1',
        'description': ('Upload a file with kind=authorization and authorization_number to record FMC authorization; kind=pending records submission. Nova does not send it to the FMC. / Carga un archivo con kind=authorization y authorization_number para registrar autorización FMC; kind=pending registra el envío. Nova no lo envía a la FMC.' if name == 'upload_capacity_evidence' else 'Read or review FMC evidence. / Consulta o revisa la evidencia de la FMC.'),
        'arguments': arguments, 'groups': [], 'handler': command, 'defaults': {'evidence_tool': name},
        **({'scope': 'nova:read nova:write', 'effect': 'remote_write'} if name in WRITES else {})})
