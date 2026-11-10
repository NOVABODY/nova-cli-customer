"""Setup adapters never disclose invitation bearer links."""
from types import SimpleNamespace

import pytest

from nova_cli_public.errors import ApiError
from nova_cli_public.team_setup import MODELS, execute


class Api:
    profile = SimpleNamespace(auth="service")
    def __init__(self, value):
        self.value, self.calls = value, []
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value

@pytest.mark.parametrize("name,args,value", [
    ("list_team_invitations", {}, {"items": [{"id": "INV-7", "accept_url": "SECRET"}], "total": 1}),
    ("invite_team_member", {"email": "test@example.com", "role": "dsp_viewer", "org_id": 7}, {"id": "INV-7", "accept_url": "SECRET"}),
    ("resend_team_invitation", {"invitation_id": "INV-7"}, {"id": "INV-7", "accept_url": "SECRET"}),
])
def test_invitation_links_are_stripped(name, args, value):
    api = Api(value)
    result = execute(api, name, args)
    assert "SECRET" not in str(result)
    assert "accept_url" not in str(result)
    assert len(api.calls) == 1

def test_slack_url_is_unchanged_and_start_is_not_retried():
    url = "https://slack.com/oauth/v2/authorize?state=a%2Fb&scope=x"
    api = Api({"authorize_url": url, "token": "SECRET"})
    assert execute(api, "start_slack_setup", {})["authorize_url"] == url
    assert api.calls == [("GET", "/slack/oauth/initiate", {"retry_auth": False})]

@pytest.mark.parametrize("args,body", [({}, {}), ({"intake_channel_id": None}, {"intake_channel_id": None}), ({"intake_channel_id": ""}, {"intake_channel_id": ""}), ({"intake_channel_id": "C123"}, {"intake_channel_id": "C123"})])
def test_channel_omitted_clear_and_set_are_distinct(args, body):
    api = Api({"intake_channel_id": None})
    execute(api, "set_roger_intake_channel", args)
    assert api.calls[0][2]["json_body"] == body

@pytest.mark.parametrize("status", [400,401,403,404,409,422,429,503])
def test_error_status_and_structured_code_survive_without_retry(status):
    api = Api(ApiError("PRIVATE", status=status, code="slack_setup_reconnect_required" if status == 401 else "test_code"))
    with pytest.raises(ApiError) as error:
        execute(api, "start_slack_setup", {})
    assert error.value.status == status
    assert error.value.code == ("slack_setup_reconnect_required" if status == 401 else "test_code")
    assert "PRIVATE" not in str(error.value)
    assert len(api.calls) == 1

def test_only_seven_setup_operations():
    assert len(MODELS) == 7
    assert not any(word in name for name in MODELS for word in ("callback", "disconnect", "token"))

CASES = [
    (["team-invitation", "list"], "list_team_invitations", {}, "GET", "/auth/invitations", {"items": [{"id": "INV-7", "accept_url": "SECRET"}], "total": 1}),
    (["team-invitation", "invite", "--email", "test@example.com", "--role", "dsp_viewer", "--org-id", "7"], "invite_team_member", {"email": "test@example.com", "role": "dsp_viewer", "org_id": 7}, "POST", "/auth/invitations", {"id": "INV-7", "accept_url": "SECRET"}),
    (["team-invitation", "resend", "INV-7"], "resend_team_invitation", {"invitation_id": "INV-7"}, "POST", "/auth/invitations/INV-7/resend", {"id": "INV-7", "accept_url": "SECRET"}),
    (["team-invitation", "revoke", "INV-7"], "revoke_team_invitation", {"invitation_id": "INV-7"}, "DELETE", "/auth/invitations/INV-7", None),
    (["roger", "status"], "get_slack_status", {}, "GET", "/slack/installation/status", {"installed": False}),
    (["roger", "start"], "start_slack_setup", {}, "GET", "/slack/oauth/initiate", {"authorize_url": "https://slack.com/authorize?state=a%2Fb"}),
    (["roger", "channel", "--intake-channel-id", ""], "set_roger_intake_channel", {"intake_channel_id": ""}, "POST", "/slack/channels", {"intake_channel_id": None}),
]


