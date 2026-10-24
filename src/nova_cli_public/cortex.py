"""Cortex file review reuses the API parser; source bytes remain unchanged."""
import json
from pathlib import Path
from uuid import uuid4

from nova_cli_public.errors import UsageError
from nova_cli_public.legacy_reads import client_from_args

MAX_FILE_BYTES = 20 * 1024 * 1024


def review(args):
    path = Path(args.file).expanduser()
    format = args.format or path.suffix.lower().lstrip('.')
    if format not in ('csv', 'xlsx'):
        raise UsageError('Use a CSV or XLSX file, or set --format.')
    try:
        options = args.options or '{}'
        if len(options.encode()) > 65536 or not isinstance(json.loads(options), dict):
            raise ValueError()
        with path.open('rb') as source:
            data = source.read(MAX_FILE_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise UsageError('Read the source file and supply a JSON options object of at most 64 KiB.') from exc
    if len(data) > MAX_FILE_BYTES:
        raise UsageError('Use a source file of at most 20 MiB.')
    boundary = 'nova-cortex-' + uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="fleet.{format}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + data
    body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="options"\r\n\r\n'
             f'{options}\r\n--{boundary}--\r\n').encode()
    return client_from_args(args).request('POST', '/vehicles/fleet-import/parse', query={'format': format},
        raw_body=body, raw_content_type='multipart/form-data; boundary=' + boundary)


CORTEX_COMMANDS = [{
    'command': 'fleet-import review', 'tool': 'review_cortex_file', 'grant': 'vehicles.fleet_import.review.v1',
    'arguments': [(['--file'], {'required': True}), (['--format'], {'choices': ['csv', 'xlsx']}),
                  (['--options'], {'help': 'Cumulative JSON corrections and excluded source rows.'})],
    'groups': [], 'handler': review,
}]
