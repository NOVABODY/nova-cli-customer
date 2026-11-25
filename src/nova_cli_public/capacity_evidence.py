"""Evidence adapters share validation and transport across CLI and MCP."""
import base64
import binascii
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nova_cli_public.errors import ApiError, NovaCliError, UsageError

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_BASE64_LENGTH = ((MAX_FILE_BYTES + 2) // 3) * 4
MAX_REQUEST_BODY_BYTES = MAX_BASE64_LENGTH + 256 * 1024 + 40

BASE = '/defect-bundle-offers/staff/evidence'
UNKNOWN = 'The outcome is unknown. Read the evidence before another attempt. / El resultado no se conoce. Consulta la evidencia antes de otro intento.'


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class File(Query):
    evidence_id: int = Field(ge=1)


class Content(File):
    file: int = Field(default=1, ge=1, le=10)


class Review(File):
    decision: Literal['accepted', 'rejected']
    note: str = Field(default='', max_length=2000)
    line: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def rejection_note(self):
        if self.decision == 'rejected' and not self.note.strip():
            raise ValueError('Enter a note to reject the evidence. / Escribe una nota para rechazar la evidencia.')
        return self


class Attachment(Query):
    content_type: Literal['image/png', 'image/jpeg', 'image/webp', 'application/pdf']
    content_base64: str = Field(min_length=4, max_length=MAX_BASE64_LENGTH)

    @model_validator(mode='after')
    def valid_file(self):
        try:
            content = base64.b64decode(self.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError('Invalid file. / Archivo no válido.') from None
        if not content or len(content) > MAX_FILE_BYTES:
            raise ValueError('Invalid file size. / Tamaño de archivo no válido.')
        return self


class Upload(Query):
    ref: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,79}$')
    unit: int = Field(ge=1)
    kind: Literal['decline', 'pending', 'authorization']
    content_type: Literal['image/png', 'image/jpeg', 'image/webp', 'application/pdf'] | None = None
    content_base64: str | None = Field(default=None, min_length=4, max_length=MAX_BASE64_LENGTH)
    attachments: list[Attachment] = Field(default_factory=list, max_length=9)
    reuse_evidence_id: int | None = Field(default=None, ge=1)
    lines: list[int] = Field(default_factory=list, max_length=200)
    authorization_number: str = Field(default='', max_length=200)

    @model_validator(mode='after')
    def valid_upload(self):
        if self.kind == 'decline' and (not self.lines or any(number < 1 for number in self.lines)):
            raise ValueError('Select defects. / Selecciona defectos.')
        if self.reuse_evidence_id is not None:
            if self.kind != 'decline' or self.content_type is not None or self.content_base64 is not None or self.attachments:
                raise ValueError('Reuse decline proof without new files. / Reutiliza evidencia de rechazo sin archivos nuevos.')
        else:
            Attachment.model_validate({'content_type': self.content_type, 'content_base64': self.content_base64})
            if self.attachments and self.kind != 'decline':
                raise ValueError('Only decline proof supports multiple files. / Solo la evidencia de rechazo admite varios archivos.')
        if self.content_base64 is not None:
            files = [self.content_base64, *(item.content_base64 for item in self.attachments)]
            total = sum(len(base64.b64decode(item, validate=True)) for item in files)
            if total > MAX_FILE_BYTES:
                raise ValueError('The combined files exceed 50 MiB. / Los archivos juntos superan 50 MiB.')
        if self.kind == 'authorization' and not self.authorization_number.strip():
            raise ValueError('Enter the FMC authorization number. / Escribe el número de autorización de la FMC.')
        return self


class RemovalPreview(Query):
    ref: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,79}$')
    unit: int = Field(ge=1)
    number: int = Field(ge=1)


class RemoveDefect(RemovalPreview):
    revision: str = Field(min_length=64, max_length=64)
    notice_version: Literal['amr-removal-v1']
    request_id: str = Field(min_length=1, max_length=100)


MODELS = {'list_capacity_evidence': Query, 'get_capacity_evidence': File,
          'read_capacity_evidence_file': Content, 'review_capacity_evidence': Review,
          'upload_capacity_evidence': Upload, 'preview_bundle_defect_removal': RemovalPreview, 'remove_bundle_defect': RemoveDefect}
WRITES = {'review_capacity_evidence', 'upload_capacity_evidence', 'remove_bundle_defect'}


