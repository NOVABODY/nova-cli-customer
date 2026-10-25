"""Vehicle metadata uses the native API and explicit operation consent."""
import json
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from nova_cli_public import legacy_reads
from nova_cli_public.defect_reviews import positive_reference
from nova_cli_public.errors import UsageError

Positive = Annotated[int, Field(ge=1, le=2147483647)]


class Vin(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    vin: Annotated[str, Field(pattern=r"^[A-HJ-NPR-Z0-9]{17}$")]

    @field_validator("vin", mode="before")
    @classmethod
    def uppercase_vin(cls, value):
        return value.upper() if isinstance(value, str) else value


class Metadata(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dsp_id: Positive | Annotated[str, Field(max_length=100, pattern=r"^(?:DSP-)?[0-9]{1,14}$"), AfterValidator(positive_reference)] | None = None
    fleet_id: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    plate: Annotated[str, Field(min_length=1, max_length=20)] | None = None
    year: Annotated[int, Field(ge=1980, le=2100)] | None = None
    make: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    model: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    mileage: Annotated[int, Field(ge=0, le=2000000)] | None = None
    grounded: bool | None = None
    grounded_reason: Annotated[str, Field(max_length=500)] | None = None
    is_active: bool | None = None
    vehicle_class: Literal['custom_delivery_van', 'regular_cargo_van', 'step_van_dot', 'electric_vehicle', 'box_truck_dot'] | None = None
    ownership: Literal['amazon_owned', 'amazon_leased', 'dsp_owned', 'rental'] | None = None
    fmc: Annotated[str, Field(max_length=50)] | None = None
    raw_vehicle_provider: Annotated[str, Field(max_length=200)] | None = None
    rental_id: Annotated[str, Field(max_length=50)] | None = None
    assigned_location_id: Positive | None = None
    location: Literal['parking_lot', 'offsite', 'checked_out'] | None = None
    vin_override_reason: Annotated[str, Field(max_length=500)] | None = None
    expected_mileage: Annotated[int, Field(ge=0)] | None = None
    mileage_correction_reason: Annotated[str, Field(max_length=500)] | None = None

    @model_validator(mode='after')
    def require_data(self):
        if not self.model_fields_set:
            raise ValueError('Enter van data. / Introduce los datos del van.')
        return self


class Update(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    vehicle_id: Annotated[str, Field(max_length=100, pattern=r"^(?:VAN-)?[0-9]{1,14}$"), AfterValidator(positive_reference)]
    data: Metadata


class CreateData(Vin):
    dsp_id: Positive | Annotated[str, Field(max_length=100, pattern=r"^(?:DSP-)?[0-9]{1,14}$"), AfterValidator(positive_reference)] | None = None
    fleet_id: Annotated[str, Field(min_length=1, max_length=50)]
    plate: Annotated[str, Field(min_length=1, max_length=20)]
    year: Annotated[int, Field(ge=1980, le=2100)]
    make: Annotated[str, Field(min_length=1, max_length=50)]
    model: Annotated[str, Field(min_length=1, max_length=100)]
    mileage: Annotated[int, Field(ge=0, le=2000000)] | None = None
    vehicle_class: Literal['custom_delivery_van', 'regular_cargo_van', 'step_van_dot', 'electric_vehicle', 'box_truck_dot'] = 'regular_cargo_van'
    ownership: Literal['amazon_owned', 'amazon_leased', 'dsp_owned', 'rental'] = 'amazon_owned'
    fmc: Annotated[str, Field(max_length=50)] | None = None
    raw_vehicle_provider: Annotated[str, Field(max_length=200)] | None = None
    rental_id: Annotated[str, Field(max_length=50)] | None = None
    assigned_location_id: Positive | None = None


class Create(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    data: CreateData


MODELS = {"decode_vehicle_vin": Vin, "update_vehicle": Update, "create_vehicle": Create}


def run(args):
    if args.vehicle_tool == "decode_vehicle_vin":
        value = Vin.model_validate({"vin": args.vin})
        return legacy_reads.client_from_args(args).request("GET", "/vehicles/decode-vin/" + value.vin)
    data = args.data
    if isinstance(data, str):
        try:
            if len(data.encode()) > 65536:
                raise ValueError()
            data = json.loads(data)
        except ValueError as exc:
            raise UsageError("Use a JSON object of at most 64 KiB. / Usa un objeto JSON de 64 KiB como máximo.") from exc
    if args.vehicle_tool == "create_vehicle":
        value = Create.model_validate({"data": data})
        return legacy_reads.client_from_args(args).request("POST", "/vehicles",
            json_body=value.data.model_dump(exclude_unset=True))
    value = Update.model_validate({"vehicle_id": args.vehicle_id, "data": data})
    return legacy_reads.client_from_args(args).request("PATCH", "/vehicles/" + value.vehicle_id,
        json_body=value.data.model_dump(exclude_unset=True))


COMMANDS = [
    {"command": "vehicle create", "tool": "create_vehicle", "grant": "vehicles.create.v1",
     "scope": "nova:read nova:write", "effect": "remote_write",
     "arguments": [(["--data"], {"required": True, "help": "JSON object with van data. / Objeto JSON con los datos del van."})],
     "groups": [], "handler": run, "defaults": {"vehicle_tool": "create_vehicle"}},
    {"command": "vehicle decode-vin", "tool": "decode_vehicle_vin", "grant": "vehicles.decode_vin.v1",
     "arguments": [(["vin"], {})], "groups": [], "handler": run,
     "defaults": {"vehicle_tool": "decode_vehicle_vin"}},
    {"command": "vehicle update", "tool": "update_vehicle", "grant": "vehicles.update.v1",
     "scope": "nova:read nova:write", "effect": "remote_write",
     "arguments": [(["vehicle_id"], {}), (["--data"], {"required": True, "help": "JSON object with van data. / Objeto JSON con los datos del van."})],
     "groups": [], "handler": run, "defaults": {"vehicle_tool": "update_vehicle"}},
]
