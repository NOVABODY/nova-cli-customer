# Nova CLI

The customer Nova Fora client signs in through your browser and uses the existing
customer workflows. The CLI and local MCP share named operations,
including vehicle, work-order, defect and vehicle-report reads, photo downloads,
cursor-based packages, notifications, search, team defaults, and health checks.
It does not accept passwords or service keys or expose arbitrary API commands.
The named customer write and photo-upload commands require explicit write consent.
Workshop event tools provide durable delivery with explicit local acknowledgment.

## Install

Use Python 3.11 or later and a working OS credential store. Install the release
wheel supplied by Nova in a dedicated environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install ./nova_cli-0.1.0-py3-none-any.whl
nova --help
```

Each successful Check job retains its tested wheel and `release-receipt.json`
for 14 days. The receipt identifies the source revision and includes SHA-256
hashes for every tracked source file and every wheel file. It also checks that
the complete packaged client matches that source. A receipt is build evidence;
it does not authorize release or package-registry publication. Use an approved
release from a reviewed main-branch revision. A pull-request artifact is a test
candidate.

Use the file name supplied with your release if its version differs. These steps
do not assume that a package-registry release is available. Your Nova deployment
must allow browser connections and the operations you request.

## Use

```sh
nova profile set personal --api https://app.nova4a.com/api
nova --profile personal auth login
nova vehicle list --status grounded --json
nova vehicle get VAN-0001 --json
nova auth status
nova auth refresh
nova auth logout
```

Use `profile set NAME --api URL` when your account uses a different Nova deployment.

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
python3 -m pip install './nova_cli-0.1.0-py3-none-any.whl[mcp]'
nova-mcp --profile personal
```

Use the same dedicated environment as the CLI. The separate HTTP MCP service
also uses a `nova-mcp` command; install that service in a different environment.
Configure a local MCP client to launch the command above over stdio. It exposes the same
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

## Discover capabilities

Run `nova capabilities` for the full command table of contents. Agents can use
`nova capabilities --json` for arguments, schemas, examples, effects, OAuth scopes
and MCP tool references. Use `nova capabilities --command "vehicle get" --json`
to inspect one command. Discovery is offline and requires no credentials. It
does not claim that an account or deployment permits an operation.

The CLI provides named customer reads, changes, uploads, and workshop events.
See the [command reference](docs/Commands.md) and [workflow coverage](docs/CustomerParity.md)
for available actions and browser handoffs.

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
The `defect list --status` filter runs on the returned page.
Use `nova COMMAND --help` for each command's options. Capability discovery lists
required operation IDs without granting access. A list-only grant cannot read
record detail. Work-order waits and line-item reads use the work-order detail
grant; package pulls use the corresponding list grant.

See [command compatibility](docs/LegacyCliParity.md) for aliases and client behavior.
Your deployment must allow the requested operation before a command can succeed.

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

Vehicle-report pulls use strict timestamp/ID keysets. Each page confirms `keyset: true`. Older APIs fail without advancing
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

### Visit composition

The existing `nova work-order schedule` command and local `schedule_work_order`
tool accept visit defect selection. Repeat `--include-defect-id` and `--exclude-defect-id` with numeric
IDs (local MCP `include_defect_id` / `exclude_defect_id` arrays), up to 100 each.
Do not repeat an ID or place it in both lists. Omitted fields remain absent.
The existing `work_orders.schedule.update.v1` grant is unchanged; the API owns
state, workshop/defect eligibility, visit locks and customer confirmation.
Selection can affect other work orders. Read current visits before changes and
check them before another attempt if the result is unknown. No retry is added.

A null repair time is rejected by the API; use the existing unschedule workflow
to remove a schedule. Clearing a repair bucket or assignment remains supported.

### PAVE report reads

Read the PAVE report history for a van, the reports for a Body Repair order,
or the order's comparison. Use a record ID that your account can read.

