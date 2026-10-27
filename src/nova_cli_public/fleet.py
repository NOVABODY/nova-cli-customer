"""Compatibility import for the shared customer read service."""
from nova_cli_public.reads import MODELS as ARGUMENTS
from nova_cli_public.reads import CustomerReadService as DelegatedService

__all__ = ["ARGUMENTS", "DelegatedService"]
