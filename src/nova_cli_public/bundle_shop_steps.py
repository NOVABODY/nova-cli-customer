"""Bought-bundle shop steps with no purchase, readiness or payment routes."""
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from nova_cli_public import bundle_workflow
from nova_cli_public.errors import ApiError, NovaCliError, UsageError

PDF = 'get_bundle_fmc_packet_pdf'
PICKUP = 'update_bundle_pickup'
NO_CHARGE = 'confirm_bundle_no_charge'
CONTACT = 'request_bundle_contact'
UNKNOWN = 'The outcome is unknown. Read the vans before another attempt. / El resultado no se conoce. Consulta las vans antes de otro intento.'
BROWSER = 'Open browser_url to buy, set initial pickup or change payment. / Abre browser_url para comprar, programar la recogida inicial o cambiar el pago.'
GUIDANCE = {
    401: 'Connect again. / Conecta de nuevo.',
    403: 'Check consent, policy and account permissions. / Comprueba el consentimiento, la política y los permisos de la cuenta.',
    404: 'This bundle or van is not available for your shop role. / Este paquete o van no está disponible para tu rol del taller.',
    409: 'Read the vans for the current price, deadline and step. ' + BROWSER + ' / Consulta las vans para ver el precio, el plazo y el paso actual.',
    413: 'Use a smaller evidence file. / Usa un archivo de evidencia más pequeño.',
    422: 'Check the fields, file and date window. / Comprueba los campos, el archivo y el horario.',
}


class Van(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ref: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,79}$')
    unit: int = Field(ge=1)


class Pickup(Van):
    start: AwareDatetime = Field(strict=False)
    end: AwareDatetime = Field(strict=False)
    estimated_return_date: date | None = Field(default=None, strict=False)

    @field_validator('start', 'end', mode='before')
    @classmethod
    def iso_timestamp(cls, value):
        if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}T', value):
            raise ValueError('Use an ISO 8601 time with a UTC offset. / Usa una hora ISO 8601 con zona horaria.')
        return value

    @field_validator('estimated_return_date', mode='before')
    @classmethod
    def calendar_date(cls, value):
        if value is not None and type(value) is not date and (not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)):
            raise ValueError('Use a date: YYYY-MM-DD. / Usa una fecha: YYYY-MM-DD.')
        return value

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('End must follow start. / El fin debe ser posterior al inicio.')
        return self


class Receipt(BaseModel):
    model_config = ConfigDict(extra='allow')
    vans: list[bundle_workflow.Van] | None = None
    refresh_required: bool = False


class PickupReceipt(Receipt):
    tasks: list[dict]


class NoChargeReceipt(Receipt):
    state: Literal['lapsed']


class ContactReceipt(Receipt):
    status: Literal['requested', 'already_requested']


MODELS = {PDF: Van, PICKUP: Pickup, NO_CHARGE: Van, CONTACT: Van}
OUTPUTS = {PICKUP: PickupReceipt, NO_CHARGE: NoChargeReceipt, CONTACT: ContactReceipt}
WRITES = {PICKUP, NO_CHARGE, CONTACT}
SUFFIXES = {PDF: 'fmc.pdf', PICKUP: 'pickup', NO_CHARGE: 'confirm-no-charge', CONTACT: 'contact'}
DESCRIPTIONS = {
    PDF: 'Download the FMC packet. Nova does not send it to the FMC. Use upload_capacity_evidence with kind=pending after submission, or kind=authorization with authorization_number and a file. / Descarga el paquete FMC. Nova no lo envía a la FMC. Usa upload_capacity_evidence con kind=pending tras enviarlo, o kind=authorization con authorization_number y un archivo.',
    PICKUP: 'Change pickup dates, or book transport for a paid or waived van. Initial readiness stays in the browser. DSP approval and live API rules apply. / Cambia las fechas de recogida o programa transporte para una van pagada o exenta. La preparación inicial se hace en el navegador. Se aplican la aprobación del DSP y las reglas de la API.',
    NO_CHARGE: 'Confirm a zero-price exit with reviewed declines. No payment is made. / Confirma una salida sin cobro con rechazos revisados. No se hace ningún pago.',
    CONTACT: 'Request Nova contact for a lapsed van with debt. Report requested or already_requested. No debt is paid. / Solicita contacto de Nova para una van vencida con deuda. Indica requested o already_requested. No se paga ninguna deuda.',
}