```sh
nova auth login --operations "vehicles.pave_reports.list.v1 body_repair.pave.list.v1 body_repair.pave.compare.v1"
nova vehicle pave-reports VAN-0001 --json
nova body-repair pave-reports BRR-0001 --json
nova body-repair pave-comparison BRR-0001 --json
```

The API must allow these operations for the registered client. Obtain new
browser consent for each required operation. Default login permissions do not
include these reads. The API checks the role, organization, order and report
visibility on every request. A held post-repair report can have an ID and phase
with no grade or evidence. Do not treat withheld values as a missing report.

Local MCP uses `list_vehicle_pave_reports`, `list_body_repair_pave_reports` and
`compare_body_repair_pave_reports`. An order report list uses the standard MCP
`items` wrapper. Other API fields stay unchanged. These tools do not start a scan,
change a report, or download files. Open the van or Body Repair order in Nova to
use its normal report controls. PAVE and Body Repair are product terms.

### Body Repair order reads

```sh
nova auth login --operations "body_repair.requests.list.v1 body_repair.requests.get.v1"
nova body-repair list --stage open --limit 20 --offset 0 --json
nova body-repair get BRR-0001 --json
```

The API must allow these operations for the registered client. Obtain new browser
consent. Default permissions do not include these reads. List filters are
`--status`, `--stage open`, `--limit` (1–200), `--offset` (0 or more), and
`--vehicle-id`. These tools do not expose staff scope or fetch another page.
For audience and losing-bidder shop rows, pass the returned `request_token` to
`body-repair get`; use the token for those rows. A token can start with
`-`. Put the token after `--` so the CLI reads it as a literal value:

```sh
nova body-repair get --json -- "$request_token"
```

Use `order_number` as the
human reference. The API owns each role's fields and visibility. Its vendor
queue can report `total` as the returned row count, so do not infer a complete
queue from that value or assume offset pagination applies to every role.

Local MCP tools are `list_body_repair_requests` and `get_body_repair_request`.
The list keeps the API's `items` and `total` object. These two tools read orders and do not fetch another page automatically.
Use the separate document commands for file downloads.


### Body documentation ZIP

`nova body-repair documentation BRR-0001 --lang es --out documentation.zip`
saves the original authorized ZIP (64 MiB limit), without extraction or overwrite.
`--lang` selects `en` or `es` (default `en`) for receipt text and filenames.
Local MCP `download_body_repair_documentation` takes `request_ref` and `lang`;
it embeds original ZIP bytes up to 1 MiB, with size/hash metadata and no file write.
For larger files use the CLI command or download documentation from the order.
Requires explicit `body_repair.documents.documentation.read.v1` consent and the
coordinated API admission/privacy fix. PDF limits and default permissions stay fixed.

Read a stored Body PAVE image with `nova body-repair pave-image
--storage-key=KEY --category panel --idx 0 --out image.bin`. Use the selected
public profile (`--profile NAME`). PNG, JPEG and WebP bytes retain their format.
CLI limit: 64 MiB; local MCP limit: 1 MiB. Oversize tools return a CLI command.
Consulta una imagen PAVE guardada con el mismo comando y el perfil público
seleccionado. Límite de CLI: 64 MiB; límite de MCP local: 1 MiB.
The API controls scope and POST evidence holds. This command does not run a scan,
fetch a provider URL, or change a report. Explicit image-read consent is required.

Read permitted inspection evidence with `nova inspection list --page 1 --per-page 20`
and `nova inspection get INS-42`. List accepts DSP/van, date, result and status filters.
An omitted status uses the API's submitted default. Pagination is explicit (1–100
rows per page); no additional pages, photos or XLSX files are fetched. Complete API
JSON is preserved. The two named reads require explicit inspection-operation consent.
Consulta las inspecciones permitidas con `nova inspection list` y `nova inspection get`.
Si no se indica el estado, se usa el estado enviado de la API. Usa la página y el
número de filas por página para consultar más resultados. No se descargan fotos ni XLSX.

### Stored photo references

