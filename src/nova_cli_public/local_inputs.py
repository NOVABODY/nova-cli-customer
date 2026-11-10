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
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
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
    if tool == 'get_skill':
        yield arguments  # A remote catalog path, never a local file input.
        return
    selected = {key: value for key, value in arguments.items()
                if (key == 'file' or key.endswith('_file') or
                    (key in ('odometer_photo_path', 'work_photo_path') and isinstance(value, str)
                     and not value.startswith('photos/'))) and value is not None and value != []}
    files = selected.get('photo_file')
    if files is not None and (not isinstance(files, list) or len(files) > 12):
        raise UsageError('Use at most 12 photos. / Usa un máximo de 12 fotos.')
    if not selected:
        yield arguments
        return
    if root is None:
        raise UsageError(DENIED)
    with TemporaryDirectory(prefix='nova-mcp-input-') as temporary:
        values = dict(arguments)
        expanded = [(key, item, position) for key, value in selected.items()
                    for position, item in enumerate(value if isinstance(value, list) else [value])]
        for index, (key, value, position) in enumerate(expanded):
            limit = 1024 * 1024 if key.endswith('_file') and key != 'review_file' else MAX_INPUT_BYTES
            if key in ('photo_file', 'odometer_photo_path', 'work_photo_path'):
                limit = 50 * 1024 * 1024
            if key == 'file' and tool in ('upload_photo', 'review_cortex_file'):
                limit = (50 if tool == 'upload_photo' else 20) * 1024 * 1024
            name, data = _read(root, value, limit)
            if tool == 'review_cortex_file' and key == 'file':
                suffix = Path(name).suffix.lower().lstrip('.')
                if suffix not in ('csv', 'xlsx') or arguments.get('format', suffix) not in (None, suffix):
                    raise UsageError(DENIED)
            if key in ('photo_file', 'odometer_photo_path', 'work_photo_path') or (tool == 'upload_photo' and key == 'file'):
                actual = image_type(data)
                expected = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.heic': 'image/heic', '.heif': 'image/heif'}.get(Path(name).suffix.lower())
                if (expected and expected != actual) or (arguments.get('content_type') and arguments['content_type'] != actual):
                    raise UsageError(IMAGE_ERROR)
                if key == 'file':
                    values['content_type'] = actual
            folder = Path(temporary) / str(index)
            folder.mkdir()
            snapshot = folder / name
            snapshot.write_bytes(data)
            if isinstance(selected[key], list):
                if position == 0:
                    values[key] = []
                values[key].append(str(snapshot))
            else:
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
        brands = (b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis')
        if data[8:12] in brands or any(data[i:i+4] in brands for i in range(16, size, 4)):
            return 'image/heic'
        if data[8:12] in (b'mif1', b'msf1'):
            return 'image/heif'
    raise UsageError("Use a JPEG, PNG, WebP, HEIC, or HEIF image. / Usa una imagen JPEG, PNG, WebP, HEIC o HEIF.")


IMAGE_ERROR = 'Use a regular image file with a matching file type, at most 50 MiB. / Usa un archivo de imagen normal con un tipo coincidente, de un máximo de 50 MiB.'
IMAGE_LIMIT = 50 * 1024 * 1024


def read_image(value, content_type=None, *, allow_pdf=False):
    """Resolve the parent, then open the final component without following links."""
    try:
        path = Path(value).expanduser()
        path = path.parent.resolve(strict=True) / path.name
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > IMAGE_LIMIT:
                raise UsageError(IMAGE_ERROR)
            data = stream.read(IMAGE_LIMIT + 1)
        if len(data) > IMAGE_LIMIT:
            raise UsageError(IMAGE_ERROR)
        actual = 'application/pdf' if allow_pdf and data.startswith(b'%PDF-') else image_type(data)
        expected = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                    '.webp': 'image/webp', '.heic': 'image/heic', '.heif': 'image/heif',
                    '.pdf': 'application/pdf'}.get(path.suffix.lower())
        if (expected is not None and actual != expected) or (content_type and content_type != actual):
            raise UsageError(IMAGE_ERROR)
        return path, data, actual
    except (OSError, ValueError):
        raise UsageError(IMAGE_ERROR) from None
