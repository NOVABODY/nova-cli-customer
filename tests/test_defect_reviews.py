import pytest
from pydantic import ValidationError

from nova_cli_public import cli, legacy_reads
from nova_cli_public.read_routes import READ_ROUTES
from nova_cli_public.reads import CustomerReadService
from nova_cli_public.write_routes import WRITE_ROUTES


class Client:
    def __init__(self):
        self.calls = []
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"items": []}

@pytest.mark.parametrize("action,tool,arguments,path,kwargs", [
    ("queue", "list_defect_review_queue", {}, "/defect-reviews/queue", {"query": {"limit": 50, "offset": 0}}),
    ("history", "list_defect_reviews", {"defect_id": "FD-1"}, "/defect-reviews/defect/FD-1", {}),
    ("approve", "approve_defect_review", {"defect_id": "FD-1", "external_vendor_id": 3, "additional_defect_ids": ["FD-2"]}, "/defect-reviews/defect/FD-1/approve", {"json_body": {"external_vendor_id": 3, "additional_defect_ids": ["FD-2"]}}),
    ("reject", "reject_defect_review", {"defect_id": "FD-1", "reject_reason_code": "duplicate"}, "/defect-reviews/defect/FD-1/reject", {"json_body": {"reject_reason_code": "duplicate"}}),
])
def test_cli_and_mcp_send_same_native_review_request(monkeypatch, action, tool, arguments, path, kwargs):
    client = Client()
    monkeypatch.setattr(legacy_reads, "client_from_args", lambda args: client)
    argv = ["defect-review", action]
    if "defect_id" in arguments:
        argv.append(arguments["defect_id"])
    for key, value in arguments.items():
        if key != "defect_id":
            for item in value if isinstance(value, list) else [value]:
                argv += ["--" + key.replace("_", "-"), str(item)]
    args = cli.build_parser().parse_args(argv)
    args.handler(args)
    CustomerReadService(client).run(tool, arguments)
    assert client.calls == [("POST" if action in ("approve", "reject") else "GET", path, kwargs)] * 2

@pytest.mark.parametrize("tool,args", [
    ("list_defect_review_queue", {"limit": 201}),
    ("list_defect_review_queue", {"dsp_id": "DSP-0"}),
    ("approve_defect_review", {"defect_id": "FD-0"}),
    ("approve_defect_review", {"defect_id": "FD-2147483648"}),
    ("approve_defect_review", {"defect_id": "1" * 101}),
    ("approve_defect_review", {"defect_id": "FD-1", "additional_defect_ids": ["FD-0"]}),
    ("list_defect_review_queue", {"offset": -1}),
    ("approve_defect_review", {"defect_id": "../1"}),
    ("approve_defect_review", {"defect_id": "FD-1", "external_vendor_id": 0}),
    ("reject_defect_review", {"defect_id": "FD-1", "reason": "x" * 501}),
    ("approve_defect_review", {"defect_id": "FD-1", "additional_defect_ids": ["FD-1"] * 101}),
    ("approve_defect_review", {"defect_id": "FD-1", "unknown": True}),
])
def test_invalid_review_arguments_do_not_call_server(tool, args):
    client = Client()
    with pytest.raises(ValidationError):
        CustomerReadService(client).run(tool, args)
    assert not client.calls

def test_review_routes_require_distinct_operation_grants():
    assert READ_ROUTES[r"/defect-reviews/queue"] == "defect_reviews.queue.list.v1"
    assert WRITE_ROUTES[("POST", r"/defect-reviews/defect/(?:FD-)?[0-9]{1,14}/approve")] == "defect_reviews.approve.v1"
