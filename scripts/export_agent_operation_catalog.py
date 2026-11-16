"""Export reviewed operation requirements for the issuer's registration checks.

Run with the development environment. Merge native_operations into
nova-john-app/test-contracts/customer-agent-operations.json in the coordinated PR.
This catalog describes supported tools; it never grants account permissions.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_cli_public.delegated import OPERATIONS
from nova_cli_public.reads import BY_TOOL

print(json.dumps({"native_operations": {
    operation: sorted(name for name, entry in BY_TOOL.items() if entry["grant"] == operation)
    for operation in sorted(OPERATIONS)
}}, indent=2))