def mapped_error(exc):
    if exc.status not in GUIDANCE:
        return exc
    return ApiError(str(exc) + ' ' + json.dumps(exc.detail, ensure_ascii=False) + ' ' + GUIDANCE[exc.status],
        status=exc.status, code=exc.code, detail=exc.detail, request_id=exc.request_id)


def execute(client, name, arguments, *, pdf_max_bytes=1024 * 1024):
    # JSON mode accepts ISO dates while retaining strict reference and unit checks.
    query = MODELS[name].model_validate_json(json.dumps(arguments))
    path = f'/bundle-offers/{query.ref}/vans/{query.unit}/{SUFFIXES[name]}'
    try:
        if name == PDF:
            return client.request('GET', path, pdf=True, pdf_max_bytes=pdf_max_bytes)
        options = {'retry_auth': False}
        if name == PICKUP:
            options['json_body'] = query.model_dump(mode='json', exclude={'ref', 'unit'}, exclude_none=True)
        value = client.request('POST', path, **options)
    except ApiError as exc:
        if name in WRITES and (exc.status is None or exc.status >= 500 or 300 <= exc.status < 400):
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise mapped_error(exc) from exc
    try:
        OUTPUTS[name].model_validate(value)
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ApiError(UNKNOWN, code='outcome_unknown') from None
    return refresh(client, query.ref, value)


def refresh(client, ref, value):
    value = bundle_workflow.safe_browser_urls(value, bundle_workflow.web_origin(client), ref)
    try:
        refreshed = bundle_workflow.execute(client, 'list_bought_bundle_vans', {'ref': ref})
        return {**value, **refreshed}
    except NovaCliError:
        return {**value, 'refresh_required': True, 'message': 'The step succeeded. Could not refresh. Read the vans before another step. / El paso se completó. No se pudo actualizar. Consulta las vans antes de otro paso.'}


def command(args):
    from nova_cli_public.legacy_reads import client_from_args
    name = args.bundle_shop_tool
    arguments = {key: getattr(args, key) for key in MODELS[name].model_fields}
    destination = None
    if name == PDF:
        destination = Path(args.out).expanduser().absolute()
        if os.path.lexists(destination):
            raise UsageError('The output file exists. / El archivo de salida ya existe.')
    try:
        result = execute(client_from_args(args), name, arguments, pdf_max_bytes=10 * 1024 * 1024)
    except ValidationError as exc:
        raise UsageError('Check the van and dates. / Comprueba la van y las fechas.') from exc
    if name == PDF:
        from nova_cli_public.body_documents import publish
        return {**publish(result, destination, 'application/pdf'), 'message': DESCRIPTIONS[PDF]}
    return result


COMMANDS = []
for action, name, grant in [('fmc-pdf', PDF, 'capacity.fmc_packet.get.v1'),
        ('pickup', PICKUP, 'capacity.pickup.update.v1'),
        ('confirm-no-charge', NO_CHARGE, 'capacity.no_charge.confirm.v1'),
        ('contact', CONTACT, 'capacity.contact.create.v1')]:
    arguments = [(['ref'], {}), (['unit'], {'type': 'int'})]
    if name == PDF:
        arguments += [(['--out'], {'required': True})]
    if name == PICKUP:
        arguments += [(['--start'], {'required': True}), (['--end'], {'required': True}), (['--estimated-return-date'], {})]
    COMMANDS.append({'command': 'bundle-shop ' + action, 'tool': name, 'grant': grant,
        'description': DESCRIPTIONS[name], 'arguments': arguments, 'groups': [],
        'handler': command, 'defaults': {'bundle_shop_tool': name},
        **({'scope': 'nova:read nova:write', 'effect': 'remote_write'} if name in WRITES else {})})

