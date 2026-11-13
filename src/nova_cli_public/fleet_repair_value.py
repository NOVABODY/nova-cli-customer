"""Typed fleet repair planning read; the API owns scope and integer-cent totals."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

TOOL = 'get_fleet_repair_value_report'
PATH = '/dashboards/reports/vehicle-availability'
GRANT = 'reports.vehicle_availability.get.v1'
Text = Annotated[str, Field(max_length=200)]
Count = Annotated[int, Field(ge=0)]


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dsp_id: Annotated[str, Field(pattern=r'^[1-9][0-9]*$', max_length=10)] | None = None
    station_code: list[Text] | None = None
    vehicle_class: Text | None = None
    make: Text | None = None
    location: Text | None = None
    grounded: bool | None = None


class Value(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    low_cents: Count | None
    typical_cents: Count | None
    high_cents: Count | None
    defect_count: Count
    missing_count: Count


class DspValue(Value):
    dsp_name: str


class FleetValue(Value):
    dsps: list[DspValue]


class Van(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    fleet_id: str
    dsp_name: str
    repair_value: Value


class Report(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    repair_value: FleetValue
    vehicles: list[Van]


def query(arguments):
    return {**Filters.model_validate(arguments).model_dump(exclude_none=True), 'include_repair_value': True}
