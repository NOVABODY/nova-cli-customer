"""Native note ownership and authorization remain in the API."""
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference


class Note(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vehicle_id: Annotated[str, Field(max_length=100, pattern=r'^(?:VAN-)?[0-9]{1,14}$'), AfterValidator(positive_reference)]
    note_id: int = Field(ge=1, le=2147483647)

class Edit(Note):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator('body', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

MODELS = {'update_vehicle_note': Edit, 'delete_vehicle_note': Note}

def run(args):
    request = MODELS[args.note_tool].model_validate({name: getattr(args, name) for name in MODELS[args.note_tool].model_fields})
    endpoint = f'/vehicles/{request.vehicle_id}/notes/{request.note_id}'
    client = legacy_reads.client_from_args(args)
    if isinstance(request, Edit):
        return client.request('PATCH', endpoint, json_body={'body': request.body})
    return client.request('DELETE', endpoint)

COMMANDS = [
    {'command': 'vehicle ' + action, 'tool': tool, 'grant': 'vehicles.notes.' + operation + '.v1',
     'scope': 'nova:read nova:write', 'effect': 'remote_write',
     'arguments': [(['vehicle_id'], {}), (['note_id'], {'type': 'int'})] +
         ([(['--body'], {'required': True})] if operation == 'update' else []),
     'groups': [], 'handler': run, 'defaults': {'note_tool': tool}}
    for action, tool, operation in [('update-note', 'update_vehicle_note', 'update'), ('delete-note', 'delete_vehicle_note', 'delete')]
]
