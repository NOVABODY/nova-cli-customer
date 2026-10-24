# Nova CLI

The customer Nova Fora client signs in through your browser and uses the existing
customer workflows. The CLI and local MCP share 58 named operations,
including vehicle, work-order, defect and vehicle-report reads, photo downloads,
cursor-based packages, notifications, search, team defaults, and health checks.
It does not accept passwords or service keys or expose arbitrary API commands.
The named customer write and photo-upload commands require explicit write consent.
Workshop event tools provide durable delivery with explicit local acknowledgment.

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
customer handlers as the CLI through named tools. Run `nova capabilities
--json` for the tool names and schemas. API responses retain the fields authorized
for your role; the client does not replace full vehicle records with a projection.
The MCP shares the public CLI's profile, credential store and refresh lock.

File tools save data under the public client data directory and return local file
paths and URIs. Record-read MCP calls allow at most 100 API reads and 10 MiB of response data;
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

The CLI provides named customer reads, changes, uploads, and workshop events.
The parity ledger records implementation and verification status.
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
verification evidence and explicit exclusions. Your deployment must
support the declared delegated contracts before these operations can succeed.

## Customer changes and photo uploads

Read-only consent is still the default. Request the combined scope and each named
operation before using a change command. Browser consent and current account
permissions must both allow the operation. For example:

```sh
nova auth login --scope "nova:read nova:write" --operations "work_orders.get.v1 work_orders.schedule.update.v1 uploads.presign.v1 defects.photos.create.v1"
nova work-order schedule WO-0001 --scheduled-at 2026-10-26T09:00:00-04:00
nova upload photo ./damage.jpg --kind defect --parent-id FD-0001 --commit
```

Report a catalog defect with `defect create` (`create_defect` in local MCP):

```sh
nova auth login --scope "nova:read nova:write" --operations "defect_catalog.get.v1 defects.create.v1 uploads.presign.v1 defects.photos.create.v1"
nova defect create --vehicle-id VAN-0001 --source maintenance_request --part headlight --defect-type not_working --vendor-workshop-id 3
```

Use the catalog for part, type and position values. `--details` accepts a JSON
object string up to 64 KiB; the API validates its catalog-specific fields. The
reporting user is your account. Reporter and mileage overrides are not accepted.
An inspection source requires your open inspection. Choose one internal or
external shop; routing still depends on current relationships and permissions.
After creation, use the returned defect ID with the photo-upload command above.
Creation itself does not upload a photo. The API must support `defects.create.v1`;
existing consent does not expand automatically.

The upload grant permits the existing upload kinds. `--commit` needs a separate
parent-photo operation: `defects.photos.create.v1`, `inspections.photos.create.v1`,
or `vehicle_reports.photos.create.v1`. Signed upload requests send no Nova bearer
token and do not follow redirects. Photos are limited to 50 MiB.

Change requests are sent once. An expired cached token, a timeout, or another error
does not trigger an automatic retry. Server errors and redirects after a change
request also have an unknown outcome. The client can refresh before the first send.
A defect report must identify the expected vehicle and catalog fields in its
success response; an incomplete or mismatched response has an unknown outcome.
An `outcome_unknown` error means the response was lost; check the record before you
try again. Business rejections retain their details, including version conflicts,
mileage requirements, and validation failures. Existing duplicate and concurrency
rules remain owned by each API operation.

MCP exposes the same named commands and reports their write effects. It does not
expose a generic request tool. File arguments must name files; MCP does not read
stdin. Capability discovery shows required scopes, operation IDs, and conditional
photo-commit grants. Discovery does not establish permission to perform a change.


## Workshop events

Event commands require `nova:read` and the `workshop_events.list.v1` operation.
The account must be able to manage the selected workshop. Obtain a head cursor,
read and reconcile the work-order snapshot, then initialize a private local inbox:

```sh
nova auth login --operations "workshop_events.list.v1 work_orders.list.v1 work_orders.get.v1"
nova events head --vendor-workshop-id 3 --json
# Reconcile the snapshot before saving its bootstrap cursor.
nova events init --vendor-workshop-id 3 --state-file ./events.sqlite --after CURSOR --snapshot-reconciled
nova events watch --vendor-workshop-id 3 --state-file ./events.sqlite
nova events ack --vendor-workshop-id 3 --state-file ./events.sqlite EVENT_CURSOR
```

