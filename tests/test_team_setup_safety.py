"""Regression coverage for untrusted setup responses and invitation inputs."""
import pytest
from pydantic import ValidationError

from nova_cli_public.team_setup import Invite, result


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "http://slack.com/authorize",
    "https://slack.com.evil.test/authorize", "https://evilslack.com/authorize",
    "https://user@slack.com/authorize", "https://slack.com:444/authorize",
    "https://slack.com/" + "x" * 4096, "https://slack.com/\nsecret",
])
def test_untrusted_setup_link_is_rejected_without_disclosure(url):
    with pytest.raises(ValueError, match="Setup link not available") as error:
        result("start_slack_setup", {"authorize_url": url})
    assert url not in str(error.value)
    assert "Reintenta" in str(error.value)


@pytest.mark.parametrize("url", [
    "https://slack.com/oauth/v2/authorize?state=a%2Fb",
    "https://workspace.slack.com/authorize", "https://slack.com:443/authorize",
])
def test_trusted_setup_link_is_preserved(url):
    assert result("start_slack_setup", {"authorize_url": url}) == {"authorize_url": url}


@pytest.mark.parametrize("name", ["invite_team_member", "resend_team_invitation", "list_team_invitations"])
def test_invitation_output_allows_only_contract_fields(name):
    invitation = {"id": "INV-7", "email": "test@example.com", "status": "pending"}
    secrets = {key: "SECRET" for key in ("accept_url", "invite_url", "token", "future_link")}
    value = invitation | secrets
    expected = invitation
    if name == "list_team_invitations":
        value = {"items": [value], "total": 1} | secrets
        expected = {"items": [invitation], "total": 1}
    assert result(name, value) == expected


@pytest.mark.parametrize("fields", [
    {"role": "administrator"}, {"role": "site_admin"}, {"role": "account_manager"},
    {"email": "invalid"}, {"email": "a@@example.com"}, {"email": "a b@example.com"},
    {"station": "x" * 21},
])
def test_invalid_invite_fields_are_rejected(fields):
    with pytest.raises(ValidationError):
        Invite.model_validate({"email": "test@example.com", "role": "dsp_viewer", "org_id": 7} | fields)


@pytest.mark.parametrize("role", [
    "dsp_owner", "dsp_manager", "dsp_dispatcher", "dsp_viewer", "vendor_admin",
    "service_writer", "foreman", "technician", "vendor_viewer",
])
def test_invitable_roles_and_station_limit_are_admitted(role):
    model = Invite.model_validate({"email": "test@example.com", "role": role, "org_id": 7, "station": "x" * 20})
    assert model.role == role
    assert Invite.model_json_schema()["properties"]["role"]["enum"]


@pytest.mark.parametrize("through_cli", [False, True])
def test_list_uses_real_client_and_pending_query(monkeypatch, through_cli):
    import io
    import json
    from email.message import Message
    from urllib.parse import parse_qs, urlsplit

    from nova_cli_public import cli
    from nova_cli_public.client import ApiClient
    from nova_cli_public.config import Profile
    from nova_cli_public.team_setup import execute

    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            response = io.BytesIO(json.dumps({"items": [{"id": "INV-7", "token": "SECRET"}], "total": 1}).encode())
            response.status, response.headers = 200, Message()
            response.headers["Content-Type"] = "application/json"
            return response
    api = ApiClient(Profile("test", "https://example.com/api", "keyring"), None, opener=Opener())
    api.access_token = "synthetic"
    if through_cli:
        monkeypatch.setattr(cli, "client_from_args", lambda args: api)
        args = cli.build_parser().parse_args(["team-invitation", "list"])
        output = args.handler(args)
    else:
        output = execute(api, "list_team_invitations", {})
    assert output == {"items": [{"id": "INV-7"}], "total": 1}
    assert len(calls) == 1 and calls[0].method == "GET"
    assert urlsplit(calls[0].full_url).path == "/api/auth/invitations"
    assert parse_qs(urlsplit(calls[0].full_url).query) == {"status": ["pending"]}


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://slack.com.evil.test/authorize"])
def test_setup_dispatch_returns_safe_bilingual_link_error(url):
    from nova_cli_public.errors import ApiError
    from nova_cli_public.team_setup import execute

    class Api:
        def request(self, method, path, *, retry_auth):
            return {"authorize_url": url}
    with pytest.raises(ApiError, match="Setup link not available") as error:
        execute(Api(), "start_slack_setup", {})
    assert url not in str(error.value) and "Reintenta" in str(error.value)


@pytest.mark.parametrize("name,arguments", [
    ("invite_team_member", {"email": "test@example.com", "role": "dsp_viewer", "org_id": 7}),
    ("resend_team_invitation", {"invitation_id": "INV-7"}),
    ("revoke_team_invitation", {"invitation_id": "INV-7"}),
    ("start_slack_setup", {}), ("set_roger_intake_channel", {}),
])
def test_setup_503_write_outcome_is_unknown_without_retry(name, arguments):
    import io
    import urllib.error
    from email.message import Message

    from nova_cli_public.client import ApiClient
    from nova_cli_public.config import Profile
    from nova_cli_public.errors import ApiError
    from nova_cli_public.team_setup import execute

    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            headers = Message()
            headers["Content-Type"] = "application/json"
            raise urllib.error.HTTPError(request.full_url, 503, "unavailable", headers,
                                         io.BytesIO(b'{"detail":{"code":"provider_unavailable","message":"PRIVATE"}}'))
    api = ApiClient(Profile("test", "https://example.com/api", "keyring"), None, opener=Opener())
    api.access_token = "synthetic"
    with pytest.raises(ApiError) as error:
        execute(api, name, arguments)
    assert error.value.code == "outcome_unknown" and error.value.status == 503
    assert "Check invitations or Slack status" in str(error.value)
    assert "Consulta" in str(error.value) and "PRIVATE" not in str(error.value)
    assert len(calls) == 1
