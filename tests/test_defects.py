import json

import pytest
from pydantic import ValidationError

from nova_cli_public import cli
from nova_cli_public.errors import ApiError
from nova_cli_public.fleet import DelegatedService


class Reader:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, query=None):
        self.calls.append((method, path, query))
        row = {
            "id": "FD-0001",
            "vehicle_id": "VAN-0001",
            "fleet_id": "TEST",
            "plate": "TEST",
            "vehicle_class": "regular_cargo_van",
            "source": "inspection",
            "part": "tire",
            "defect_type": "worn",
            "details": {},
            "reported_at": "2026-10-23T12:00:00Z",
            "created_at": "2026-10-23T12:00:00Z",
            "updated_at": "2026-10-23T12:00:00Z",
            "notes": "Visible note",
        }
        return (
            {"items": [row], "total": 1, "page": 1, "per_page": 50}
            if path.endswith("defects")
            else row
        )


def test_cli_defect_detail_preserves_server_filtered_fields(monkeypatch, capsys):
    reader = Reader()
    monkeypatch.setattr(cli, "client_from_args", lambda args: reader)
    assert cli.main(["defect", "get", "FD-0001", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["notes"] == "Visible note"
    assert reader.calls == [("GET", "/defects/FD-0001", None)]


def test_defect_list_passes_customer_filters_and_pagination():
    reader = Reader()
    result = DelegatedService(reader).run(
        "list_defects",
        {
            "vehicle_id": "VAN-0001",
            "inspection_id": "INS-0001",
            "date_from": "2026-10-23",
            "open_only": True,
            "page": 2,
            "per_page": 20,
            "tz_offset_minutes": 240,
        },
    )
    assert result["items"][0]["notes"] == "Visible note"
    query = reader.calls[0][2]
    assert query["date_from"] == "2026-10-23"
    assert (query["page"], query["per_page"], query["open_only"]) == (2, 20, True)


@pytest.mark.parametrize(
    "arguments",
    [
        {"per_page": 201},
        {"page": 0},
        {"tz_offset_minutes": 841},
        {"dsp_id": True},
        {"inspection_id": "../auth"},
        {"date_from": "2026-02-30"},
        {"date_to": "tomorrow"},
        {"unknown": "filter"},
    ],
)
def test_invalid_defect_filters_fail_before_transport(arguments):
    reader = Reader()
    with pytest.raises(ValidationError):
        DelegatedService(reader).run("list_defects", arguments)
    assert not reader.calls


@pytest.mark.parametrize("identifier", ["../vehicles", "FD-1?admin=true", "", "WO-0001"])
def test_invalid_defect_id_fails_before_transport(identifier):
    reader = Reader()
    with pytest.raises(ValidationError):
        DelegatedService(reader).run("get_defect", {"defect_id": identifier})
    assert not reader.calls


def test_malformed_defect_response_is_rejected(monkeypatch):
    reader = Reader()
    monkeypatch.setattr(reader, "request", lambda *args, **kwargs: {"id": "FD-1"})
    with pytest.raises(ApiError, match="Invalid read response"):
        DelegatedService(reader).run("get_defect", {"defect_id": "FD-1"})
