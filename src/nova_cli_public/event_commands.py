"""Customer workshop event commands and bounded MCP argument contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nova_cli_public import events, legacy_reads


class EventHead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    vendor_workshop_id: int = Field(gt=0)


class EventInit(EventHead):
    after: str = Field(min_length=1)
    snapshot_reconciled: Literal[True]
    reset: bool = False

    @field_validator("snapshot_reconciled", mode="before")
    @classmethod
    def require_reconciliation(cls, value):
        if value is not True:
            raise ValueError("Snapshot reconciliation must be explicitly true.")
        return value


class EventWatch(EventHead):
    limit: int = Field(default=100, ge=1, le=500)
    max_pending: int = Field(default=1000, ge=1, le=1000)
    wait_seconds: int = Field(default=0, ge=0, le=25)


class EventAck(EventHead):
    cursor: str = Field(min_length=1)


EVENT_MODELS = {
    "events_head": EventHead,
    "events_init": EventInit,
    "events_watch": EventWatch,
    "events_ack": EventAck,
}
EVENT_LOCAL_TOOLS = {"events_init", "events_watch", "events_ack"}


def _run(args):
    return events.run_events(args, legacy_reads.client_from_args(args))


def _command(name, arguments):
    return {
        "command": "events " + name,
        "tool": "events_" + name,
        "grant": "workshop_events.list.v1",
        "arguments": [(["--vendor-workshop-id"], {"type": "int", "required": True})]
        + ([] if name == "head" else [(["--state-file"], {"required": True})])
        + arguments,
        "groups": [],
        "handler": _run,
        "defaults": {"events_command": name},
    }


EVENT_COMMANDS = [
    _command("head", []),
    _command(
        "init",
        [
            (["--after"], {"required": True}),
            (["--snapshot-reconciled"], {"action": "store_true", "required": True}),
            (["--reset"], {"action": "store_true"}),
        ],
    ),
    _command(
        "watch",
        [
            (["--once"], {"action": "store_true"}),
            (["--limit"], {"type": "int", "default": 100}),
            (["--max-pending"], {"type": "int", "default": 10000}),
        ],
    ),
    _command("ack", [(["cursor"], {})]),
]
