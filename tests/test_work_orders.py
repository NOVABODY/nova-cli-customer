import pytest

from nova_cli_public import cli
from nova_cli_public.fleet import DelegatedService


class Reader:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, query=None):
        self.calls.append((method, path, query))
        row = {
            "id": "WO-0001",
            "status": "reported",
            "vehicle_id": 1,
            "dsp_id": 2,
            "vendor_workshop_id": 3,
            "notes": [{"text": "Visible note"}],
        }
        return {"items": [row], "total": 1} if path.endswith("work-orders") else row


def test_cli_work_order_read_preserves_server_filtered_detail(monkeypatch, capsys):
    reader = Reader()
    monkeypatch.setattr(cli, "client_from_args", lambda args: reader)
    assert cli.main(["work-order", "get", "WO-0001", "--json"]) == 0
    assert "Visible note" in capsys.readouterr().out
    assert reader.calls == [("GET", "/work-orders/WO-0001", None)]


@pytest.mark.parametrize(
    "arguments",
    [
        {"limit": 501},
        {"offset": -1},
        {"scheduled_within_hours": 0},
        {"unknown": "filter"},
        {"dsp_id": True},
    ],
)
def test_invalid_work_order_filters_do_not_send_request(arguments):
    reader = Reader()
    with pytest.raises(ValueError):
        DelegatedService(reader).run("list_work_orders", arguments)
    assert reader.calls == []


@pytest.mark.parametrize("identifier", ["../vehicles", "WO-1?x=1", "https://example.test", ""])
def test_invalid_work_order_id_does_not_send_request(identifier):
    reader = Reader()
    with pytest.raises(ValueError):
        DelegatedService(reader).run("get_work_order", {"work_order_id": identifier})
    assert reader.calls == []


def test_work_order_list_applies_filters_without_discarding_server_fields():
    reader = Reader()
    result = DelegatedService(reader).run(
        "list_work_orders", {"status": "scheduled", "scheduled": False, "dsp_id": "DSP-0001"}
    )
    assert result["items"][0]["notes"] == [{"text": "Visible note"}]
    assert reader.calls[0][2]["scheduled"] is False
    assert reader.calls[0][2]["status"] == "scheduled"

    assert reader.calls[0][2]["dsp_id"] == "DSP-0001"


def test_selected_workshops_reach_cli_and_local_mcp_transport(monkeypatch, capsys):
    reader = Reader()
    monkeypatch.setattr(cli, 'client_from_args', lambda args: reader)
    assert cli.main(['work-order', 'list', '--vendor-workshop-ids', 'VW-1,2', '--json']) == 0
    capsys.readouterr()
    assert reader.calls[-1][2]['vendor_workshop_ids'] == 'VW-1,2'
    DelegatedService(reader).run('list_work_orders', {'vendor_workshop_ids': '1,2'})
    assert reader.calls[-1][2]['vendor_workshop_ids'] == '1,2'


@pytest.mark.parametrize('tool,arguments,path,payload', [
    ('set_work_order_assignment', {'wo_id': 'WO-1', 'proposed_workshop_id': 7}, '/work-orders/WO-1/assignment', {'proposed_workshop_id': 7}),
    ('schedule_work_order', {'wo_id': 'WO-1', 'vendor_workshop_id': 7, 'ro_number': 'WEST-1'}, '/work-orders/WO-1/schedule', {'vendor_workshop_id': 7, 'ro_number': 'WEST-1'}),
])
def test_intake_selection_reaches_local_mcp_write_transport(tool, arguments, path, payload):
    from unittest.mock import create_autospec

    from nova_cli_public.client import ApiClient

    client = create_autospec(ApiClient, instance=True)
    client.request.return_value = {'id': 'WO-1', 'status': 'processing'}
    DelegatedService(client).run(tool, arguments)
    client.request.assert_called_once_with('POST', path, json_body=payload)
