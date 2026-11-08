"""Customer recap report and consent-bound vendor referrals; no Admin operations."""
import json
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError
from nova_cli_public.inspection_confirmations import UNKNOWN, aware_datetime


class ReportQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dsp_id: Annotated[str, Field(pattern=r'^(?:DSP-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]


class ListQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    state: Literal['', 'submitted', 'under_review', 'invited', 'onboarding', 'completed', 'rejected', 'expired', 'revoked'] = ''


class Submit(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    shop_name: str = Field(min_length=1, max_length=160)
    contact_name: str = Field(min_length=1, max_length=160)
    contact_email: str = Field(min_length=3, max_length=320, pattern=r'^[^\s@]+@[^\s@]+$')
    repair_types: list[Literal['mechanical', 'body', 'tires', 'pm', 'cnmr', 'detailing', 'netradyne']] = Field(min_length=1, max_length=7)
    service_location: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=1000)
    language: Literal['en', 'es'] = 'en'
    contact_consent: Literal[True]


class Report(BaseModel):
    model_config = ConfigDict(strict=True)
    dsp_id: int = Field(ge=1)
    cutoff: Annotated[str, AfterValidator(aware_datetime)]
    as_of: Annotated[str, AfterValidator(aware_datetime)]
    findings: list[dict]
    inspected: int = Field(ge=0)
    incomplete: int = Field(ge=0)
    defects: int = Field(ge=0)
    critical: int = Field(ge=0)


class Referral(BaseModel):
    model_config = ConfigDict(strict=True)
    reference: str = Field(min_length=1, max_length=100)
    shop_name: str
    status: str


MODELS = {'get_first_inspection_recap_report': ReportQuery, 'list_vendor_referrals': ListQuery, 'submit_vendor_referral': Submit}
OUTPUTS = {'get_first_inspection_recap_report': Report, 'list_vendor_referrals': list[Referral], 'submit_vendor_referral': Referral}
WRITES = {'submit_vendor_referral'}


def run(args):
    name = args.recap_tool
    query = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields if getattr(args, key, None) is not None})
    report = isinstance(query, ReportQuery)
    path = f"/first-inspection-recaps/{int(query.dsp_id.split('-')[-1])}/report" if report else '/vendor-referrals'
    value = legacy_reads.client_from_args(args).request('POST' if name in WRITES else 'GET', path,
        **({'json_body': query.model_dump()} if name in WRITES else {'params': query.model_dump()} if not report else {}))
    try:
        from pydantic import TypeAdapter
        result = TypeAdapter(OUTPUTS[name]).validate_python(value)
        json.dumps(value, allow_nan=False)
        if report and result.dsp_id != int(query.dsp_id.split('-')[-1]):
            raise ValueError('Wrong DSP')
    except (ValueError, TypeError):
        raise ApiError(UNKNOWN, code='outcome_unknown') if name in WRITES else ApiError('Invalid response. / Respuesta no válida.') from None
    return value


COMMANDS = [
 {'command': 'inspection-recap report', 'tool': 'get_first_inspection_recap_report', 'grant': 'first_recaps.report.v1',
  'description': 'Read your scoped first platform recap. / Consulta tu resumen de plataforma con el alcance autorizado.',
  'arguments': [(['dsp_id'], {})], 'groups': [], 'handler': run, 'defaults': {'recap_tool': 'get_first_inspection_recap_report'}},
 {'command': 'vendor-referral list', 'tool': 'list_vendor_referrals', 'grant': 'vendor_referrals.list.v1',
  'description': 'List your vendor referrals. / Lista tus referencias de proveedores.',
  'arguments': [(['--limit'], {'type': 'int', 'default': 50}), (['--offset'], {'type': 'int', 'default': 0}), (['--state'], {'default': ''})],
  'groups': [], 'handler': run, 'defaults': {'recap_tool': 'list_vendor_referrals'}},
 {'command': 'vendor-referral submit', 'tool': 'submit_vendor_referral', 'grant': 'vendor_referrals.submit.v1',
  'description': 'Refer a vendor with contact consent. This does not scope a vendor or dispatch work. / Recomienda un proveedor con consentimiento de contacto. No asigna proveedores ni envía trabajo.',
  'arguments': [(['--' + key.replace('_', '-')], {'required': True}) for key in
   ('shop_name', 'contact_name', 'contact_email', 'service_location', 'reason')] + [
   (['--repair-types'], {'action': 'append', 'required': True}), (['--language'], {'default': 'en', 'choices': ['en', 'es']}),
   (['--contact-consent'], {'action': 'store_true', 'required': True})],
  'groups': [], 'handler': run, 'defaults': {'recap_tool': 'submit_vendor_referral'}, 'scope': 'nova:read nova:write', 'effect': 'remote_write'},
]
