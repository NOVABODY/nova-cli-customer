# Nova CLI

The public Nova Fora client signs in through your browser and reads the fleet
vehicles your account can access. This initial version supports two operations:
list vehicles and read one vehicle. It does not accept passwords or service keys,
change fleet records, or provide arbitrary API or administrator commands.

**Preview:** your Nova deployment must support native browser authorization and
allow your account to connect. Publishing this client does not enable that API
or approve a customer rollout. Contact your Nova administrator for availability.

## Install

Requires Python 3.11 or later and a working OS credential store.

```sh
pip install 'nova-cli @ git+https://github.com/NOVABODY/nova-cli.git'
nova --help
```

This is a source install. No package-registry release is implied. If you used the
older private operator package named `nova-cli`, replace it with the private
`nova-cli-internal` package before installing this public package. Update operator
scripts to `nova-internal`; `nova` now selects this public client. Do not copy
internal profiles or credentials. The private repository's migration guide has
the internal installation steps.

## Use

```sh
nova profile set personal --api https://YOUR_NOVA_HOST/api
nova --profile personal auth login
nova vehicle list --grounded --json
nova vehicle get VAN-0001 --json
nova auth status
nova auth refresh
nova auth logout
```

Login opens Nova in your browser. Check the account and permissions, then approve
or decline. The client uses S256 PKCE and a bound local callback. Refresh tokens
stay in the OS credential store; access tokens stay in process memory. No file
credential fallback is available. Unlock your OS credential store if access fails.

`auth status` reports local credential presence, not server verification.
`auth logout` removes the local credential. To revoke the connection on the
server, disconnect it in Nova account settings. `profile remove NAME` also
removes only the local profile and its credential. Use a separate profile for
each Nova host. `NOVA_PUBLIC_PROFILE` can select a saved public profile.

## Local MCP

```sh
pip install 'nova-cli[mcp] @ git+https://github.com/NOVABODY/nova-cli.git'
nova-mcp --profile personal
```

Configure a local MCP host to launch that command over stdio. It exposes only
`list_vehicles` and `get_vehicle`, with typed arguments and outputs. It shares the
public CLI's profile, credential store and refresh lock. There is no hosted HTTP
server, widget, password login or service-account mode in this package. Disconnect
in Nova to deny subsequent calls, including from an already-running MCP process.

## Separation from the private operator CLI

| Boundary | Public client | Private operator client |
| --- | --- | --- |
| Distribution | `nova-cli` | `nova-cli-internal` |
| Command | `nova` / `nova-cli` | `nova-internal` |
| Python package | `nova_cli_public` | `nova_cli` |
| Local MCP | `nova-mcp` | `nova-internal-mcp` |
| Config/data/keyring/lock namespace | `nova-cli-public` | legacy `nova-cli` |
| Profile environment | `NOVA_PUBLIC_PROFILE` | `NOVA_PROFILE` |

The public client does not read internal profiles, credentials or environment
selectors. Both packages can coexist. This is an accidental-use boundary; the
API remains responsible for authorization on every request.

## Development

```sh
uv sync --frozen --extra dev
uv run ruff check .
uv run pytest -q
uv build
```

Tests use synthetic data and credentials. They exercise the real loopback callback
and MCP SDK stdio, credential rotation and failure handling, route/argument
restrictions and response projections. They do not prove customer activation or
compatibility with every hosted assistant.
