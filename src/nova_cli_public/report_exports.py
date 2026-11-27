"""Bounded original vendor report exports; never execute or extract content."""
from .errors import ApiError, UsageError
from .vendor_defect_reports import MAX_BYTES, MIMES, validate_export


def target(method, path, json_body, raw_body, format):
    if (format not in MIMES or method != 'GET' or path != '/defects/report/export.' + format
            or json_body is not None or raw_body is not None):
        raise UsageError('Use the named report export. / Usa la exportación de informe indicada.')


def read(response, format):
    try:
        if (response.status != 200 or response.headers.get('Content-Type', '').split(';')[0].strip().lower() != MIMES[format]
                or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
            raise ValueError()
        length = response.headers.get('Content-Length')
        if length is not None and (len(length) > 8 or not length.isascii() or not length.isdigit() or int(length) > MAX_BYTES):
            raise ValueError()
        raw = response.read(MAX_BYTES + 1)
        if length is not None and len(raw) != int(length):
            raise ValueError()
        validate_export(raw, format)
        return raw
    except (ValueError, UnicodeError):
        raise ApiError('Cannot read the report export. Limit: 2 MiB. / No se puede leer la exportación del informe. Límite: 2 MiB.') from None
