"""Durable, at-least-once local acceptance for workshop invalidations."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from nova_cli_public.errors import ApiError, AuthError, UsageError

EVENT_NAMES = {
    "work_order.changed",
    "work_order.removed",
    "defect.changed",
    "defect.removed",
    "comment.changed",
    "photo.changed",
    "title.changed",
    "assignment.changed",
    "schedule.changed",
    "ro.changed",
}


class EventInboxError(UsageError):
    """Fixed local inbox instructions safe to return through MCP."""


class EventInbox:
    def __init__(self, path: Path, identity: str) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA fullfsync=ON")
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS events ("
            "seq INTEGER PRIMARY KEY, cursor TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,"
            "acked INTEGER NOT NULL DEFAULT 0);"
        )
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            saved = self.get("identity")
            mismatch = saved is not None and saved != identity
            if not mismatch:
                self.db.execute("INSERT OR IGNORE INTO state VALUES ('identity', ?)", (identity,))
        if mismatch:
            self.db.close()
            raise EventInboxError(
                "Event inbox belongs to another API, profile, credential, or workshop."
            )

    def close(self) -> None:
        self.db.close()

    def get(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    @contextmanager
    def watcher(self) -> Iterator[None]:
        # Ack uses only SQLite; a second watcher must not race the resume cursor.
        import fcntl

        fd = os.open(
            str(self.path) + ".lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise EventInboxError(
                    "Another watcher or initializer is using this event inbox."
                ) from exc
            yield
        finally:
            os.close(fd)

    def initialize(self, cursor: str, *, reset: bool = False) -> None:
        if not cursor.strip():
            raise EventInboxError("A nonblank bootstrap/reset cursor is required.")
        with self.watcher(), self.db:
            if self.pending():
                raise EventInboxError(
                    "Process and acknowledge pending events before resetting the cursor."
                )
            if self.get("cursor") is not None and not reset:
                raise EventInboxError(
                    "Inbox is initialized; --reset requires explicit snapshot reconciliation."
                )
            self.db.execute("INSERT OR REPLACE INTO state VALUES ('cursor', ?)", (cursor,))

    def pending(self) -> list[dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in self.db.execute("SELECT payload FROM events WHERE acked=0 ORDER BY seq")
        ]

    def accept(self, page: Any) -> list[dict[str, Any]]:
        if not isinstance(page, dict) or not isinstance(page.get("items"), list):
            raise ApiError("Invalid event page: expected items array.")
        cursor = page.get("next_cursor")
        if not isinstance(cursor, str) or not cursor or not isinstance(page.get("has_more"), bool):
            raise ApiError("Invalid event page: expected next_cursor and has_more.")
        if page["has_more"] and not page["items"]:
            raise ApiError("Invalid empty event page with has_more; cursor was not advanced.")
        for item in page["items"]:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("cursor"), str)
                or not item["cursor"]
                or not isinstance(item.get("event"), str)
                or item["event"] not in EVENT_NAMES
                or not isinstance(item.get("work_order_id"), str)
                or not item["work_order_id"]
                or "defect_id" not in item
                or (item["defect_id"] is not None and not isinstance(item["defect_id"], str))
                or not isinstance(item.get("occurred_at"), str)
            ):
                raise ApiError("Invalid durable event; resume cursor was not advanced.")
        accepted = []
        # FULL synchronous commit makes both event payloads and resume cursor durable
        # before any stdout emission. Failed emission is recovered from this inbox.
        with self.db:
            for item in page["items"]:
                existing = self.db.execute(
                    "SELECT payload FROM events WHERE cursor=?", (item["cursor"],)
                ).fetchone()
                if existing and json.loads(existing[0]) != item:
                    raise ApiError("Event cursor reused with changed payload; resume stopped.")
                result = self.db.execute(
                    "INSERT OR IGNORE INTO events(cursor,payload) VALUES (?,?)",
                    (item["cursor"], json.dumps(item, sort_keys=True)),
                )
                if result.rowcount:
                    accepted.append(item)
            self.db.execute("INSERT OR REPLACE INTO state VALUES ('cursor', ?)", (cursor,))
        return accepted

    def acknowledge(self, cursor: str) -> None:
        with self.db:
            result = self.db.execute("UPDATE events SET acked=1 WHERE cursor=?", (cursor,))
            if not result.rowcount:
                raise EventInboxError("Cursor is not a durably accepted event in this inbox.")


def _connect(client, workshop_id):
    if type(workshop_id) is not int or workshop_id < 1:
        raise EventInboxError("--vendor-workshop-id must be positive.")
    client.refresh()
    identity = client.connection_identity()
    head = client.request(
        "GET",
        "/workshop-events",
        query={
            "vendor_workshop_id": workshop_id,
            "wait_seconds": 0,
        },
    )
    if client.connection_identity() != identity:
        raise AuthError("Connection changed. Start again with its own event inbox.")
    binding = json.dumps(
        [client.profile.api.rstrip("/"), client.profile.name, workshop_id, identity]
    )
    return identity, binding, head


def _page(client, identity, workshop_id, cursor, limit, wait_seconds):
    value = client.request(
        "GET",
        "/workshop-events",
        query={
            "vendor_workshop_id": workshop_id,
            "after": cursor,
            "limit": limit,
            "wait_seconds": wait_seconds,
        },
    )
    if client.connection_identity() != identity:
        raise AuthError("Connection changed. The event inbox was not advanced.")
    return value


def run_events(args, client):
    if args.events_command == "watch":
        if args.quiet:
            raise EventInboxError("events watch emits NDJSON; --quiet is not supported.")
        if not 1 <= args.limit <= 500 or args.max_pending < 1:
            raise EventInboxError("--limit must be 1..500 and --max-pending must be positive.")
        if args.timeout <= 25:
            raise EventInboxError("--timeout must exceed the 25-second server long-poll wait.")
    identity, binding, head = _connect(client, args.vendor_workshop_id)
    if args.events_command == "head":
        return head
    try:
        inbox = EventInbox(Path(args.state_file), binding)
        try:
            if args.events_command == "init":
                if not args.snapshot_reconciled:
                    raise EventInboxError("Reconcile the snapshot before initializing the inbox.")
                # Check the opaque bootstrap cursor against the live stream before saving.
                _page(client, identity, args.vendor_workshop_id, args.after, 1, 0)
                inbox.initialize(args.after, reset=args.reset)
                return {"initialized": True, "cursor": args.after}
            if args.events_command == "ack":
                inbox.acknowledge(args.cursor)
                return {"acknowledged": args.cursor}
            with inbox.watcher():
                if inbox.get("cursor") is None:
                    raise EventInboxError(
                        "Run events head, reconcile a snapshot, then events init --after."
                    )
                for item in inbox.pending():
                    print(json.dumps(item, sort_keys=True), flush=True)
                failures = 0
                while True:
                    remaining = args.max_pending - len(inbox.pending())
                    if remaining <= 0:
                        raise EventInboxError(
                            "Inbox backpressure: acknowledge processed events, then restart."
                        )
                    try:
                        page = _page(
                            client,
                            identity,
                            args.vendor_workshop_id,
                            inbox.get("cursor"),
                            min(args.limit, remaining),
                            0 if args.once else 25,
                        )
                    except ApiError as exc:
                        if (
                            args.once
                            or (exc.status is not None and exc.status < 500)
                            or failures >= 5
                        ):
                            raise
                        failures += 1
                        time.sleep(min(2**failures, 30))
                        continue
                    failures = 0
                    for item in inbox.accept(page):
                        print(json.dumps(item, sort_keys=True), flush=True)
                    if args.once:
                        args.quiet = True  # NDJSON already emitted; no trailing JSON null.
                        return None
        finally:
            inbox.close()
    except (OSError, sqlite3.Error) as exc:
        raise EventInboxError(
            "Could not access event inbox or output; accepted events remain replayable."
        ) from exc


def run_event_tool(name, values, client):
    """One bounded page per tool call; init/reset and ack are explicit local actions."""
    import hashlib

    from nova_cli_public.config import data_dir

    workshop_id = values["vendor_workshop_id"]
    identity, binding, head = _connect(client, workshop_id)
    if name == "events_head":
        return head
    path = (
        data_dir()
        / "mcp-event-inboxes"
        / (hashlib.sha256(binding.encode()).hexdigest() + ".sqlite")
    )
    try:
        return _event_tool_inbox(name, values, client, identity, binding, path)
    except (OSError, sqlite3.Error) as exc:
        raise EventInboxError(
            "Could not access event inbox; accepted events remain replayable."
        ) from exc


def _event_tool_inbox(name, values, client, identity, binding, path):
    workshop_id = values["vendor_workshop_id"]
    inbox = EventInbox(path, binding)
    try:
        if name == "events_init":
            if not values["snapshot_reconciled"]:
                raise EventInboxError("Reconcile the snapshot before initializing the inbox.")
            _page(client, identity, workshop_id, values["after"], 1, 0)
            inbox.initialize(values["after"], reset=values.get("reset", False))
            return {"initialized": True, "cursor": values["after"]}
        if name == "events_ack":
            inbox.acknowledge(values["cursor"])
            return {"acknowledged": values["cursor"]}
        with inbox.watcher():
            if inbox.get("cursor") is None:
                raise EventInboxError("Run events_head, reconcile a snapshot, then events_init.")
            pending = inbox.pending()
            remaining = values["max_pending"] - len(pending)
            # Return durable work before reading again: an expired remote cursor
            # must not hide the cursors needed to acknowledge and reset the inbox.
            if not pending:
                page = _page(
                    client,
                    identity,
                    workshop_id,
                    inbox.get("cursor"),
                    min(values["limit"], remaining),
                    values["wait_seconds"],
                )
                inbox.accept(page)
            pending = inbox.pending()
            return {
                "items": pending[: values["max_pending"]],
                "next_cursor": inbox.get("cursor"),
                "pending_count": len(pending),
                "backpressure": len(pending) >= values["max_pending"],
                "ack_required": True,
            }
    finally:
        inbox.close()


def cursor_reset_detail(exc):
    """Expose only the documented reset signal, never arbitrary read-error content."""
    if not isinstance(exc, ApiError) or exc.status != 410 or not isinstance(exc.detail, dict):
        return None
    cursor = exc.detail.get("reset_cursor")
    if exc.detail.get("code") == "cursor_expired" and isinstance(cursor, str) and cursor:
        return {"code": "cursor_expired", "reset_cursor": cursor}
    return None
