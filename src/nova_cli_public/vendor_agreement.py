"""Read organization agreement status; acceptance requires personal browser signing."""
from pydantic import BaseModel, ConfigDict

from nova_cli_public import legacy_reads
from nova_cli_public.errors import ApiError


class Status(BaseModel):
    model_config = ConfigDict(strict=True)
    required: bool
    version_label: str | None
    review_url: str | None


def run(args):
    value = legacy_reads.client_from_args(args).request('GET', '/terms/contract/vendor/status')
    try:
        return Status.model_validate(value).model_dump()
    except ValueError:
        raise ApiError('Invalid agreement status. / Estado del contrato no válido.') from None


COMMANDS = [{
    'command': 'vendor-agreement status', 'tool': 'get_vendor_agreement_status',
    'grant': 'vendor_agreement.status.get.v1',
    'description': 'Read your organization’s agreement status. A vendor administrator must sign at review_url. / Consulte el estado del contrato de su organización. Un administrador del proveedor debe firmar en review_url.',
    'arguments': [], 'groups': [], 'handler': run,
}]