Use `nova defect list-photos FD-123` or the local MCP tool `list_defect_photos`
to read permitted photo metadata. The response retains `items`, `total` and
all permitted fields. This read requires `defects.photos.list.v1` consent.
It does not fetch a provider URL or download files. Use the existing
`defect photos` command to download photos.

Usa `nova defect list-photos FD-123` o la herramienta local MCP
`list_defect_photos` para consultar los metadatos de fotos permitidos. La
respuesta conserva `items`, `total` y los campos permitidos. Esta consulta
requiere el permiso `defects.photos.list.v1`. No accede a una URL del
proveedor ni descarga archivos. Usa `defect photos` para descargar fotos.
Review pending defects with `nova defect-review queue --limit 50`. Read the
history with `nova defect-review history FD-1`. Use `nova defect-review approve
FD-1` or `nova defect-review reject FD-1 --reject-reason-code duplicate` to record
a decision. Run `nova capabilities --command "defect-review approve" --json` for
all routing fields. Request the exact `defect_reviews.queue.list.v1`,
`defect_reviews.list.v1`, `defect_reviews.approve.v1`, or
`defect_reviews.reject.v1` operations at sign-in. Decisions require write scope.

Use `nova vehicle decode-vin 1FTBR1C80MKA12345` to read VIN data. Use
`nova vehicle update VAN-1 --data '{"plate":"NEW123"}'` to change van data.
The MCP tools are `decode_vehicle_vin` and `update_vehicle`; the update tool
accepts a closed `data` object. Omitted fields stay unchanged. Explicit `null`
is sent to the API. Human updates accept `location` values `parking_lot`,
`offsite` and `checked_out` through the native partial update. Existing
check-in/check-out commands retain their handoff and evidence workflow.
Request `vehicles.decode_vin.v1` or `vehicles.update.v1` at sign-in. Updates
require write scope. The API controls role, tenant, mileage and field permissions.
Consulta los datos del VIN con `nova vehicle decode-vin`. Cambia los datos
permitidos del van con `nova vehicle update`. Los campos omitidos no cambian.
El campo `location` acepta `parking_lot`, `offsite` y `checked_out` mediante
la actualización nativa. Los comandos para registrar entrada y salida
conservan su proceso de entrega y pruebas. La API aplica los permisos de
rol, organización y campos.

Set a defect cost with `nova defect set-cost FD-7 --estimated-cost 12.3450`
or stdio MCP `set_defect_cost({"defect_id":"FD-7","estimated_cost":"12.3450"})`.
This uses native `POST /defects/{defect_id}/cost`, operation
`defects.cost.set.v1`, and full `nova:read nova:write` consent. The API decides
role, tenant, active work-order access and automatic approval. Input is a decimal
string greater than zero and at most 999999.99; the native receipt is preserved.
After an unknown outcome, read the defect before another attempt.

Add a van with `nova vehicle create --data '{"fleet_id":"NEW1","vin":"1FTBR1C80MKA12345","plate":"NEW123","year":2021,"make":"Ford","model":"Transit"}'`.
The `create_vehicle` MCP tool accepts the same closed `data` object. Request
`vehicles.create.v1` and write scope at sign-in. Optional fields stay omitted
unless supplied. The API owns uniqueness, role and tenant checks. Update-only
fields and custody changes are not accepted by this command.
Añade un van con `nova vehicle create --data`. Se requieren el ID de flota,
VIN, matrícula, año, marca y modelo. Solicita el permiso `vehicles.create.v1`
y el alcance de escritura. La API comprueba los permisos y los datos duplicados.


