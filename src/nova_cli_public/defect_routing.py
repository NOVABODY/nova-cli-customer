"""Shop selection and request routing use explicit operation consent."""
import json
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError

Reference = Annotated[str, Field(pattern=r'^(?:RR-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
VehicleId = Annotated[str, Field(pattern=r'^(?:VAN-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]


class Shops(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vehicle_id: VehicleId
    repair_type: Literal['mechanical', 'cnmr', 'pm', 'tires', 'detailing', 'netradyne', 'body']
    service_station_code: str | None = Field(default=None, max_length=20)


class Route(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    rr_id: Reference
    vendor_workshop_id: int = Field(ge=1, le=2147483647)
    mode: Literal['resume', 'reroute'] = 'resume'


MODELS = {'list_defect_routing_shops': Shops, 'route_repair_request': Route}


def run(args):
    name = args.routing_tool
    values = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields
        if hasattr(args, key)}).model_dump(exclude_none=True)
    client = legacy_reads.client_from_args(args)
    if name == 'list_defect_routing_shops':
        return client.request('GET', '/vendor-workshops', query=values)
    path = '/repair-requests/' + values.pop('rr_id') + '/route'
    value = client.request('POST', path, query={'mode': values.pop('mode')}, json_body=values)
    valid = isinstance(value, dict) and isinstance(value.get('work_order_ids'), list)
    try:
        valid = (valid and value['id'].startswith('RR-')
            and int(value['id'][3:]) == int(args.rr_id.split('-')[-1])
            and value.get('status') in ('open', 'accepted', 'cancelled', 'fulfilled', 'stale'))
        json.dumps(value, allow_nan=False)
    except (KeyError, ValueError, TypeError, AttributeError, RecursionError):
        valid = False
    if not valid:
        raise ApiError('The routing outcome is unknown. Read the request before another attempt. / El resultado de la asignación es desconocido. Consulta la solicitud antes de otro intento.', code='outcome_unknown')
    return value


COMMANDS = [
    {'command': 'defect-routing shops', 'tool': 'list_defect_routing_shops',
     'grant': 'vendor_workshops.list.v1', 'groups': [], 'handler': run,
     'description': 'Read shop eligibility for this van and repair type. / Consulta los talleres elegibles para esta van y este tipo de reparación.',
     'defaults': {'routing_tool': 'list_defect_routing_shops'},
     'arguments': [(['--vehicle-id'], {'required': True}), (['--repair-type'], {'required': True}),
                   (['--service-station-code'], {'default': None})]},
    {'command': 'defect-routing resume', 'tool': 'route_repair_request',
     'grant': 'repair_requests.route.v1', 'scope': 'nova:read nova:write', 'effect': 'remote_write',
     'groups': [], 'handler': run, 'defaults': {'routing_tool': 'route_repair_request'},
     'description': 'Route an open repair request to the selected eligible shop. / Asigna una solicitud de reparación abierta al taller elegible seleccionado.',
     'arguments': [(['rr_id'], {}), (['--vendor-workshop-id'], {'required': True, 'type': 'int'}),
                   (['--mode'], {'default': 'resume'})]},
]
