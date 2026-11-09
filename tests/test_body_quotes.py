import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from nova_cli_public import body_quotes as quotes
from nova_cli_public.errors import ApiError

DATA = {
    "based_on_scope_revision": 2,
    "scope_mode": "guided",
    "body_labor_rate_cents": 8500,
    "line_items": [
        {
            "description": "Repair panel",
            "body_labor_hours": 1.5,
            "parts_cents": 2500,
            "linked_components": ["Door"],
        }
    ],
    "issue_resolutions": [{"index": 0, "outcome": "covered", "line_position": 0}],
}
ARGS = {"request_ref": "BRR-7", "data": DATA}
CASES = [
    (quotes.NAMES[0], {}, "GET", "/body-repair/repair-leads", None, {"items": []}),
    (
        quotes.NAMES[1],
        {"request_ref": "BRR-7"},
        "GET",
        "/body-repair/requests/BRR-7/quotes",
        None,
        {"request_id": "BRR-7", "quotes": []},
    ),
    (
        quotes.NAMES[2],
        {"request_ref": "BRR-7", "based_on_scope_revision": 2, "confirm": True},
        "POST",
        "/body-repair/requests/BRR-7/scope/read",
        {"based_on_scope_revision": 2, "confirm": True},
        {"scope_revision": 2, "last_viewed_at": "2026-11-09T12:00:00Z"},
    ),
    (
        quotes.NAMES[3],
        ARGS,
        "POST",
        "/body-repair/requests/BRR-7/quotes",
        DATA,
        {
            "quote": {
                "id": "BRQ-3",
                "request_id": "BRR-7",
                "status": "active",
                "vendor_raw_cents": 15250,
            }
        },
    ),
    (
        quotes.NAMES[4],
        {"request_ref": "BRR-7", "quote_id": "BRQ-3"},
        "POST",
        "/body-repair/requests/BRR-7/quotes/BRQ-3/withdraw",
        None,
        {"request": {"id": "BRR-7"}, "quote_id": "BRQ-3"},
    ),
]


@pytest.mark.parametrize("name,arguments,method,path,body,result", CASES)
def test_exact_wire_payload_and_no_implicit_scope_confirmation(
    name, arguments, method, path, body, result
):
    api = SimpleNamespace(request=Mock(return_value=result))
    assert quotes.execute(api, name, arguments) == result
    api.request.assert_called_once_with(
        method, path, **({"json_body": body, "retry_auth": False} if name in quotes.WRITES else {})
    )


@pytest.mark.parametrize(
    "data",
    [
        {**DATA, "unknown": True},
        {**DATA, "based_on_scope_revision": "2"},
        {**DATA, "based_on_scope_revision": True},
        {**DATA, "line_items": [{"unknown": 1}]},
        {**DATA, "line_items": [{"parts_cents": -1}]},
        {**DATA, "line_items": [{"body_labor_hours": float("nan")}]},
        {**DATA, "issue_resolutions": [{"index": 0, "outcome": "declined"}]},
        {**DATA, "issue_resolutions": [{"index": 0, "outcome": "covered"}]},
        {
            **DATA,
            "issue_resolutions": [
                {"index": 0, "outcome": "declined", "decline_reason": "not_found", "extra": 1}
            ],
        },
        {**DATA, "repair_start_date": "2026-02-30"},
        {**DATA, "line_items": [{}] * 401},
    ],
)
def test_strict_submit_rejects_invalid_input_before_api(data):
    api = SimpleNamespace(request=Mock())
    with pytest.raises(ValidationError):
        quotes.execute(api, quotes.NAMES[3], {**ARGS, "data": data})
    api.request.assert_not_called()


