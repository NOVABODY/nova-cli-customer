"""Report a problem through the same durable intake as the Nova app."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nova_cli_public.errors import ApiError

NAME = 'report_bug'
OPERATION = 'bug_reports.create.v1'
DESCRIPTION = ('Report a problem. Include only data you can share with Nova support. '
    'Use the same report ID and content to retry. / Informa de un problema. '
    'Incluye solo datos que puedas compartir con el soporte de Nova. '
    'Usa el mismo ID de informe y contenido para reintentar.')
UNKNOWN = ('The report outcome is unknown. Keep the report ID. Do not send a new report. / '
    'Se desconoce el resultado del informe. Conserva el ID del informe. No envíes un informe nuevo.')


class Report(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    note: str = Field(min_length=3, max_length=2000)
    report_id: str
    path: str | None = Field(default=None, max_length=200)
    view_id: str | None = Field(default=None, max_length=100)
    view_label: str | None = Field(default=None, max_length=100)
    display_mode: str | None = Field(default='mcp', max_length=20)
    viewport: str | None = Field(default=None, max_length=20)
    photos: list[Annotated[str, Field(max_length=4_000_000)]] = Field(default_factory=list, max_length=3)

    @field_validator('note', mode='before')
    @classmethod
    def strip_note(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('report_id')
    @classmethod
    def valid_id(cls, value):
        UUID(value)
        return value

    @model_validator(mode='after')
    def total_photos(self):
        if sum(map(len, self.photos)) > 6_000_000:
            raise ValueError('Photos are too large. / Las fotos son demasiado grandes.')
        return self


class Receipt(BaseModel):
    model_config = ConfigDict(strict=True)
    ok: Literal[True]
    duplicate: bool


MODELS = {NAME: Report}
WRITES = {NAME}
OUTPUTS = {NAME: Receipt}


def execute(client, arguments):
    report = Report.model_validate(arguments)
    try:
        value = client.request('POST', '/bug-reports', json_body=report.model_dump(exclude_none=True), retry_auth=False)
    except ApiError as exc:
        if exc.status is None or exc.status >= 500 or 300 <= exc.status < 400:
            raise ApiError(UNKNOWN, code='outcome_unknown', status=exc.status) from exc
        raise
    try:
        Receipt.model_validate(value)
    except ValueError:
        raise ApiError(UNKNOWN, code='outcome_unknown') from None
    return value


def run(args):
    from nova_cli_public.legacy_reads import client_from_args
    return execute(client_from_args(args), cli_arguments(args))


COMMANDS = [{'command': 'bug-report submit', 'tool': NAME, 'grant': OPERATION,
    'description': DESCRIPTION, 'scope': 'nova:read nova:write', 'effect': 'remote_write',
    'arguments': [(['--note'], {'required': True}), (['--report-id'], {'required': True})]
        + [(['--' + key.replace('_', '-')], {}) for key in
            ('path', 'view_id', 'view_label', 'display_mode', 'viewport')]
        + [(['--photo-file'], {'action': 'append', 'default': []})]
        + [(['--photo'], {'dest': 'photos', 'action': 'append', 'default': []})],
    'groups': [], 'handler': run}]


def cli_arguments(args):
    import base64
    from pathlib import Path

    from nova_cli_public.errors import UsageError

    values = {key: getattr(args, key) for key in Report.model_fields if getattr(args, key, None) is not None}
    photos = list(values.get('photos') or [])
    files = getattr(args, 'photo_file', None) or []
    if len(photos) + len(files) > 3:
        raise UsageError('Use at most three photos. / Usa un máximo de tres fotos.')
    for filename in files:
        source = Path(filename)
        content_type = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(source.suffix.lower())
        if content_type is None:
            raise UsageError('Use PNG, JPEG, or WebP. / Usa PNG, JPEG o WebP.')
        try:
            with source.open('rb') as stream:
                content = stream.read(3_000_001)
        except OSError as exc:
            raise UsageError('Cannot read the photo. / No se puede leer la foto.') from exc
        if len(content) > 3_000_000:
            raise UsageError('The photo is too large. / La foto es demasiado grande.')
        photos.append('data:' + content_type + ';base64,' + base64.b64encode(content).decode())
    values.setdefault('display_mode', 'cli')
    values['photos'] = photos
    return Report.model_validate(values).model_dump(exclude_none=True)
