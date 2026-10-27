import pytest

from nova_cli_public import cli
from nova_cli_public.errors import UsageError
from nova_cli_public.reads import CustomerReadService


class Client:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs["json_body"]))
        return {"id": "WO-1"}


def test_cli_and_local_mcp_change_visit_defects():
    direct, local = Client(), Client()
    args = cli.build_parser().parse_args(
        [
            "work-order",
            "schedule",
            "WO-1",
            "--include-defect-id",
            "2",
            "--include-defect-id",
            "3",
            "--exclude-defect-id",
            "4",
        ]
    )
    args._client = direct
    args.handler(args)
    CustomerReadService(local).run(
        "schedule_work_order",
        {
            "wo_id": "WO-1",
            "include_defect_id": [2, 3],
            "exclude_defect_id": [4],
        },
    )
    assert (
        direct.calls
        == local.calls
        == [
            (
                "POST",
                "/work-orders/WO-1/schedule",
                {"include_defect_ids": [2, 3], "exclude_defect_ids": [4]},
            )
        ]
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"include_defect_id": [1, 1]},
        {"include_defect_id": [0]},
        {"exclude_defect_id": [-1]},
        {"include_defect_id": [1], "exclude_defect_id": [1]},
        {"include_defect_id": list(range(1, 102))},
    ],
)
def test_local_mcp_rejects_invalid_visit_composition_before_request(fields):
    client = Client()
    with pytest.raises(UsageError):
        CustomerReadService(client).run("schedule_work_order", {"wo_id": "WO-1", **fields})
    assert client.calls == []

