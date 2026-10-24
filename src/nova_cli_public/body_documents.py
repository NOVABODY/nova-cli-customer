"""Save the existing authorized Body PDFs to the caller's chosen file."""
import os
import re
import tempfile
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
