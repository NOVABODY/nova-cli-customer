"""Durable customer event delivery, connection isolation, and bounded tool calls."""

import json
import sqlite3

import pytest
from pydantic import ValidationError

from nova_cli_public import cli, events
from nova_cli_public.capabilities import manifest
from nova_cli_public.config import Profile
from nova_cli_public.errors import ApiError, UsageError
from nova_cli_public.events import EventInbox
from nova_cli_public.reads import CustomerReadService

ITEM = {
    "event": "work_order.changed",
    "cursor": "event-1",
    "work_order_id": "WO-1",
    "defect_id": None,
    "occurred_at": "2026-10-23T12:00:00Z",
}
PAGE = {"items": [ITEM], "next_cursor": "event-1", "has_more": False}
HEAD = {"items": [], "next_cursor": "head", "has_more": False}
EMPTY = {"items": [], "next_cursor": "event-1", "has_more": False}


class Client:
    profile = Profile("test", "https://nova.example/api")

    def __init__(self):
        self.identity = ("https://nova.example", "1", "tenant-1", "grant-1")
        self.requests = []
        self.pages = []
        self.head_error = None
        self.change_after_read = False
        self.rotations = 0

    def refresh(self):
        self.rotations += 1

    def connection_identity(self):
        return self.identity

    def request(self, method, path, *, query):
        self.requests.append((method, path, query))
        if "after" not in query:
            if self.head_error:
                raise self.head_error
            return HEAD
        value = self.pages.pop(0) if self.pages else HEAD
        if isinstance(value, BaseException):
            raise value
        if self.change_after_read:
            self.identity = (*self.identity[:3], "new-grant")
        return value


def setup_cli(monkeypatch, tmp_path):
    client = Client()
    monkeypatch.setattr(cli, "client_from_args", lambda args: client)
    common = ["--vendor-workshop-id", "3", "--state-file", str(tmp_path / "inbox"), "--json"]
    assert cli.main(["events", "init", "--after", "head", "--snapshot-reconciled", *common]) == 0
    return client, common


def state(path):
    with sqlite3.connect(path) as db:
        return (
            db.execute("SELECT value FROM state WHERE key='cursor'").fetchone()[0],
            db.execute("SELECT count(*) FROM events WHERE acked=0").fetchone()[0],
        )


def test_accept_replay_ack_and_reset_are_explicit(tmp_path):
    path = tmp_path / "inbox"
    inbox = EventInbox(path, "identity")
    inbox.initialize("head")
    assert inbox.accept(PAGE) == [ITEM]
    inbox.close()
    inbox = EventInbox(path, "identity")
    assert inbox.pending() == [ITEM]
    assert inbox.accept(PAGE) == []
    with pytest.raises(UsageError, match="acknowledge pending"):
        inbox.initialize("reset", reset=True)
    inbox.acknowledge("event-1")
    inbox.acknowledge("event-1")
    with pytest.raises(UsageError, match="not a durably accepted"):
        inbox.acknowledge("unknown")
    with pytest.raises(UsageError, match="--reset"):
        inbox.initialize("reset")
    inbox.initialize("reset", reset=True)
    assert inbox.get("cursor") == "reset"
    inbox.close()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(UsageError, match="another API"):
        EventInbox(path, "different identity")