@pytest.mark.parametrize("argv,name,arguments,method,path,value", CASES)
def test_cli_and_sdk_dispatch_all_setup_operations(monkeypatch, argv, name, arguments, method, path, value):
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from nova_cli_public import cli
    from nova_cli_public.mcp import create_server
    from nova_cli_public.reads import CustomerReadService
    from nova_cli_public.team_setup import WRITES, result
    api = Api(value)
    monkeypatch.setattr(cli, "client_from_args", lambda args: api)
    parsed = cli.build_parser().parse_args(argv)
    expected = result(name, value)
    assert parsed.handler(parsed) == expected
    async def check():
        async with create_connected_server_and_client_session(create_server(CustomerReadService(api))) as sdk:
            tools = {t.name: t for t in (await sdk.list_tools()).tools}
            assert set(MODELS) <= set(tools)
            assert tools[name].annotations.readOnlyHint is (name not in WRITES)
            assert not any(word in t for t in tools if t in MODELS for word in ("callback", "disconnect", "token"))
            response = await sdk.call_tool(name, arguments)
            assert not response.isError and response.structuredContent == expected
    asyncio.run(check())
    assert len(api.calls) == 2
    assert all(call[:2] == (method, path) for call in api.calls)
    assert api.calls[0] == api.calls[1]


@pytest.mark.parametrize("name,arguments", [
    ("invite_team_member", {"email": "a@b.com", "role": "dsp_viewer", "org_id": "7"}),
    ("resend_team_invitation", {"invitation_id": "../7"}),
    ("start_slack_setup", {"callback": "evil"}),
    ("invite_team_member", {"email": "a@b.com", "role": "dsp_viewer", "org_id": 7, "org_type": "dsp"}),
])
def test_invalid_setup_input_never_sends(name, arguments):
    from pydantic import ValidationError
    api = Api({})
    with pytest.raises(ValidationError):
        execute(api, name, arguments)
    assert api.calls == []


@pytest.mark.parametrize("status,code", [(401, "slack_setup_reconnect_required"), (503, "provider_unavailable")])
def test_customer_transport_does_not_retry_setup_get_or_lose_code(monkeypatch, status, code):
    from nova_cli_public.client import ApiClient
    from nova_cli_public.config import Profile
    api = ApiClient(Profile("test", "https://example.com/api", "keyring"), None)
    api.access_token = "synthetic"
    calls = []
    def send(*args, **kwargs):
        calls.append(args)
        raise ApiError("PRIVATE", status=status, code=code)
    monkeypatch.setattr(api, "_send", send)
    with pytest.raises(ApiError) as error:
        execute(api, "start_slack_setup", {})
    assert error.value.code == ("outcome_unknown" if status == 503 else code)
    assert error.value.status == status
    assert len(calls) == 1


def test_customer_routes_admit_setup_get_as_write_only():
    from nova_cli_public.read_routes import admitted_read
    from nova_cli_public.write_routes import admitted_write
    assert not admitted_read("/slack/oauth/initiate")
    assert admitted_write("GET", "/slack/oauth/initiate")
    for path in ("/slack/oauth/callback", "/slack-installations", "/slack/disconnect"):
        assert not admitted_read(path)
        assert not admitted_write("GET", path)
        assert not admitted_write("POST", path)


@pytest.mark.parametrize("status,code", [(401, "slack_setup_reconnect_required"), (403, "invitation_platform_connection_denied"), (503, "provider_unavailable")])
def test_cli_errors_show_status_code_and_safe_next_step(monkeypatch, capsys, status, code):
    import json

    from nova_cli_public import cli
    api = Api(ApiError("PRIVATE", status=status, code=code))
    monkeypatch.setattr(cli, "client_from_args", lambda args: api)
    assert cli.main(["--json", "roger", "start"]) == 1
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["status"] == status and error["code"] == code
    assert "PRIVATE" not in error["message"]
    if status == 401:
        assert "Refresh or reconnect" in error["message"]