@pytest.mark.parametrize("confirm", [None, False, 1, "true"])
def test_confirmation_requires_explicit_boolean_true(confirm):
    with pytest.raises(ValidationError):
        quotes.Confirm.model_validate(
            {"request_ref": "BRR-7", "based_on_scope_revision": 2, "confirm": confirm}
        )


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429])
def test_api_refusals_keep_safe_code_and_guidance_without_raw_detail(status):
    failure = ApiError(
        "Refused",
        status=status,
        code="scope_stale",
        detail={"current_revision": 3},
        request_id="req-1",
    )
    api = SimpleNamespace(request=Mock(side_effect=failure))
    with pytest.raises(ApiError) as caught:
        quotes.execute(api, quotes.NAMES[3], ARGS)
    assert caught.value.status == status and caught.value.code == "scope_stale"
    assert caught.value.detail is None
    assert "Refused" not in str(caught.value)
    assert quotes.GUIDANCE[status] in str(caught.value)
    assert api.request.call_count == 1


@pytest.mark.parametrize(
    "failure", [None, {}, {"quote": {}}, ApiError("lost"), ApiError("failed", status=503)]
)
def test_unknown_write_never_retries(failure):
    api = SimpleNamespace(
        request=Mock(side_effect=failure)
        if isinstance(failure, Exception)
        else Mock(return_value=failure)
    )
    with pytest.raises(ApiError) as caught:
        quotes.execute(api, quotes.NAMES[3], ARGS)
    assert caught.value.code == "outcome_unknown" and api.request.call_count == 1


def test_cli_capabilities_and_stdio_use_the_same_closed_schema(monkeypatch):
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public import cli, legacy_reads
    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import MODELS, CustomerReadService

    result = CASES[3][-1]
    api = SimpleNamespace(
        request=Mock(return_value=result), profile=SimpleNamespace(auth="delegated")
    )
    monkeypatch.setattr(legacy_reads, "client_from_args", lambda args: api)
    args = cli.build_parser().parse_args(
        ["body-repair", "submit-quote", "BRR-7", "--data", json.dumps(DATA)]
    )
    assert args.handler(args) == result
    assert MODELS[quotes.NAMES[3]] is quotes.Submit

    async def check():
        async with create_connected_server_and_client_session(
            create_server(CustomerReadService(api))
        ) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            assert set(quotes.NAMES) <= tools.keys()
            assert not tools[quotes.NAMES[3]].annotations.readOnlyHint
            assert tools[quotes.NAMES[0]].annotations.readOnlyHint
            response = await sdk.call_tool(quotes.NAMES[3], ARGS)
            assert not response.isError and response.structuredContent == result
            invalid = await sdk.call_tool(quotes.NAMES[3], {**ARGS, "unknown": True})
            assert invalid.isError

    asyncio.run(check())
    assert api.request.call_count == 2


@pytest.mark.parametrize("name,arguments,method,path,body,result", CASES)
def test_real_customer_transport_admits_only_the_named_contract(
    monkeypatch, name, arguments, method, path, body, result
):
    from nova_cli_public.capabilities import manifest
    from nova_cli_public.cli import build_parser
    from nova_cli_public.client import ApiClient
    from nova_cli_public.config import Profile

    client = ApiClient(Profile("test", "https://nova.example/api", "keyring", "delegated"), Mock())
    client.access_token = "synthetic-access"
    send = Mock(return_value=SimpleNamespace(body=result))
    monkeypatch.setattr(client, "_send", send)
    assert quotes.execute(client, name, arguments) == result
    assert send.call_count == 1
    entry = next(row for row in manifest(build_parser())["commands"] if row.get("mcp_tool") == name)
    assert entry["required_operation"] == quotes.GRANTS[name]
    assert any(row["method"] == method for row in entry["api_routes"])


def test_numeric_quote_reference_accepts_canonical_withdrawal_receipt():
    result = {"request": {"id": "BRR-7"}, "quote_id": "BRQ-00003"}
    api = SimpleNamespace(request=Mock(return_value=result))
    assert quotes.execute(api, quotes.NAMES[4], {"request_ref": "BRR-7", "quote_id": "3"}) == result