Use `vehicle update-note VAN-7 3 --body Fixed` or `vehicle delete-note VAN-7 3`
for a note that you can manage. Request `vehicles.notes.update.v1` or
`vehicles.notes.delete.v1` with write consent. The API checks note ownership
and van access. List up to 200 notes with `vehicle list-notes VAN-7 --limit 200`.
Cambia o elimina una nota que puedas gestionar con `vehicle update-note` o
`vehicle delete-note`. La API comprueba la autoría y el acceso al van.
The server checks note ownership and the current connection permissions.
Read native repair requests with `nova repair-request list`, `get RR-7`, or
`external-vendor-options RR-7`. Stdio tools are `list_repair_requests`,
`get_repair_request` and `list_repair_request_external_vendor_options`. Request
`repair_requests.list.v1`, `repair_requests.get.v1` or
`repair_requests.external_vendor_options.list.v1` at sign-in. List filters use
the native status and rental routing fields; one page defaults to 100 records
and permits at most 500. Native fields and totals stay unchanged. Routing and
approval mutations are excluded. Companion API admission must be deployed.

Aggregate reports use `report work-order-completion`, `report repair-metrics`, and
`report inspection-compliance`. The local MCP tools are
`get_work_order_completion_report`, `get_repair_metrics_report`, and
`get_inspection_compliance_report`. Use optional `--date-from` and `--date-to`
(`YYYY-MM-DD`) and `--dsp-id`; the first two reports also accept
`--vendor-workshop-id`. Omit dates to use API defaults (UTC today and 30 days
before it, or 7 days for compliance). Filters only narrow permitted records.
Blank filters and invalid filter strings retain API behavior. The API rejects
reversed dates and repair metric windows over 366 days. Reports retain all native
fields, nullable metrics, SLA basis, timestamps, and series; the client does not
calculate metrics. Each report requires its matching `reports.*.get.v1` grant.

Read Fleet Updates with `nova fleet-updates list`. Use the native kind, status, group, limit and offset filters. Resolve an existing issue with `nova fleet-issue resolve 7 keep`. The other native actions are `inactive`, `update_plate` and `plate_correct`; the API checks which actions the issue permits. An inactive action can make the van inactive. These commands do not submit unlisted van reports or reconcile the fleet. Resolution requires full write consent and `fleet_issues.resolve.v1`; listing requires `fleet_updates.list.v1`.

Consulta las actualizaciones de flota con `nova fleet-updates list`. Resuelve un problema con `nova fleet-issue resolve 7 keep`. La API comprueba el rol, la organización y las acciones permitidas. La acción `inactive` puede desactivar el van. Estas operaciones no envían informes de vans no incluidos ni concilian la flota.

Cancel a repair request with `repair-request cancel RR-7 --reason Done`.
Request `repair_requests.cancel.v1` and write consent. The API cancels eligible
child work orders and sends the existing notifications. Completed requests
remain fulfilled; the returned status reflects the native rollup. Read the
request after an unknown outcome before another attempt.
Cancela una solicitud con `repair-request cancel RR-7`. La API cancela las
órdenes de trabajo correspondientes y envía las notificaciones existentes.
Consulta la solicitud tras un resultado desconocido antes de otro intento.

Use `nova repair-request dismiss-rental-routing RR-7`, or local stdio tool
`dismiss_rental_routing`, to dismiss an obsolete rental routing reminder.
Request `repair_requests.rental_routing.dismiss.v1` with fresh write consent.
The native request stays open; no cost is accepted, repair routed, or vendor
email sent. Native role and DSP scope checks apply. After an unknown outcome,
read the repair request before another attempt; the client never retries the write.

`nova repair-request preview-external-vendor-options --vehicle-id VAN-7
--repair-type mechanical` reads native vendor options before a request exists.
Optional flags are `--defect-id` and `--service-station-code`. Local MCP tool
`preview_repair_request_external_vendor_options` uses the same closed inputs.
Request `repair_requests.external_vendor_options.preview.v1` read consent.
The API owns Station, category, tenant, and contact selection. This creates no
request, dispatch, or vendor email; recipient addresses are not returned.

