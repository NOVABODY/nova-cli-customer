"""Snapshot model-selected inputs inside the folder selected by the operator."""
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from nova_cli_public.errors import UsageError

MAX_INPUT_BYTES = 100 * 1024 * 1024
DENIED = 'Use a file in the folder set with --file-root. / Usa un archivo de la carpeta indicada con --file-root.'


def _read(root, value, limit=MAX_INPUT_BYTES):
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
                data = stream.read(limit + 1)
                if len(data) > limit:
                    raise UsageError(DENIED)
                return path.name, data
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        raise UsageError(DENIED) from None


@contextmanager
def local_inputs(arguments, root, *, tool=None):
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
            limit = 1024 * 1024 if key.endswith('_file') and key != 'review_file' else MAX_INPUT_BYTES
            if key == 'file' and tool in ('upload_photo', 'review_cortex_file'):
                limit = (50 if tool == 'upload_photo' else 20) * 1024 * 1024
            name, data = _read(root, value, limit)
            if tool == 'review_cortex_file' and key == 'file':
                suffix = Path(name).suffix.lower().lstrip('.')
                if suffix not in ('csv', 'xlsx') or arguments.get('format', suffix) not in (None, suffix):
                    raise UsageError(DENIED)
            if tool == 'upload_photo' and key == 'file':
                values['content_type'] = image_type(data)
            folder = Path(temporary) / str(index)
            folder.mkdir()
            snapshot = folder / name
            snapshot.write_bytes(data)
            values[key] = str(snapshot)
        yield values


def image_type(data):
    """Identify supported image signatures; this is not a full image decoder."""
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if len(data) >= 16 and data[:4] == b'RIFF' and data[8:12] == b'WEBP' and data[12:16] in (b'VP8 ', b'VP8L', b'VP8X'):
        return 'image/webp'
    size = int.from_bytes(data[:4], 'big')
    if 16 <= size <= len(data) and data[4:8] == b'ftyp':
        brands = (b'heic', b'heix', b'hevc', b'hevx')
        if data[8:12] in brands or any(data[i:i+4] in brands for i in range(16, size, 4)):
            return 'image/heic'
    raise UsageError("Use a JPEG, PNG, HEIC, or WebP image. / Use una imagen JPEG, PNG, HEIC o WebP.")
