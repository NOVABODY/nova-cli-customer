"""Cortex file review reuses the API parser; source bytes remain unchanged."""
import json
from pathlib import Path
from uuid import uuid4

from nova_cli_public.errors import ApiError, UsageError
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


def import_review(args):
    try:
        with Path(args.review_file).expanduser().open('rb') as source:
            raw = source.read(100 * 1024 * 1024 + 1)
        if len(raw) > 100 * 1024 * 1024:
            raise ValueError()
        value = json.loads(raw)
        if (not isinstance(value, dict) or not isinstance(value.get('mapped'), list)
                or not 1 <= len(value['mapped']) <= 2000 or not all(isinstance(row, dict) for row in value['mapped'])
                or not isinstance(value.get('errors'), list) or value['errors']
                or not isinstance(value.get('missing_columns'), list) or value['missing_columns']
                or type(value.get('skipped')) is not int or value['skipped'] < 0
                or not isinstance(value.get('records'), list) or len(value['records']) < len(value['mapped'])
                or not all(isinstance(row, dict) and type(row.get('excluded')) is bool
                           and type(row.get('inactive')) is bool for row in value['records'])):
            raise ValueError()
    except (OSError, ValueError) as exc:
        raise UsageError('Use a complete review with no source errors and 1 to 2000 mapped rows; at most 100 MiB.') from exc
    if args.deactivate_missing and (value['skipped'] or any(row.get('excluded') or row.get('inactive') for row in value['records'])):
        raise UsageError('Do not deactivate missing vans after source rows were skipped or excluded.')
    body = {'rows': value['mapped'], 'dry_run': args.dry_run,
            'add_missing_stations': args.add_missing_stations, 'deactivate_missing': args.deactivate_missing}
    try:
        result = client_from_args(args).request('POST', '/vehicles/bulk-upsert', json_body=body)
        if (not isinstance(result, dict) or not isinstance(result.get('results'), list)
                or not all(isinstance(row, dict) and isinstance(row.get('action'), str) and row['action'] for row in result['results'])
                or not isinstance(result.get('summary'), dict) or type(result['summary'].get('error')) is not int
                or result['summary']['error'] < 0):
            raise ApiError('Nova returned an unsupported import response.')
    except ApiError as exc:
        if not args.dry_run and (exc.status is None or exc.status >= 500):
            raise ApiError('The import outcome is unknown. Read the fleet before trying again.', code='outcome_unknown') from None
        raise
    return {**result, 'ok': result['summary']['error'] == 0 and not any(row['action'] == 'error' for row in result['results']), 'dry_run': args.dry_run}


CORTEX_IMPORT_COMMANDS = [{
    'command': 'fleet-import ' + action, 'tool': action + '_fleet_import',
    'grant': 'vehicles.fleet_import.apply.v1', 'scope': 'nova:read nova:write',
    'effect': 'remote_read' if action == 'preview' else 'remote_write', 'read_only': action == 'preview',
    'arguments': [(['--review-file'], {'required': True}),
                  (['--add-missing-stations'], {'action': 'store_true', 'default': False}),
                  (['--deactivate-missing'], {'action': 'store_true', 'default': False})],
    'groups': [], 'handler': import_review, 'defaults': {'dry_run': action == 'preview'},
} for action in ['preview', 'apply']]
