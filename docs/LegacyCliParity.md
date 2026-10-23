# Legacy customer CLI parity

The reference is the legacy CLI at `b3cc5c583c6a6516a27b41f13614c05bf1dd1506`.
Parity covers its 67 accepted command outcomes: 52 customer business commands,
9 local client commands, 2 health commands, and 4 event commands.
Command registration alone does not establish parity. Each outcome requires
compatible arguments, defaults, payloads, response fields, pagination, files and
error behavior, plus enforced user, organization and operation permissions.

The implementation reuses the existing customer handlers and their tests. The
CLI and MCP share explicitly named operations. MCP exposes structured inputs;
local account setup uses browser or local CLI handoffs. It does not expose
credential values or change credentials through a business tool.

## Exclusions and deliberate differences

The 13 platform administration commands, arbitrary authenticated API command,
service-key setup, and direct password-reset command are excluded. Browser
login and browser account recovery replace password collection. Profiles bind
credentials to an explicit API origin and use the operating-system credential
store; file token storage and token-bearing host overrides are excluded.

Customer business actions remain in scope even when the API requires a human
user or customer administrator. The server retains its existing role and record
checks. Platform administration is not implied by access to a customer command.

## Completion evidence

Rows advance only after compatibility and authorization checks pass. The 29 read
commands passed local behavior tests, MCP validation and sampled browser journeys.
The nine local profile and auth commands are also locally verified. Installed-wheel
profile checks cover set, use, list, show, remove and API-origin preservation;
browser journeys cover login, status, refresh and logout with the system credential store.
The 25 mutation/upload commands passed reused payload/validation tests and shared
CLI/MCP transport checks. Installed-client journeys verify persisted notes, shop-only
defect titles, notifications, signed photo upload plus parent commit, foreign-record
denial, explicit write refresh, and read-only connection denial. Remaining event
commands are pending. These results are not a deployment claim.
Existing vehicle, work-order and defect list/get commands are included because
matching names alone does not prove legacy options or response parity.
Read, mutation/upload and event cohorts are independently reviewable. Browser
consent, installed CLI and actual MCP protocol checks supplement the reused
behavioral tests. Public package contents must exclude private administration
code, imports and credentials. CI, merge, deployment and production verification
are separate from local parity evidence.

The machine-readable companion is [legacy-customer-parity.json](legacy-customer-parity.json).

| Legacy command | Cohort | CLI | MCP |
| --- | --- | --- | --- |
| `profile set` | client setup | Locally verified | Setup handoff |
| `profile use` | client setup | Locally verified | Setup handoff |
| `profile list` | client setup | Locally verified | Setup handoff |
| `profile show` | client setup | Locally verified | Setup handoff |
| `profile remove` | client setup | Locally verified | Setup handoff |
| `auth login` | client setup | Locally verified | Setup handoff |
| `auth logout` | client setup | Locally verified | Setup handoff |
| `auth status` | client setup | Locally verified | Setup handoff |
| `auth whoami` | reads | Locally verified | Locally verified |
| `auth refresh` | client setup | Locally verified | Setup handoff |
| `health check` | reads | Locally verified | Locally verified |
| `health ready` | reads | Locally verified | Locally verified |
| `search` | reads | Locally verified | Locally verified |
| `work-order list` | reads | Locally verified | Locally verified |
| `work-order get` | reads | Locally verified | Locally verified |
| `work-order create` | writes and uploads | Locally verified | Locally verified |
| `work-order assignment get` | reads | Locally verified | Locally verified |
| `work-order assignment set` | writes and uploads | Locally verified | Locally verified |
| `work-order schedule` | writes and uploads | Locally verified | Locally verified |
| `work-order scheduling-defaults` | reads | Locally verified | Locally verified |
| `work-order wait` | reads | Locally verified | Locally verified |
| `work-order line-items list` | reads | Locally verified | Locally verified |
| `work-order line-items update` | writes and uploads | Locally verified | Locally verified |
| `work-order accept` | writes and uploads | Locally verified | Locally verified |
| `work-order complete` | writes and uploads | Locally verified | Locally verified |
| `work-order cancel` | writes and uploads | Locally verified | Locally verified |
| `work-order unschedule` | writes and uploads | Locally verified | Locally verified |
| `work-order release` | writes and uploads | Locally verified | Locally verified |
| `work-order add-delay-reason` | writes and uploads | Locally verified | Locally verified |
| `work-order decline` | writes and uploads | Locally verified | Locally verified |
| `work-order add-note` | writes and uploads | Locally verified | Locally verified |
| `work-order list-notes` | reads | Locally verified | Locally verified |
| `work-order activity` | reads | Locally verified | Locally verified |
| `team repair-bucket-defaults` | reads | Locally verified | Locally verified |
| `events head` | events | Pending | Pending |
| `events init` | events | Pending | Pending |
| `events watch` | events | Pending | Pending |
| `events ack` | events | Pending | Pending |
| `vehicle list` | reads | Locally verified | Locally verified |
| `vehicle get` | reads | Locally verified | Locally verified |
| `vehicle list-notes` | reads | Locally verified | Locally verified |
| `vehicle add-note` | writes and uploads | Locally verified | Locally verified |
| `vehicle list-checkouts` | reads | Locally verified | Locally verified |
| `vehicle check-out` | writes and uploads | Locally verified | Locally verified |
| `vehicle check-in` | writes and uploads | Locally verified | Locally verified |
| `vehicle-report create` | writes and uploads | Locally verified | Locally verified |
| `vehicle-report list` | reads | Locally verified | Locally verified |
| `vehicle-report get` | reads | Locally verified | Locally verified |
| `vehicle-report resolve-vehicle` | writes and uploads | Locally verified | Locally verified |
| `vehicle-report promote` | writes and uploads | Locally verified | Locally verified |
| `vehicle-report dismiss` | writes and uploads | Locally verified | Locally verified |
| `vehicle-report pull` | reads | Locally verified | Locally verified |
| `defect list` | reads | Locally verified | Locally verified |
| `defect get` | reads | Locally verified | Locally verified |
| `defect update` | writes and uploads | Locally verified | Locally verified |
| `defect list-comments` | reads | Locally verified | Locally verified |
| `defect catalog` | reads | Locally verified | Locally verified |
| `defect photos` | reads | Locally verified | Locally verified |
| `defect pull` | reads | Locally verified | Locally verified |
| `notification list` | reads | Locally verified | Locally verified |
| `notification unread-count` | reads | Locally verified | Locally verified |
| `notification read` | writes and uploads | Locally verified | Locally verified |
| `notification read-all` | writes and uploads | Locally verified | Locally verified |
| `notification preferences` | reads | Locally verified | Locally verified |
| `notification update-preferences` | writes and uploads | Locally verified | Locally verified |
| `notification turn-off-optional-delivery` | writes and uploads | Locally verified | Locally verified |
| `upload photo` | writes and uploads | Locally verified | Locally verified |