def test_confirmation_cannot_succeed_for_another_scope_revision():
    api = SimpleNamespace(
        request=Mock(return_value={"scope_revision": 3, "last_viewed_at": "2026-11-09T12:00:00Z"})
    )
    with pytest.raises(ApiError) as caught:
        quotes.execute(
            api,
            quotes.NAMES[2],
            {"request_ref": "BRR-7", "based_on_scope_revision": 2, "confirm": True},
        )
    assert caught.value.code == "outcome_unknown" and api.request.call_count == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 503])
def test_mcp_returns_safe_code_and_actionable_guidance(status):
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    api = SimpleNamespace(
        request=Mock(
            side_effect=ApiError(
                "Refused", status=status, code="scope_stale", detail={"current_revision": 3}
            )
        ),
        profile=SimpleNamespace(auth="service"),
    )
    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService

    server = create_server(CustomerReadService(api))

    async def check():
        async with create_connected_server_and_client_session(server) as sdk:
            response = await sdk.call_tool(quotes.NAMES[3], ARGS)
            assert response.isError
            assert response.structuredContent["error"]["code"] == (
                "outcome_unknown" if status == 503 else "scope_stale"
            )
            assert (
                quotes.UNKNOWN if status == 503 else quotes.GUIDANCE[status]
            ) in response.content[0].text
            if status < 500:
                assert "detail" not in response.structuredContent["error"]

    asyncio.run(check())
    assert api.request.call_count == 1


@pytest.mark.parametrize("field,value", [
    ("grade_days", {}),
    ("line_key", "client-key"),
    ("origin", "client"),
    ("added_at", "2026-11-09T12:00:00Z"),
])
def test_submit_refuses_unsupported_and_server_stamped_fields(field, value):
    data = {"based_on_scope_revision": 2}
    if field == "grade_days":
        data[field] = value
    else:
        data["line_items"] = [{field: value}]
    with pytest.raises(ValidationError):
        quotes.Submit.model_validate({"request_ref": "BRR-7", "data": data})


@pytest.mark.parametrize("item", [True, 1.5, "1", {}, [], None])
def test_pave_item_numbers_require_integers(item):
    with pytest.raises(ValidationError):
        quotes.Line.model_validate({"pave_item_nos": [item]})


def test_pave_item_numbers_accept_integer_references():
    assert quotes.Line.model_validate({"pave_item_nos": [1, 2]}).pave_item_nos == [1, 2]


@pytest.mark.parametrize("write,status,malformed", [
    (False, None, False), (False, 503, False), (False, 418, False),
    (False, None, True), (True, 418, False), (True, 503, False),
    (True, None, False), (True, None, True),
])
def test_mcp_unknown_outcome_only_for_uncertain_writes(write, status, malformed):
    name = quotes.NAMES[3] if write else quotes.NAMES[1]
    arguments = ARGS if write else {"request_ref": "BRR-7"}
    api = SimpleNamespace(request=Mock(return_value={}) if malformed else Mock(
        side_effect=ApiError("PRIVATE", status=status, code="bad\x1bcode", detail={"secret": "PRIVATE"})
    ))
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService

    async def call():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            return await sdk.call_tool(name, arguments)

    response = asyncio.run(call())
    assert response.isError
    assert (quotes.UNKNOWN in response.content[0].text) is (write and (status in (None, 503)))
    assert "PRIVATE" not in str(response) and "bad" not in str(response)
    assert "detail" not in response.structuredContent["error"]


@pytest.mark.parametrize("code", ["x" * 81, "non_ascii_é", "bad.code", "bad\ncode"])
def test_quote_errors_refuse_unbounded_or_non_ascii_codes(code):
    api = SimpleNamespace(request=Mock(side_effect=ApiError("PRIVATE", status=409, code=code)))
    with pytest.raises(ApiError) as caught:
        quotes.execute(api, quotes.NAMES[3], ARGS)
    assert caught.value.code == "quote_http_409"


def test_quote_tool_descriptions_preserve_complete_bilingual_text():
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService

    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(Mock()))) as sdk:
            tools = {tool.name: tool for tool in (await sdk.list_tools()).tools}
            for entry in quotes.COMMANDS:
                assert tools[entry["tool"]].description == entry["description"]

    asyncio.run(check())
