"""Native fleet/rental catalog and scoped vehicle company choice."""
import json
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import ApiError


class Catalog(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    active_only: bool = True


class Assignment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vehicle_id: Annotated[str, Field(pattern=r'^(?:VAN-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
    company_id: Annotated[int, Field(ge=1)] | Annotated[str, Field(pattern=r'^(?:FMC-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]


MODELS = {'list_fmc_companies': Catalog, 'set_vehicle_fmc_company': Assignment}


def reference(value, prefix):
    return isinstance(value, str) and value.startswith(prefix) and value[len(prefix):].isdigit() and int(value[len(prefix):]) > 0


def run(args):
    tool = args.fmc_tool
    body = MODELS[tool].model_validate({key: getattr(args, key) for key in MODELS[tool].model_fields})
    api = legacy_reads.client_from_args(args)
    writing = tool == 'set_vehicle_fmc_company'
    value = (api.request('PUT', '/vehicles/' + body.vehicle_id + '/fmc-company', json_body={'company_id': body.company_id})
        if writing else api.request('GET', '/fmc-companies', query={} if body.active_only else {'active_only': 'false'}))
    try:
        if writing:
            if (not isinstance(value, dict) or not reference(value.get('id'), 'VAN-')
                    or int(value['id'][4:]) != int(body.vehicle_id.split('-')[-1])
                    or not reference(value.get('fmc_company_id'), 'FMC-')
                    or int(value['fmc_company_id'][4:]) != int(str(body.company_id).split('-')[-1])):
                raise ValueError()
        elif not isinstance(value, list) or any(not isinstance(row, dict) or not reference(row.get('id'), 'FMC-')
                or not isinstance(row.get('name'), str) or type(row.get('is_active')) is not bool for row in value):
            raise ValueError()
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        if writing:
            raise ApiError('The company assignment outcome is unknown. Read the van before another attempt. / El resultado de la asignación de empresa es desconocido. Consulta el van antes de otro intento.', code='outcome_unknown') from exc
        raise ApiError('Invalid fleet company response. / Respuesta de empresas de flotas no válida.') from exc
    return value


COMMANDS = [
    {'command': 'fmc-company list', 'tool': 'list_fmc_companies', 'grant': 'fmc_companies.list.v1',
     'description': 'Read fleet and rental companies. / Consulta empresas de flotas y alquiler.',
     'arguments': [(['--include-inactive'], {'action': 'store_false', 'dest': 'active_only', 'default': True})],
     'groups': [], 'handler': run, 'defaults': {'fmc_tool': 'list_fmc_companies'}},
    {'command': 'vehicle set-fmc-company', 'tool': 'set_vehicle_fmc_company', 'grant': 'vehicles.fmc_company.update.v1',
     'scope': 'nova:read nova:write', 'effect': 'remote_write',
     'description': 'Set the fleet or rental company for a van. / Configura la empresa de flota o alquiler para un van.',
     'arguments': [(['vehicle_id'], {}), (['--company-id'], {'required': True})],
     'groups': [], 'handler': run, 'defaults': {'fmc_tool': 'set_vehicle_fmc_company'}},
]
