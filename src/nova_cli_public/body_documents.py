"""Save the existing authorized Body PDFs to the caller's chosen file."""
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nova_cli_public.errors import UsageError
from nova_cli_public.legacy_reads import client_from_args


def download(args, kind):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.request_ref):
        raise UsageError("Use an order reference. / Use una referencia de orden.")
    quote = getattr(args, 'quote', None)
    if quote is not None and not re.fullmatch(r'(?:BRQ-)?[0-9]+', quote):
        raise UsageError("Use a numeric or BRQ quote ID. / Use un ID de cotización numérico o BRQ.")
    destination = Path(args.out).expanduser().absolute()
    if os.path.lexists(destination):
        raise UsageError("The output file exists. / El archivo de salida ya existe.")
    data = client_from_args(args).request('GET', f'/body-repair/requests/{args.request_ref}/{kind}',
        query={'quote': quote} if quote is not None else None, pdf=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.nova-document-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    return {'ok': True, 'out': str(destination), 'content_type': 'application/pdf', 'size_bytes': len(data)}


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
class EmbeddedPDF:
    data: bytes

    def descriptor(self):
        digest = hashlib.sha256(self.data).hexdigest()
        return {'uri': 'urn:sha256:' + digest, 'mime_type': 'application/pdf',
                'size_bytes': len(self.data), 'sha256': digest}


def embedded(client, request_ref, kind, quote=None):
    return EmbeddedPDF(client.request('GET', f'/body-repair/requests/{request_ref}/{kind}',
        query={'quote': quote} if quote is not None else None,
        pdf=True, pdf_max_bytes=PDF_EMBED_MAX_BYTES))
