"""Two typed fleet reads using the existing delegated ApiClient."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nova_cli_public.errors import ApiError as ResponseError


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AssistantFleetQuery(Arguments):
    search: str | None = Field(default=None, max_length=200)
    fleet_id: str | None = Field(default=None, max_length=100)
    grounded: bool | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class FleetGet(Arguments):
    vehicle_id: str = Field(
        description="Vehicle ID from the fleet list. / ID del vehículo de la lista de la flota.",
        min_length=1,
        max_length=100,
        pattern=r"^(?:[0-9]+|VAN-[0-9]+)$",
    )


class AssistantVehicle(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    fleet_id: str
    vin: str
    plate: str
    make: str
    model: str
    year: int
    mileage: int
    grounded: bool
    is_active: bool


class AssistantVehicleList(BaseModel):
    model_config = ConfigDict(strict=True)
    items: list[AssistantVehicle]
    total: int
    page: int
    per_page: int


ARGUMENTS = {"list_vehicles": AssistantFleetQuery, "get_vehicle": FleetGet}
OUTPUTS = {"list_vehicles": AssistantVehicleList, "get_vehicle": AssistantVehicle}


class DelegatedService:
    def __init__(self, reader):
        self.client = reader

    def tool_schemas(self):
        return {name: model.model_json_schema() for name, model in ARGUMENTS.items()}

    def output_schema(self, name):
        return OUTPUTS[name].model_json_schema()

    def run(self, name, arguments):
        if name not in ARGUMENTS:
            raise ValueError("Unknown tool")
        query = ARGUMENTS[name].model_validate(arguments)
        is_list = name == "list_vehicles"
        path = "/assistant/vehicles" if is_list else "/assistant/vehicles/" + query.vehicle_id
        value = self.client.request(
            "GET", path, query=query.model_dump(exclude_none=True) if is_list else {}
        )
        try:
            return OUTPUTS[name].model_validate(value).model_dump()
        except ValidationError:
            raise ResponseError("Invalid fleet response") from None