def execute(client, name, arguments):
    query = MODELS[name].model_validate(arguments)
    method, target, options = 'GET', BASE, {}
    if isinstance(query, File):
        target += f'/{query.evidence_id}'
    if name == 'read_capacity_evidence_file':
        target += '/content'
        options = {'query': {'file': query.file}}
    if isinstance(query, Review):
        method, target = 'POST', target + '/review'
        options = {'json_body': query.model_dump(exclude={'evidence_id'}, exclude_none=True), 'retry_auth': False}
    if isinstance(query, Upload):
        method, target = 'POST', f'/bundle-offers/{query.ref}/vans/{query.unit}/evidence-content'
        options = {'json_body': query.model_dump(exclude={'ref', 'unit'}, exclude_none=True), 'retry_auth': False}
    if isinstance(query, RemovalPreview):
        target = f'/bundle-offers/{query.ref}/vans/{query.unit}/defects/{query.number}'
        target += '/remove' if isinstance(query, RemoveDefect) else '/removal-preview'
        if isinstance(query, RemoveDefect):
            method = 'POST'
            options = {'json_body': query.model_dump(exclude={'ref', 'unit', 'number'}), 'retry_auth': False}
    try:
        value = client.request(method, target, **options)
        valid = isinstance(value, dict)
        if isinstance(query, RemovalPreview):
            valid = valid and value.get('number') == query.number and (value.get('removed') is True if isinstance(query, RemoveDefect) else type(value.get('eligible')) is bool and isinstance(value.get('notice'), str))
        elif name == 'list_capacity_evidence':
            valid = valid and isinstance(value.get('rows'), list)
        elif name == 'read_capacity_evidence_file':
            valid = valid and isinstance(value.get('content_base64'), str) and isinstance(value.get('content_type'), str)
        else:
            valid = valid and type(value.get('id')) is int and value.get('review_state') in ('unreviewed', 'accepted', 'rejected')
            if isinstance(query, Review):
                valid = valid and value['id'] == query.evidence_id
                if query.line is None:
                    valid = valid and value['review_state'] == query.decision
                else:
                    valid = valid and type(value.get('reviewed_line')) is int and value.get('reviewed_line') == query.line and value.get('decision') == query.decision
        if not valid:
            raise ApiError('Invalid evidence response. / Respuesta de evidencia no válida.')
        json.dumps(value, allow_nan=False)
        if isinstance(query, Upload):
            from .bundle_shop_steps import refresh
            return refresh(client, query.ref, value)
        return value
    except (NovaCliError, ValueError, TypeError) as exc:
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
        arguments = {key: getattr(args, key) for key in MODELS[name].model_fields}
        if isinstance(arguments.get('attachments'), str):
            try:
                arguments['attachments'] = json.loads(arguments['attachments'])
            except (ValueError, TypeError):
                raise UsageError('Use a JSON array of files. / Usa una lista JSON de archivos.') from None
        return execute(client_from_args(args), name, arguments)
    except ValidationError as exc:
        raise UsageError('Check evidence arguments. / Comprueba los argumentos de evidencia.') from exc



COMMANDS = []
for action, name, operation in [('list', 'list_capacity_evidence', 'list'), ('get', 'get_capacity_evidence', 'get'),
        ('file', 'read_capacity_evidence_file', 'content'), ('review', 'review_capacity_evidence', 'review'),
        ('upload', 'upload_capacity_evidence', 'upload'),
        ('removal-preview', 'preview_bundle_defect_removal', 'capacity.defects.removal_preview.v1'),
        ('remove-defect', 'remove_bundle_defect', 'capacity.defects.remove.v1')]:
    arguments = []
    for key, field in MODELS[name].model_fields.items():
        options = {'type': 'int'} if key in ('unit', 'evidence_id', 'line', 'file', 'reuse_evidence_id', 'number') else {}
        if key == 'lines':
            options = {'nargs': '+', 'type': 'int'}
        options['required'] = field.is_required()
        options['default'] = [] if key in ('lines', 'attachments') else field.default if not field.is_required() else None
        arguments.append((['--' + key.replace('_', '-')], options))
    COMMANDS.append({'command': 'capacity-evidence ' + action, 'tool': name,
        'grant': operation if operation.startswith('capacity.') else 'capacity.evidence.' + operation + '.v1',
        'description': ('Preview removal and show its notice. Remove only after explicit confirmation using the preview revision and notice version. Do not repeat unknown writes. / Muestra la vista previa y el aviso. Retira solo tras confirmación explícita con la revisión y versión del aviso. No repitas escrituras desconocidas.' if isinstance(MODELS[name], type) and issubclass(MODELS[name], RemovalPreview) else 'Upload a file with kind=authorization and authorization_number to record FMC authorization; kind=pending records submission. Nova does not send it to the FMC. / Carga un archivo con kind=authorization y authorization_number para registrar autorización FMC; kind=pending registra el envío. Nova no lo envía a la FMC.' if name == 'upload_capacity_evidence' else 'Read or review FMC evidence. / Consulta o revisa la evidencia de la FMC.'),
        'arguments': arguments, 'groups': [], 'handler': command, 'defaults': {'evidence_tool': name},
        **({'scope': 'nova:read nova:write', 'effect': 'remote_write'} if name in WRITES else {})})
