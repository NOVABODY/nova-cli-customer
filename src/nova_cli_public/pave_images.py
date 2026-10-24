"""One fixed authorized image read; never fetch a provider URL."""
from pathlib import Path

from nova_cli_public import claim_archive
from nova_cli_public.errors import ApiError, UsageError

PATH = '/body-repair/pave/image'
MIMES = ('image/png', 'image/jpeg', 'image/webp')


def query(storage_key, category, idx):
    if (not isinstance(storage_key, str) or not 1 <= len(storage_key) <= 500
            or category not in ('panel', 'damage', 'side', 'vehicle') or type(idx) is not int or not 0 <= idx <= 999):
        raise UsageError('Check the image arguments. / Revisa los argumentos de la imagen.')
    return {'storage_key': storage_key, 'category': category, 'idx': idx}


def target(method, path, values, json_body, raw_body, limit):
    if (method != 'GET' or path != PATH or set(values or {}) != {'storage_key', 'category', 'idx'}
            or json_body is not None or raw_body is not None or type(limit) is not int or not 1 <= limit <= claim_archive.MAX_BYTES):
        raise UsageError('Use the named PAVE image read. / Usa la lectura de imagen PAVE.')
    query(**values)


def mime(raw):
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return MIMES[0]
    if raw.startswith(b'\xff\xd8\xff'):
        return MIMES[1]
    if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        return MIMES[2]
    raise ApiError('Invalid image format. / Formato de imagen no válido.')


def download(args):
    from nova_cli_public import body_documents
    from nova_cli_public.legacy_reads import client_from_args

    values = query(args.storage_key, args.category, args.idx)
    destination = Path(args.out).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise UsageError('The output file exists. / El archivo de salida ya existe.')
    raw = client_from_args(args).request('GET', PATH, query=values, image=True)
    return body_documents.publish(raw, destination, mime(raw))


def embedded(client, values):
    from nova_cli_public import body_documents

    raw = client.request('GET', PATH, query=query(**values), image=True, image_max_bytes=body_documents.PDF_EMBED_MAX_BYTES)
    return body_documents.EmbeddedDocument(raw, mime(raw))