def test_failed_transaction_cannot_advance_or_accept(tmp_path):
    inbox = EventInbox(tmp_path / "inbox", "identity")
    inbox.initialize("head")
    inbox.db.execute(
        "CREATE TRIGGER fail_cursor BEFORE INSERT ON state WHEN NEW.key='cursor' "
        "BEGIN SELECT RAISE(ABORT, 'disk failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        inbox.accept(PAGE)
    assert inbox.get("cursor") == "head"
    assert inbox.pending() == []
    inbox.close()


@pytest.mark.parametrize(
    "page",
    [
        None,
        {},
        {"items": []},
        {"items": [], "next_cursor": "lost", "has_more": True},
        {"items": [{**ITEM, "event": "heartbeat"}], "next_cursor": "lost", "has_more": False},
    ],
)
def test_invalid_page_does_not_advance(tmp_path, page):
    inbox = EventInbox(tmp_path / "inbox", "identity")
    inbox.initialize("head")
    with pytest.raises(ApiError):
        inbox.accept(page)
    assert inbox.get("cursor") == "head"
    assert inbox.pending() == []
    inbox.close()


def test_changed_duplicate_rolls_back(tmp_path):
    inbox = EventInbox(tmp_path / "inbox", "identity")
    inbox.initialize("head")
    inbox.accept(PAGE)
    with pytest.raises(ApiError, match="changed payload"):
        inbox.accept(
            {**PAGE, "items": [{**ITEM, "work_order_id": "WO-OTHER"}], "next_cursor": "later"}
        )
    assert inbox.get("cursor") == "event-1"
    assert inbox.pending() == [ITEM]
    inbox.close()


def test_two_watchers_cannot_race(tmp_path):
    first, second = [EventInbox(tmp_path / "inbox", "identity") for _ in range(2)]
    with first.watcher(), pytest.raises(UsageError, match="Another watcher"), second.watcher():
        pytest.fail("second watcher admitted")
    first.close()
    second.close()


def test_cli_replays_after_refresh_and_requires_ack(monkeypatch, tmp_path, capsys):
    client, common = setup_cli(monkeypatch, tmp_path)
    capsys.readouterr()
    client.pages = [PAGE, EMPTY, EMPTY]
    for _ in range(2):
        assert cli.main(["events", "watch", "--once", *common]) == 0
        assert json.loads(capsys.readouterr().out) == ITEM
    assert client.rotations == 3
    assert cli.main(["events", "ack", "event-1", *common]) == 0
    capsys.readouterr()
    assert cli.main(["events", "watch", "--once", *common]) == 0
    assert capsys.readouterr().out == ""
    assert client.requests[-1][2]["after"] == "event-1"


def test_output_failure_leaves_event_durable(monkeypatch, tmp_path, capsys):
    client, common = setup_cli(monkeypatch, tmp_path)
    capsys.readouterr()
    client.pages = [PAGE]

    def fail_output(*args, **kwargs):
        raise BrokenPipeError()

    monkeypatch.setattr(events, "print", fail_output, raising=False)
    assert cli.main(["events", "watch", "--once", *common]) == 2
    assert state(tmp_path / "inbox") == ("event-1", 1)


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_terminal_errors_never_advance_or_retry(monkeypatch, tmp_path, capsys, status):
    client, common = setup_cli(monkeypatch, tmp_path)
    capsys.readouterr()
    client.requests.clear()
    client.pages = [
        ApiError(
            "error",
            status=status,
            detail={"code": "cursor_expired", "reset_cursor": "reset", "private": "must not leak"},
        )
    ]
    assert cli.main(["events", "watch", "--once", *common]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    if status == 410:
        assert error["detail"] == {"code": "cursor_expired", "reset_cursor": "reset"}
    assert "must not leak" not in captured.err
    assert len(client.requests) == 2  # authorization head plus one event page
    assert state(tmp_path / "inbox") == ("head", 0)


def test_revoked_access_blocks_pending_replay(monkeypatch, tmp_path, capsys):
    client, common = setup_cli(monkeypatch, tmp_path)
    client.pages = [PAGE]
    assert cli.main(["events", "watch", "--once", *common]) == 0
    capsys.readouterr()
    client.head_error = ApiError("revoked", status=403)
    assert cli.main(["events", "watch", "--once", *common]) == 1
    assert capsys.readouterr().out == ""
    assert state(tmp_path / "inbox") == ("event-1", 1)


def test_new_login_cannot_replay_previous_grant_inbox(monkeypatch, tmp_path, capsys):
    client, common = setup_cli(monkeypatch, tmp_path)
    capsys.readouterr()
    client.identity = (*client.identity[:3], "new-grant")
    assert cli.main(["events", "watch", "--once", *common]) == 2
    assert capsys.readouterr().out == ""
    assert state(tmp_path / "inbox") == ("head", 0)


def test_connection_change_during_page_cannot_accept(monkeypatch, tmp_path, capsys):
    client, common = setup_cli(monkeypatch, tmp_path)
    capsys.readouterr()
    client.pages = [PAGE]
    client.change_after_read = True
    assert cli.main(["events", "watch", "--once", *common]) == 1
    assert capsys.readouterr().out == ""
    assert state(tmp_path / "inbox") == ("head", 0)


def test_cli_backpressure_replays_without_fetching_page(monkeypatch, tmp_path, capsys):
    client, common = setup_cli(monkeypatch, tmp_path)
    client.pages = [PAGE]
    assert cli.main(["events", "watch", "--once", *common]) == 0
    capsys.readouterr()
    client.requests.clear()
    assert cli.main(["events", "watch", "--max-pending", "1", *common]) == 2
    assert json.loads(capsys.readouterr().out) == ITEM
    assert len(client.requests) == 1  # authorization only
    assert state(tmp_path / "inbox") == ("event-1", 1)


def test_continuous_retries_are_bounded_and_keep_cursor(monkeypatch, tmp_path, capsys):
    client, common = setup_cli(monkeypatch, tmp_path)
    capsys.readouterr()
    client.requests.clear()
    client.pages = [ApiError("unavailable", status=503) for _ in range(6)]
    waits = []
    monkeypatch.setattr(events.time, "sleep", waits.append)
    assert cli.main(["events", "watch", *common]) == 1
    assert waits == [2, 4, 8, 16, 30]
    assert all(r[2]["after"] == "head" and r[2]["wait_seconds"] == 25 for r in client.requests[1:])
    assert state(tmp_path / "inbox") == ("head", 0)


@pytest.mark.parametrize(
    "flags",
    [
        ["--quiet"],
        ["--limit", "501"],
        ["--limit", "0"],
        ["--timeout", "25"],
        ["--max-pending", "0"],
    ],
)
def test_invalid_watch_configuration_makes_no_request(monkeypatch, tmp_path, flags):
    client, common = setup_cli(monkeypatch, tmp_path)
    client.requests.clear()
    assert cli.main(["events", "watch", *common, *flags]) == 2
    assert client.requests == []


def test_mcp_watch_is_bounded_durable_and_acknowledged(monkeypatch, tmp_path):
    monkeypatch.setattr("nova_cli_public.config.data_dir", lambda: tmp_path)
    client = Client()
    service = CustomerReadService(client)
    values = {"vendor_workshop_id": 3}
    service.run("events_init", {**values, "after": "head", "snapshot_reconciled": True})
    client.requests.clear()
    client.pages = [PAGE]
    first = service.run("events_watch", {**values, "max_pending": 1, "wait_seconds": 25})
    assert first["items"] == [ITEM] and first["backpressure"]
    assert len(client.requests) == 2
    assert client.requests[-1][2] == {
        "vendor_workshop_id": 3,
        "after": "head",
        "limit": 1,
        "wait_seconds": 25,
    }
    client.requests.clear()
    assert service.run("events_watch", {**values, "max_pending": 1})["items"] == [ITEM]
    assert len(client.requests) == 1
    service.run("events_ack", {**values, "cursor": "event-1"})
    client.pages = [EMPTY]
    assert service.run("events_watch", values)["items"] == []
    assert len(list((tmp_path / "mcp-event-inboxes").glob("*.sqlite"))) == 1


@pytest.mark.parametrize(
    "values",
    [
        {"state_file": "/tmp/arbitrary"},
        {"wait_seconds": 26},
        {"max_pending": 1001},
        {"limit": 0},
        {"vendor_workshop_id": 0},
    ],
)
def test_mcp_rejects_unbounded_or_external_state_arguments(values):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run("events_watch", {"vendor_workshop_id": 3, **values})
    assert client.requests == []


def test_mcp_relogin_uses_new_inbox(monkeypatch, tmp_path):
    monkeypatch.setattr("nova_cli_public.config.data_dir", lambda: tmp_path)
    client = Client()
    service = CustomerReadService(client)
    service.run(
        "events_init", {"vendor_workshop_id": 3, "after": "head", "snapshot_reconciled": True}
    )
    client.identity = (*client.identity[:3], "new-grant")
    with pytest.raises(UsageError, match="events_init"):
        service.run("events_watch", {"vendor_workshop_id": 3})


def test_discovery_distinguishes_local_inbox_effects_from_remote_writes():
    rows = {row["command"]: row for row in manifest(cli.build_parser())["commands"]}
    for name in ("head", "init", "watch", "ack"):
        row = rows["events " + name]
        assert row["required_scope"] == "nova:read"
        assert row["required_operation"] == "workshop_events.list.v1"
        assert row["api_routes"] == [{"method": "GET", "path_pattern": "/workshop-events"}]
        assert row["effects"] == ["remote_read"] + ([] if name == "head" else ["local_file_write"])
        assert "state_file" not in row["tool_input_schema"]["properties"]


def test_mcp_stdio_event_lifecycle_and_expired_cursor(tmp_path):
    import asyncio
    import os
    import sys
    from pathlib import Path

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    runner = tmp_path / "server.py"
    runner.write_text(
        "import runpy, asyncio\nfrom pathlib import Path\n"
        + f"ns=runpy.run_path({str(Path(__file__).resolve())!r})\n"
        + "from nova_cli_public import config\n"
        + f"config.data_dir=lambda: Path({str(tmp_path / 'data')!r})\n"
        + "from nova_cli_public.mcp import create_server, run_stdio\n"
        + "client=ns['Client']()\n"
        + "client.pages=[ns['HEAD'], ns['PAGE'], ns['EMPTY'], "
        + "ns['ApiError']('expired',status=410,detail={'code':'cursor_expired','reset_cursor':'reset'})]\n"
        + "asyncio.run(run_stdio(create_server(ns['CustomerReadService'](client))))\n"
    )

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(runner)],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            rows = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert rows["events_head"].annotations.readOnlyHint
            assert not rows["events_watch"].annotations.readOnlyHint
            args = {"vendor_workshop_id": 3}
            assert (await session.call_tool("events_head", args)).structuredContent == HEAD
            initialized = await session.call_tool(
                "events_init",
                {
                    **args,
                    "after": "head",
                    "snapshot_reconciled": True,
                },
            )
            assert initialized.structuredContent["initialized"]
            page = await session.call_tool("events_watch", args)
            assert page.structuredContent["items"] == [ITEM]
            ack = await session.call_tool("events_ack", {**args, "cursor": "event-1"})
            assert ack.structuredContent == {"acknowledged": "event-1"}
            assert (await session.call_tool("events_watch", args)).structuredContent["items"] == []
            expired = await session.call_tool("events_watch", args)
            assert expired.isError
            assert expired.structuredContent["error"] == {
                "code": "cursor_expired",
                "detail": {"code": "cursor_expired", "reset_cursor": "reset"},
            }

    asyncio.run(scenario())


def test_mcp_lower_pending_limit_bounds_replay_without_discarding(monkeypatch, tmp_path):
    monkeypatch.setattr("nova_cli_public.config.data_dir", lambda: tmp_path)
    client = Client()
    service = CustomerReadService(client)
    args = {"vendor_workshop_id": 3}
    service.run("events_init", {**args, "after": "head", "snapshot_reconciled": True})
    other = {**ITEM, "cursor": "event-2"}
    client.pages = [{"items": [ITEM, other], "next_cursor": "event-2", "has_more": False}]
    assert len(service.run("events_watch", {**args, "max_pending": 2})["items"]) == 2
    client.requests.clear()
    bounded = service.run("events_watch", {**args, "max_pending": 1})
    assert bounded["items"] == [ITEM]
    assert bounded["pending_count"] == 2 and bounded["backpressure"]
    assert len(client.requests) == 1
    service.run("events_ack", {**args, "cursor": "event-1"})
    assert service.run("events_watch", {**args, "max_pending": 1})["items"] == [other]


@pytest.mark.parametrize("reconciled", [False, 1, "true"])
def test_mcp_init_requires_explicit_boolean_reconciliation(reconciled):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run(
            "events_init",
            {
                "vendor_workshop_id": 3,
                "after": "head",
                "snapshot_reconciled": reconciled,
            },
        )
    assert client.requests == []


def test_mcp_pending_replay_survives_remote_cursor_expiry(monkeypatch, tmp_path):
    monkeypatch.setattr("nova_cli_public.config.data_dir", lambda: tmp_path)
    client = Client()
    service = CustomerReadService(client)
    args = {"vendor_workshop_id": 3}
    service.run("events_init", {**args, "after": "head", "snapshot_reconciled": True})
    client.pages = [PAGE]
    assert service.run("events_watch", args)["items"] == [ITEM]
    client.pages = [ApiError("expired", status=410)]
    client.requests.clear()
    assert service.run("events_watch", args)["items"] == [ITEM]
    assert len(client.requests) == 1  # Live authorization, no stale resume read.
    service.run("events_ack", {**args, "cursor": "event-1"})
    with pytest.raises(ApiError) as expired:
        service.run("events_watch", args)
    assert expired.value.status == 410


def test_mcp_returns_actionable_uninitialized_inbox_error(monkeypatch, tmp_path):
    import asyncio

    from mcp import types

    from nova_cli_public.mcp import create_server

    monkeypatch.setattr("nova_cli_public.config.data_dir", lambda: tmp_path)
    server = create_server(CustomerReadService(Client()))
    result = asyncio.run(
        server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name="events_watch",
                    arguments={"vendor_workshop_id": 3},
                ),
            )
        )
    )
    assert result.root.isError
    assert result.root.structuredContent["error"] == {
        "code": "event_inbox_error",
        "detail": {"message": "Run events_head, reconcile a snapshot, then events_init."},
    }
