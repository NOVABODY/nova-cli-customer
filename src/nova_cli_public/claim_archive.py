"""Bounded validation of the existing stored documentation ZIP; never extract files."""
import io
import re
import struct
import zipfile

from nova_cli_public.errors import ApiError, UsageError

MAX_BYTES = 64 * 1024 * 1024
MIME = 'application/zip'
ROUTE = r'/body-repair/requests/[A-Za-z0-9_-]{1,64}/documentation'


def target(method, path, query, json_body, raw_body, limit):
    if (method != 'GET' or not re.fullmatch(ROUTE, path)
            or set(query or {}) - {'lang'} or (query or {}).get('lang', 'en') not in ('en', 'es')
            or json_body is not None or raw_body is not None
            or type(limit) is not int or not 1 <= limit <= MAX_BYTES):
        raise UsageError('Use the named documentation ZIP read. / Usa la lectura del ZIP de documentación.')


def read(response, limit):
    if (response.status != 200 or response.headers.get('Content-Type', '').split(';')[0].strip().lower() != MIME
            or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
        raise ApiError('Nova did not return a documentation ZIP. / Nova no devolvió un ZIP de documentación.')
    length = response.headers.get('Content-Length')
    if length is not None and (len(length) > 8 or not length.isascii() or not length.isdigit()):
        raise ApiError('Invalid ZIP length. / Longitud de ZIP no válida.')
    if length is not None and int(length) > limit:
        raise ApiError('ZIP exceeds the byte limit. / El ZIP supera el límite de bytes.', code='archive_too_large')
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ApiError('ZIP exceeds the byte limit. / El ZIP supera el límite de bytes.', code='archive_too_large')
    if length is not None and len(raw) != int(length):
        raise ApiError('Incomplete ZIP transfer. / Transferencia de ZIP incompleta.')
    try:
        # Bound directory allocation before ZipFile parses it; ZIP64/multidisk are not emitted.
        end = raw.rfind(b'PK\x05\x06', max(0, len(raw) - 65557))
        if end < 0 or end + 22 > len(raw):
            raise ValueError
        disk, directory_disk, on_disk, count, size, offset, comment = struct.unpack_from('<4H2LH', raw, end + 4)
        if (disk or directory_disk or on_disk != count or not 2 <= count <= 4
                or size > count * (46 + 800) or offset + size != end
                or comment or end + 22 != len(raw)):
            raise ValueError
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) != count or len({entry.filename for entry in entries}) != count:
                raise ValueError
            pdfs = notes = total = 0
            for entry in entries:
                name = entry.filename
                if (len(name) > 200 or '/' in name or '\\' in name or ':' in name or '\x00' in name
                        or len(name.encode('utf-8')) > 800 or entry.extra or entry.comment
                        or entry.is_dir() or entry.flag_bits & 1 or entry.compress_type != zipfile.ZIP_STORED
                        or entry.compress_size != entry.file_size or entry.file_size <= 0):
                    raise ValueError
                pdfs += name.lower().endswith('.pdf')
                notes += name.lower().endswith('.txt')
                total += entry.file_size
                if total > limit:
                    raise ValueError
                # STORED only: no decompressor; ZipExtFile checks CRC at EOF.
                with archive.open(entry) as stream:
                    while stream.read(65536):
                        pass
            if not 1 <= pdfs <= 3 or notes > 1 or pdfs + notes != count:
                raise ValueError
    except (ValueError, struct.error, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, UnicodeError, OverflowError):
        raise ApiError('Invalid documentation ZIP. / ZIP de documentación no válido.') from None
    return raw
