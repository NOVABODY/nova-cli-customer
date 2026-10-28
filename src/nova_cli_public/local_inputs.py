"""Snapshot model-selected inputs inside the folder selected by the operator."""
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from nova_cli_public.errors import UsageError

MAX_INPUT_BYTES = 100 * 1024 * 1024
DENIED = 'Use a file in the folder set with --file-root. / Usa un archivo de la carpeta indicada con --file-root.'


def _read(root, value):
    if not isinstance(value, str) or not value or value == '-':
        raise UsageError(DENIED)
    path = Path(value).expanduser()
    if '..' in path.parts:
        raise UsageError(DENIED)
    path = path if path.is_absolute() else root / path
    try:
        parts = path.relative_to(root).parts
        if not parts or os.open not in os.supports_dir_fd or not hasattr(os, 'O_NOFOLLOW'):
            raise UsageError(DENIED)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in parts[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            with os.fdopen(source, 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise UsageError(DENIED)
                data = stream.read(MAX_INPUT_BYTES + 1)
                if len(data) > MAX_INPUT_BYTES:
                    raise UsageError(DENIED)
                return path.name, data
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        raise UsageError(DENIED) from None


@contextmanager
def local_inputs(arguments, root):
    """Do not let a handler reopen an attacker-swapped source or follow a link."""
    selected = {key: value for key, value in arguments.items()
                if (key == 'file' or key.endswith('_file')) and value is not None}
    if not selected:
        yield arguments
        return
    if root is None:
        raise UsageError(DENIED)
    with TemporaryDirectory(prefix='nova-mcp-input-') as temporary:
        values = dict(arguments)
        for index, (key, value) in enumerate(selected.items()):
            name, data = _read(root, value)
            folder = Path(temporary) / str(index)
            folder.mkdir()
            snapshot = folder / name
            snapshot.write_bytes(data)
            values[key] = str(snapshot)
        yield values
