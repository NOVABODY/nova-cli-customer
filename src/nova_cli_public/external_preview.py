"""Native external vendor discovery before a repair request exists."""
import json
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import DefectId, positive_reference
from nova_cli_public.errors import ApiError
from nova_cli_public.repair_requests import validate


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vehicle_id: Annotated[str, Field(pattern=r'^(?:VAN-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
    repair_type: str = Field(max_length=20)
    defect_id: DefectId | None = None
    service_station_code: str | None = Field(default=None, max_length=20)


MODELS = {'preview_repair_request_external_vendor_options': Preview}


def run(args):
    body = Preview.model_validate({key: getattr(args, key) for key in Preview.model_fields}).model_dump(exclude_none=True)
    value = legacy_reads.client_from_args(args).request('POST', '/repair-requests/external-vendor-options/prepare', json_body=body)
    validate('list_repair_request_external_vendor_options', value)
    try:
        if any(not isinstance(row, dict) for key in ('items', 'contacts', 'related_defects') for row in value[key]):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ApiError('Invalid repair options response. / Respuesta de opciones de reparación no válida.') from exc
    return value


COMMANDS = [{
    'command': 'repair-request preview-external-vendor-options', 'tool': 'preview_repair_request_external_vendor_options',
    'description': 'Read external repair provider options before a request exists. / Consulta opciones de proveedores de reparación externos antes de crear una solicitud.',
    'grant': 'repair_requests.external_vendor_options.preview.v1', 'scope': 'nova:read', 'effect': 'remote_read',
    'arguments': [(['--' + name.replace('_', '-')], {'required': field.is_required(), **({} if field.is_required() else {'default': field.default})})
                  for name, field in Preview.model_fields.items()],
    'groups': [], 'handler': run, 'defaults': {},
}]
