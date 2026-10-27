"""Set defect cost through the native API without retrying uncertain writes."""
import json
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import DefectId
from nova_cli_public.errors import ApiError


class Cost(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    defect_id: DefectId
    estimated_cost: Annotated[str, Field(min_length=1, max_length=100)]

    @field_validator('estimated_cost')
    @classmethod
    def valid_amount(cls, value):
        try:
            amount = Decimal(value)
            if not amount.is_finite() or not 0 < amount <= Decimal('999999.99'):
                raise ValueError()
        except (InvalidOperation, ValueError) as exc:
            raise ValueError('Enter a cost greater than zero and at most 999999.99. / Introduce un costo mayor que cero y de 999999.99 como máximo.') from exc
        return value


MODELS = {'set_defect_cost': Cost}


def run(args):
    request = Cost.model_validate({'defect_id': args.defect_id, 'estimated_cost': args.estimated_cost})
    value = legacy_reads.client_from_args(args).request('POST', '/defects/' + request.defect_id + '/cost',
        json_body={'estimated_cost': request.estimated_cost})
    try:
        if (not isinstance(value, dict) or type(value.get('defect_id')) is not int
                or value['defect_id'] != int(request.defect_id.split('-')[-1])
                or type(value.get('auto_approved')) is not bool
                or type(value.get('estimated_cost')) not in (str, int, float)):
            raise ValueError()
        amount = Decimal(str(value['estimated_cost']))
        if not amount.is_finite() or amount < 0:
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ApiError('The change outcome is unknown. Check the record before trying again. / El resultado del cambio es desconocido. Revisa el registro antes de intentarlo de nuevo.', code='outcome_unknown') from exc
    return value


COMMANDS = [{
    'command': 'defect set-cost', 'tool': 'set_defect_cost', 'grant': 'defects.cost.set.v1',
    'scope': 'nova:read nova:write', 'effect': 'remote_write',
    'arguments': [(['defect_id'], {}), (['--estimated-cost'], {'required': True})],
    'groups': [], 'handler': run, 'defaults': {},
}]
