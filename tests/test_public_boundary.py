import json

import pytest

from nova_cli_public import cli, delegated
from nova_cli_public.config import ConfigStore, Profile, config_dir, data_dir
from nova_cli_public.errors import UsageError
from nova_cli_public.tokens import SERVICE_NAME


@pytest.mark.parametrize(
    "arguments",
    [
        ["admin"],
        ["api", "GET", "/vehicles"],
        ["upload"],
        ["work-order", "create"],
        ["defect", "create"],
        ["auth", "set-service-key"],
        ["auth", "login", "--email", "user@example.test"],
        ["profile", "set", "x", "--auth", "password"],
        ["profile", "set", "x", "--token-store", "file"],
    ],
)
def test_internal_commands_are_unavailable(arguments):
    with pytest.raises(SystemExit) as error:
        cli.build_parser().parse_args(arguments)
    assert error.value.code == 2


@pytest.mark.parametrize(
    "auth,storage",
    [("password", "keyring"), ("service", "keyring"), ("delegated", "file"), ("delegated", "auto")],
)
def test_legacy_auth_or_file_storage_cannot_be_loaded(auth, storage):
    with pytest.raises(UsageError):
        Profile("same", "https://nova.example/api", storage, auth)


def test_public_paths_and_keyring_do_not_reuse_internal_namespace():
    assert config_dir().name == data_dir().name == SERVICE_NAME == "nova-cli-public"


def test_internal_environment_does_not_select_public_profile(monkeypatch):
    store = ConfigStore()
    store.set_profile("public", "https://nova.example/api")
    store.set_profile("other", "https://other.example/api")
    store.use_profile("public")
    monkeypatch.setenv("NOVA_PROFILE", "other")
    monkeypatch.setenv("NOVA_API", "https://other.example/api")
    args = cli.build_parser().parse_args(["auth", "status"])
    assert cli.profile_from_args(args).name == "public"


def test_public_login_returns_no_tokens(monkeypatch, capsys):
    ConfigStore().set_profile("personal", "https://nova.example/api")
    monkeypatch.setattr(
        delegated,
        "login",
        lambda client: {"scope": "nova:read", "resource": "https://nova.example/api"},
    )
    assert cli.main(["--profile", "personal", "auth", "login", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["connection"]["scope"] == "nova:read"
    assert "access_token" not in result and "refresh_token" not in result


def test_invalid_profile_change_preserves_saved_settings():
    store = ConfigStore()
    store.set_profile("personal", "https://nova.example/api")
    before = store.load()
    with pytest.raises(UsageError):
        store.set_profile("personal", "http://localhost/api")
    assert store.load() == before


def test_removing_profile_deletes_only_public_credential_without_nested_lock(monkeypatch):
    import keyring

    values = {}
    monkeypatch.setattr(
        keyring, "get_password", lambda service, account: values.get((service, account))
    )
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, account, value: values.__setitem__((service, account), value),
    )
    monkeypatch.setattr(
        keyring, "delete_password", lambda service, account: values.pop((service, account), None)
    )
    profile = ConfigStore().set_profile("personal", "https://nova.example/api")
    bound = delegated.credential_profile(profile)
    values[(SERVICE_NAME, bound.name)] = "synthetic-public"
    values[("nova-cli", bound.name)] = "synthetic-internal"
    assert cli.main(["profile", "remove", "personal"]) == 0
    assert values == {("nova-cli", bound.name): "synthetic-internal"}
    assert "personal" not in ConfigStore().load()["profiles"]


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/assistant/vehicles"),
        ("GET", "/auth/admin"),
        ("GET", "https://other.example/api/assistant/vehicles"),
        ("GET", "//other.example/assistant/vehicles"),
        ("GET", "/assistant/vehicles/../auth/me"),
        ("POST", "/auth/service-token"),
        ("POST", "/auth/login"),
    ],
)
def test_transport_rejects_internal_or_foreign_routes_without_opening_network(method, path):
    from nova_cli_public.client import ApiClient

    class NeverOpen:
        def open(self, *args, **kwargs):
            pytest.fail("Disallowed request reached transport")

    client = ApiClient(Profile("test", "https://nova.example/api"), object(), opener=NeverOpen())
    with pytest.raises(UsageError):
        client._send(method, path)


def test_distribution_uses_nova_fora_name_and_retains_customer_entry_points():
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(__file__).parents[1] / 'pyproject.toml').read_text())['project']
    assert project['name'] == 'nova-fora-cli', 'The customer distribution must not use the unrelated nova-cli package name'
    assert project['scripts'] == {
        'nova': 'nova_cli_public.cli:main', 'nova-cli': 'nova_cli_public.cli:main',
        'nova-mcp': 'nova_cli_public.mcp:main',
    }
