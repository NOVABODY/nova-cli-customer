"""Save authorized Body documents to the caller's chosen file."""
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nova_cli_public import claim_archive
from nova_cli_public.errors import UsageError
from nova_cli_public.legacy_reads import client_from_args


def download(args, kind):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.request_ref):
        raise UsageError("Use an order reference. / Use una referencia de orden.")
    quote = getattr(args, 'quote', None)
    if quote is not None and not re.fullmatch(r'(?:BRQ-)?[0-9]+', quote):
        raise UsageError("Use a numeric or BRQ quote ID. / Use un ID de cotización numérico o BRQ.")
    lang = getattr(args, 'lang', 'en')
    if kind == 'documentation' and lang not in ('en', 'es'):
        raise UsageError('Use en or es. / Usa en o es.')
    destination = Path(args.out).expanduser().absolute()
    if os.path.lexists(destination):
        raise UsageError("The output file exists. / El archivo de salida ya existe.")
    data = client_from_args(args).request('GET', f'/body-repair/requests/{args.request_ref}/{kind}',
        query={'lang': lang} if kind == 'documentation' else {'quote': quote} if quote is not None else None,
        **({'archive': True} if kind == 'documentation' else {'pdf': True}))
    return publish(data, destination, claim_archive.MIME if kind == 'documentation' else 'application/pdf')


def publish(data, destination, media):
    try:
        descriptor, temporary = tempfile.mkstemp(prefix='.nova-document-', dir=destination.parent)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(data)
            os.link(temporary, destination)
        finally:
            os.unlink(temporary)
    except OSError:
        raise UsageError('Cannot save the document. Check the output folder. / '
                         'No se puede guardar el documento. Revisa la carpeta de salida.') from None
    return {'ok': True, 'out': str(destination), 'content_type': media, 'size_bytes': len(data)}



PDF_EMBED_MAX_BYTES = 1024 * 1024
DOCUMENT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'description': 'Descriptor for PDF bytes embedded in the resource content. No local file is written.',
    'required': ['uri', 'mime_type', 'size_bytes', 'sha256'],
    'properties': {
        'uri': {'type': 'string', 'pattern': r'^urn:sha256:[a-f0-9]{64}$'},
        'mime_type': {'const': 'application/pdf'},
        'size_bytes': {'type': 'integer', 'minimum': 1, 'maximum': PDF_EMBED_MAX_BYTES},
        'sha256': {'type': 'string', 'pattern': r'^[a-f0-9]{64}$'},
    },
}


@dataclass(frozen=True)
class EmbeddedDocument:
    data: bytes
    mime_type: str = 'application/pdf'

    def descriptor(self):
        digest = hashlib.sha256(self.data).hexdigest()
        return {'uri': 'urn:sha256:' + digest, 'mime_type': self.mime_type,
                'size_bytes': len(self.data), 'sha256': digest}


def embedded(client, request_ref, kind, quote=None, lang="en"):
    if kind == 'documentation':
        return EmbeddedDocument(client.request('GET', f'/body-repair/requests/{request_ref}/documentation',
            query={'lang': lang}, archive=True, archive_max_bytes=PDF_EMBED_MAX_BYTES), claim_archive.MIME)
    return EmbeddedDocument(client.request('GET', f'/body-repair/requests/{request_ref}/{kind}',
        query={'quote': quote} if quote is not None else None,
        pdf=True, pdf_max_bytes=PDF_EMBED_MAX_BYTES))


def document_schema(kind):
    if kind != 'documentation':
        return DOCUMENT_SCHEMA
    return {**DOCUMENT_SCHEMA, 'description': 'Descriptor for ZIP bytes embedded in the resource content. No local file is written.',
        'properties': {**DOCUMENT_SCHEMA['properties'], 'mime_type': {'const': claim_archive.MIME}}}