`watch` emits NDJSON. Each page and resume cursor are committed together before
output. A failed output can therefore leave the cursor advanced with the accepted
events still pending; restart to replay them. Acknowledge each event only after
processing it. Events are invalidation signals; use the record tools to read the
current state. Empty long polls produce no output. `--once` reads one page without
retrying; continuous watch retries transient read failures up to five times.
`--max-pending` stops new reads until accepted events are acknowledged.

The inbox is bound to the API, profile, account, organization, connection, and
workshop. Token refresh retains it; a new login requires a new inbox. Current
server access is checked before replay or acknowledgment. An expired cursor
returns `cursor_expired` and `reset_cursor`. Reconcile a new snapshot, process and
acknowledge pending events, then use `events init --reset --snapshot-reconciled`
with the returned cursor. Reset never discards pending events.

MCP exposes `events_head`, `events_init`, `events_watch`, and `events_ack`. It uses
managed inboxes under the public client data directory, without caller-provided
file paths. Each watch call fetches at most one page of 500 events, waits at most
25 seconds, and returns at most 1,000 pending events. Lower `max_pending` to use a
smaller batch. Pending events are returned before another remote page is read.
Repeated calls return unacknowledged events. The result reports
`pending_count` and `backpressure`; use `events_ack` after processing each item.
Local inbox effects are declared in MCP annotations and offline capabilities.

Vehicle-report pulls require API support for strict timestamp/ID keysets
(API #5027). Each page confirms `keyset: true`. Older APIs fail without advancing
the cursor. Pulls use offset zero with the saved `(updated_at, id)` boundary so
an earlier report moving forward does not hide an unprocessed report. A newer
version replaces the earlier version within a pull; consumers upsert between
pulls. A timestamp-only saved cursor replays its timestamp to retain tied IDs.
This is an incremental scan, not a database snapshot.

Defect pulls also require the confirmed API keyset contract. New defect cursors
store both `reported_at` and `id`; `cursor_before` and `cursor_after` use that
object shape. Existing timestamp-only cursor files replay their saved timestamp
once, then save a numeric-ID boundary. Upsert by defect ID to absorb this
compatibility replay. New defects at a saved timestamp remain reachable. No
checkpoint advances until the whole pull and its output complete.

Review a Cortex CSV or XLSX file with `nova fleet-import review --file fleet.csv`.
Use `--options '{"corrections":{"2":{"vin":"1FTBR1C85LKA12345"}},"excluded_rows":[]}'`
to resend the same original file with cumulative corrections and exclusions.
The API returns source rows, field errors and mapped rows without importing
fleet data. Review corrections with the human; do not invent fleet facts.
The separate `vehicles.fleet_import.review.v1` grant uses read scope. Requires
the customer Cortex admission API; existing default grants gain no permission.
Local stdio MCP exposes `review_cortex_file` using the same local path/bytes
contract. This is not a hosted assistant file-transfer or import-apply claim.
Limits: 20 MiB source file and 64 KiB JSON options; existing API decoding and
row limits also apply. No source file is rewritten or archived by review.

Local MCP retains its 2 MiB response limit for Cortex previews. Use the CLI
for a larger preview, or review a smaller source file without changing row facts.

Save the corrected Cortex review as JSON. Run
`nova fleet-import preview --review-file reviewed.json` for database checks,
then `nova fleet-import apply --review-file reviewed.json` only after reviewing
the result with the human. Both require full scope and the separate
`vehicles.fleet_import.apply.v1` grant. `preview_fleet_import` and
`apply_fleet_import` expose the same actions in local MCP. Preview makes no fleet
changes; apply can create or update vans. `--add-missing-stations` and
`--deactivate-missing` are explicit options. Deactivation is blocked after
excluded, inactive or skipped source rows. Resolve errors or explicitly exclude
rows through Cortex review first; do not edit facts to bypass an import error.

Import accepts 1–2000 mapped rows and a complete review JSON of at most 100 MiB.
No automatic split occurs, because deactivation cannot be split safely. Partial
row errors retain results but return CLI exit 1 and MCP isError. A lost/invalid
apply response or server failure returns outcome_unknown; inspect the fleet
before trying again. Neither preview nor apply automatically retries its POST.

Connect through the existing browser flow with the review/import operations:
`nova auth login --scope "nova:read nova:write" --operations "vehicles.fleet_import.review.v1 vehicles.fleet_import.apply.v1"`.
Fleet reads for recovery require their own consent, or use the fleet in your
browser. This does not expand an existing saved connection.
