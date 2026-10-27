"""Native review adapters; authorization and routing remain in the API."""
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nova_cli_public import legacy_reads


def positive_reference(value):
    if not 1 <= int(value.rsplit("-", 1)[-1]) <= 2147483647:
        raise ValueError("Use a positive record ID. / Usa un ID de registro positivo.")
    return value


DefectId = Annotated[str, Field(max_length=100, pattern=r"^(?:FD-)?[0-9]{1,14}$"), AfterValidator(positive_reference)]


class Queue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dsp_id: Annotated[str, Field(max_length=100, pattern=r"^(?:DSP-)?[0-9]{1,14}$"), AfterValidator(positive_reference)] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class History(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    defect_id: DefectId


class Decision(History):
    reason: str | None = Field(default=None, max_length=500)
    is_rush: bool | None = None
    is_critical: bool | None = None
    key_location: str | None = Field(default=None, max_length=80)
    vendor_workshop_id: int | None = None
    external_vendor_id: int | None = Field(default=None, gt=0)
    additional_defect_ids: list[DefectId] | None = Field(default=None, max_length=100)
    dsp_contact_user_id: int | None = Field(default=None, gt=0)
    override_eligibility: bool | None = None
    accept_dsp_responsibility: bool | None = None
    service_station_code: str | None = Field(default=None, max_length=20)
    reject_reason_code: str | None = Field(default=None, max_length=40)


MODELS = {
    "list_defect_review_queue": Queue,
    "list_defect_reviews": History,
    "approve_defect_review": Decision,
    "reject_defect_review": Decision,
}


def run(args):
    values = MODELS[args.review_tool].model_validate({
        key: getattr(args, key) for key in MODELS[args.review_tool].model_fields
        if hasattr(args, key)
    }).model_dump(exclude_none=True)
    client = legacy_reads.client_from_args(args)
    if args.review_tool == "list_defect_review_queue":
        return client.request("GET", "/defect-reviews/queue", query=values)
    path = "/defect-reviews/defect/" + values.pop("defect_id")
    if args.review_tool == "list_defect_reviews":
        return client.request("GET", path)
    return client.request("POST", path + "/" + args.review_action, json_body=values)


COMMANDS = []
for action, tool, grant, model in [
    ("queue", "list_defect_review_queue", "queue.list", Queue),
    ("history", "list_defect_reviews", "list", History),
    ("approve", "approve_defect_review", "approve", Decision),
    ("reject", "reject_defect_review", "reject", Decision),
]:
    arguments = []
    for name, field in model.model_fields.items():
        options = {}
        if name in ("limit", "offset", "vendor_workshop_id", "external_vendor_id", "dsp_contact_user_id"):
            options["type"] = "int"
        if name in ("is_rush", "is_critical", "override_eligibility", "accept_dsp_responsibility"):
            options["action"] = "BooleanOptionalAction"
        if name == "additional_defect_ids":
            options["action"] = "append"
        if not field.is_required():
            options["default"] = field.default
        arguments.append(([name if field.is_required() else "--" + name.replace("_", "-")], options))
    COMMANDS.append({
        "command": "defect-review " + action, "tool": tool,
        "grant": "defect_reviews." + grant + ".v1", "arguments": arguments,
        "groups": [], "handler": run,
        "defaults": {"review_tool": tool, "review_action": action},
        **({"scope": "nova:read nova:write", "effect": "remote_write"}
           if action in ("approve", "reject") else {}),
    })
