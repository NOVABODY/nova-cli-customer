"""Shop intake uses defect references and the canonical API decisions."""
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ApiError, UsageError

DefectId = Annotated[str, Field(pattern=r'^(?:FD-)?[0-9]{1,14}$')]
ReasonCode = Literal['parts_unavailable', 'specialty_required', 'out_of_warranty', 'cost_too_high',
    'insufficient_information', 'shop_no_capability', 'illegitimate_defect',
    'already_completed_or_not_present', 'customer_declined', 'other']


class Accept(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    defect_id: DefectId
    ro_number: Annotated[str, Field(min_length=1, max_length=60)] | None = None


class Reject(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    defect_id: DefectId
    reject_reason_code: ReasonCode
    reason: Annotated[str, Field(max_length=500)] | None = None


MODELS = {'accept_defect': Accept, 'reject_defect': Reject}
DESCRIPTIONS = {
    'accept_defect': 'Accept one defect sent to your shop. Return its work order. / Acepta un defecto enviado a tu taller. Devuelve su orden de trabajo.',
    'reject_defect': 'Reject one defect sent to your shop. Keep other defects unchanged. / Rechaza un defecto enviado a tu taller. Conserva los otros defectos sin cambios.',
}
UNKNOWN = 'Read the defect before another attempt. / Consulta el defecto antes de otro intento.'


def execute(client, name, arguments):
    values = MODELS[name].model_validate(arguments).model_dump(exclude_none=True)
    reference = values.pop('defect_id')
    if int(reference.split('-')[-1]) < 1:
        raise UsageError('Use a positive defect reference. / Usa una referencia de defecto positiva.')
    action = 'accept' if name == 'accept_defect' else 'reject'
    try:
        result = client.request('POST', '/defects/' + reference + '/' + action,
            json_body=values, retry_auth=False)
    except ApiError as exc:
        if exc.status is None or exc.status >= 500 or 300 <= exc.status < 400:
            raise ApiError(UNKNOWN, code='outcome_unknown') from exc
        raise
    valid = isinstance(result, dict)
    if valid and action == 'accept':
        valid = isinstance(result.get('id'), str) and re.fullmatch(r'WO-[0-9]{1,14}', result['id']) and result.get('status') == 'processing'
    elif valid:
        valid = result.get('rejected_defect_ids') == [int(reference.split('-')[-1])]
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ApiError(UNKNOWN, code='outcome_unknown')
    return result


def command(args):
    from .cli import client_from_args

    name = args.shop_tool
    try:
        return execute(args._client if hasattr(args, '_client') else client_from_args(args), name,
            {key: getattr(args, key) for key in MODELS[name].model_fields if hasattr(args, key)})
    except ValidationError as exc:
        raise UsageError('Check the defect and reason. / Comprueba el defecto y el motivo.') from exc