Read vendor repair scores with `vendor-scorecard get VW-7` and comparisons with
`vendor-scorecard benchmarks VW-7`. The local MCP tools are
`get_vendor_scorecard` and `get_vendor_scorecard_benchmarks`. Both accept optional
`--days` (1–365); omit it to use the platform scorecard window. The summary also
accepts `--subject-kind work_order` or `body_repair`; comparisons accept optional
`--dsp-id`. The API controls role, fleet, workshop, relationship, and anonymous
rating release rules. Native fields and calculations remain unchanged. These
reads do not submit feedback or create correction work. Request the matching
`vendor_scorecard.get.v1` or `vendor_scorecard.benchmarks.get.v1` permission.

Read the selected local day's scheduled work with
`daily-work scheduled DSP-7 --service-date 2026-06-14` or the local MCP tool
`list_dsp_scheduled_work`. The service date is required. The API controls the DSP
role and tenant scope, timezone, live state, and labels. Native fields remain
unchanged. Request `dashboards.dsp_scheduled_work.list.v1` read permission.

Consulta el trabajo programado del día local con este comando o herramienta.
Introduce la fecha del servicio. La API controla los permisos y los datos actuales.

Read a daily work summary with `daily-work summary DSP-7 [--service-date YYYY-MM-DD]`
or `get_dsp_daily_work_summary`. Omit the date to use the DSP-local previous day.
Mark the summary as read with `daily-work acknowledge DSP-7 --service-date YYYY-MM-DD`
or `acknowledge_dsp_daily_work_summary`. The acknowledgment date is required.
The API retains native work, defect, count, label, and role/tenant rules. Read and
acknowledgment require the matching `dashboards.dsp_daily_work_summary.get.v1` and
`dashboards.dsp_daily_work_summary.acknowledge.v1` grants; acknowledgment needs full
write consent. It stores this principal's read state. No automatic write retry occurs;
read the summary after an unknown outcome before another attempt.

Consulta un resumen diario con `daily-work summary`. Omite la fecha para consultar
el día anterior en la zona horaria de la flota. Marca el resumen como leído con
`daily-work acknowledge` y su fecha. Se requiere permiso completo para marcarlo.
Consulta el resumen tras un resultado desconocido antes de otro intento.
### Repair rating and problem queues

`list_pending_vendor_feedback` reads native repairs that still need a rating. `list_vendor_problem_reports` reads native repair problem reports. The API owns the caller's role and tenant scope, active workshop scope, the pending-rating window and clamp, status normalization, and invalid-filter behavior. Optional filters stay omitted unless supplied. Native rows and fields are retained; MCP array results use the existing `items` envelope. These tools do not submit ratings or change reports.

Use `nova vendor-scorecard pending-feedback [--days 30] [--dsp-id DSP-7]` and `nova vendor-scorecard problem-reports [--vendor-workshop-id VW-7] [--status open]`.


### Report quality reads

Use `nova report inspector-performance [--days 30] [--dsp-id DSP-7]` or `nova report driver-da-quality [--days 30]`. The read tools are `list_inspector_performance` and `list_driver_da_quality`. Inspector reports require a site administrator or vendor administrator. Driver reports require a DSP owner, manager or dispatcher and include their own fleet. Optional `days` accepts 1–365; omitted filters retain API defaults. The API owns role and tenant scope, invalid-report details, and calculations.

Delegated reads require the exact live permissions `reports.inspector_performance.list.v1` and `reports.driver_da_quality.list.v1`. Service accounts retain the same authorized business outcome and native scope.
Read fleet/rental companies with `fmc-company list`; `--include-inactive`
retains the platform's administrator-only inactive view. Set a van's company
with `vehicle set-fmc-company VAN-7 --company-id FMC-8`. Local MCP tools are
`list_fmc_companies` (`active_only` defaults to true) and
`set_vehicle_fmc_company` (closed `vehicle_id`, `company_id` inputs). Request
`fmc_companies.list.v1` read or `vehicles.fmc_company.update.v1` write consent.
The API owns role, tenant, active-company and rental-scope checks. An uncertain
assignment is not retried; read the van before another attempt.
