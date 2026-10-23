"""Typed customer reads using the existing delegated ApiClient."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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


class WorkOrderQuery(Arguments):
    status: str | None = None
    dsp_id: str | None = Field(default=None, pattern=r"^(?:[0-9]+|DSP-[0-9]+)$")
    vendor_workshop_id: str | None = Field(default=None, pattern=r"^(?:[0-9]+|VW-[0-9]+)$")
    vehicle_id: str | None = Field(default=None, pattern=r"^(?:[0-9]+|VAN-[0-9]+)$")
    assigned_to_me: bool = False
    scheduled_within_hours: int | None = Field(default=None, ge=1, le=720)
    scheduled_from_now: bool = False
    scheduled: bool | None = None
    has_confirmed_pickup: bool | None = None
    at_shop_custody: bool | None = None
    returned_within_hours: int | None = Field(default=None, ge=1, le=720)
    current_relationship_only: bool = False
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class WorkOrderGet(Arguments):
    work_order_id: str = Field(pattern=r"^(?:[0-9]+|WO-[0-9]+)$")


class WorkOrder(BaseModel):
    # The API filters all additional fields for the authenticated role.
    model_config = ConfigDict(strict=True, extra="allow")
    id: str
    status: str
    vehicle_id: int
    dsp_id: int
    vendor_workshop_id: int


class WorkOrderList(BaseModel):
    model_config = ConfigDict(strict=True)
    items: list[WorkOrder]
    total: int


class DefectQuery(Arguments):
    vehicle_id: str | None = Field(default=None, pattern=r"^(?:[0-9]+|VAN-[0-9]+)$")
    dsp_id: str | None = Field(default=None, pattern=r"^(?:[0-9]+|DSP-[0-9]+)$")
    inspection_id: str | None = Field(default=None, pattern=r"^(?:[0-9]+|INS-[0-9]+)$")
    source: str | None = None
    date_from: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    date_to: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    open_only: bool = False
    tz_offset_minutes: int = Field(default=0, ge=-840, le=840)
    include_no_shop: bool = False
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=200)

    @field_validator("date_from", "date_to")
    @classmethod
    def calendar_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value


class DefectGet(Arguments):
    defect_id: str = Field(pattern=r"^(?:[0-9]+|FD-[0-9]+)$")


class Defect(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    id: str
    vehicle_id: str
    fleet_id: str
    plate: str
    vehicle_class: str
    source: str
    part: str
    defect_type: str
    details: dict
    reported_at: str
    created_at: str
    updated_at: str


class DefectList(BaseModel):
    model_config = ConfigDict(strict=True)
    items: list[Defect]
    total: int
    page: int
    per_page: int


ARGUMENTS = {
    "list_vehicles": AssistantFleetQuery,
    "get_vehicle": FleetGet,
    "list_work_orders": WorkOrderQuery,
    "get_work_order": WorkOrderGet,
    "list_defects": DefectQuery,
    "get_defect": DefectGet,
}
OUTPUTS = {
    "list_vehicles": AssistantVehicleList,
    "get_vehicle": AssistantVehicle,
    "list_work_orders": WorkOrderList,
    "get_work_order": WorkOrder,
    "list_defects": DefectList,
    "get_defect": Defect,
}


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
        is_list = name.startswith("list_")
        resource, identifier = {
            "list_vehicles": ("vehicles", None),
            "get_vehicle": ("vehicles", "vehicle_id"),
            "list_work_orders": ("work-orders", None),
            "get_work_order": ("work-orders", "work_order_id"),
            "list_defects": ("defects", None),
            "get_defect": ("defects", "defect_id"),
        }[name]
        path = "/assistant/" + resource
        if identifier:
            path += "/" + getattr(query, identifier)
        value = self.client.request(
            "GET", path, query=query.model_dump(exclude_none=True) if is_list else {}
        )
        try:
            return OUTPUTS[name].model_validate(value).model_dump()
        except ValidationError:
            raise ResponseError("Invalid read response") from None
