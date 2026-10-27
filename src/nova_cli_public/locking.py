"""OS-user scoped locks for profile credential mutations."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from nova_cli_public.errors import UsageError


@contextmanager
def profile_lock(name: str):
    # Keyring profile names share one OS-user namespace even across XDG roots.
    # Keep this lock in that same OS-user scope. Empty lock files contain no secrets.
    directory = Path.home() / ".cache" / "nova-cli-public" / "profile-locks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    filename = hashlib.sha256(name.encode()).hexdigest() + ".lock"
    try:
        with FileLock(directory / filename, timeout=25, mode=0o600):
            yield
    except Timeout:
        raise UsageError(
            "This Nova profile is busy. Retry after the current operation completes."
        ) from None
