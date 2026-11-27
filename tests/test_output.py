import json

import pytest

from nova_cli_public.output import emit, humanize


@pytest.mark.parametrize(("row", "expected"), [
    ({"id": "WO-1", "status": "reported", "vehicle_grounded": True}, "vehicle_grounded=True"),
    ({"id": "WO-1", "status": "reported", "vehicle_grounded": False}, "vehicle_grounded=False"),
    ({"id": "VAN-1", "fleet_id": "NF001", "grounded": True}, "grounded=True"),
])
def test_human_list_output_shows_grounded_status(row, expected):
    assert expected in humanize({"items": [row], "total": 1})


def test_json_output_keeps_the_van_grounded_status(capsys):
    emit({"items": [{"id": "WO-1", "vehicle_grounded": True}], "total": 1}, as_json=True)
    assert json.loads(capsys.readouterr().out)["items"][0]["vehicle_grounded"] is True
