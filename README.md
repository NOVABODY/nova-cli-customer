# Nova CLI

The customer Nova Fora client signs in through your browser and uses the existing
customer read workflows. The CLI and local MCP share 29 named operations,
including vehicle, work-order, defect and vehicle-report reads, photo downloads,
cursor-based packages, notifications, search, team defaults, and health checks.
It does not accept passwords or service keys or expose arbitrary API commands.
Customer writes and workshop events remain pending; this is not full legacy parity.

**Private preview:** This repository remains private. Public release requires a separate decision.

**Deployment availability:** your Nova deployment must support native browser authorization and
allow your account to connect. Publishing this client does not enable that API
or approve a customer rollout. Contact your Nova administrator for availability.

## Install

Requires Python 3.11 or later and a working OS credential store.

```sh
pip install 'nova-cli @ git+https://github.com/NOVABODY/nova-cli-customer.git'
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
nova vehicle list --status grounded --json
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
pip install 'nova-cli[mcp] @ git+https://github.com/NOVABODY/nova-cli-customer.git'
nova-mcp --profile personal
```

Configure a local MCP host to launch that command over stdio. It exposes the same
customer read handlers as the CLI through named tools. Run `nova capabilities
--json` for the tool names and schemas. API responses retain the fields authorized
for your role; the client does not replace full vehicle records with a projection.
The MCP shares the public CLI's profile, credential store and refresh lock.

File tools save data under the public client data directory and return local file
paths and URIs. MCP calls allow at most 100 API reads and 10 MiB of response data;
each response is limited to 2 MiB. Photo calls allow at most 10 defect IDs, 20
photos and 100 MiB in total, with the existing 50 MiB limit per photo. Photos use
signed HTTPS URLs without Nova bearer credentials. Wait calls are limited to 25
seconds. CLI file paths, cursor options and polling controls remain available.

File tools create local files and can update a local cursor. Their MCP annotations
identify these effects. Cursors are bound to the signed-in account, organization
and connection; a new sign-in cannot reuse another account's cursor. A failed
file or stdout write does not advance the cursor. Disconnect in Nova to deny
subsequent calls, including from an already-running MCP process.

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

## Discover capabilities

Run `nova capabilities` for the full command table of contents. Agents can use
`nova capabilities --json` for arguments, schemas, examples, effects, OAuth scopes
and MCP tool references. Use `nova capabilities --command "vehicle get" --json`
to inspect one command. Discovery is offline and requires no credentials. It
does not claim that an account or deployment permits an operation.

The CLI currently provides fleet, work-order, and defect reads. Full DSP and vendor
workflow parity is not yet available.
See [customer workflow coverage](docs/CustomerParity.md) for the full inventory,
missing workflows, browser handoffs, and implementation sequence.

## Consent and legacy read commands

Fresh login requests the full vehicle read operations shown in browser consent:
`vehicles.list_full.v1` and `vehicles.get_full.v1`. Existing connections with the
older projected fleet grants are not upgraded. Sign in again to approve the full
read operations. A denial can also mean that your current account cannot read
the record; new consent does not bypass account permissions.

To request other reads, supply the complete operation list. For example:

```sh
nova auth login --operations "vehicles.list_full.v1 vehicles.get_full.v1 work_orders.list.v1 work_orders.get.v1 defects.list.v1 defects.get.v1 defects.photos.list.v1"
nova vehicle list --status all --dsp-id DSP-0001 --json
nova wo get WO-0001 --json
nova defects list --status scheduled --json
nova defect photos FD-0001 --out ./photos
nova defect pull --vehicle VAN-0001 --out ./defects.json
```

`wo` and `work-orders`, `defects`, and `notifications` retain the legacy aliases.
The legacy `defect list --status` filter runs on the returned page, as before.
Use `nova COMMAND --help` for each command's options. Capability discovery lists
required operation IDs without granting access. A list-only grant cannot read
record detail. Work-order waits and line-item reads use the work-order detail
grant; package pulls use the corresponding list grant.

The legacy read handlers and their behavioral tests were extracted from source
tree `c2298bbf8b1c17e5f520dcc3aefa5ce172ab12ec`. They run entirely inside the
public package; the private operator package is not a dependency. The shared
registry supplies CLI registration, MCP tools and capability discovery.
See [legacy parity](docs/LegacyCliParity.md) for the complete command ledger,
remaining writes and events, and explicit exclusions. Your deployment must support
the declared delegated read contracts before these operations can succeed.
