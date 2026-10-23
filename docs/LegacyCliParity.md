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
They are not yet a deployment claim.
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
| `profile set` | client setup | Pending | Setup handoff |
| `profile use` | client setup | Pending | Setup handoff |
| `profile list` | client setup | Pending | Setup handoff |
| `profile show` | client setup | Pending | Setup handoff |
| `profile remove` | client setup | Pending | Setup handoff |
| `auth login` | client setup | Pending | Setup handoff |
| `auth logout` | client setup | Pending | Setup handoff |
| `auth status` | client setup | Pending | Setup handoff |
| `auth whoami` | reads | Locally verified | Locally verified |
| `auth refresh` | client setup | Pending | Setup handoff |
| `health check` | reads | Locally verified | Locally verified |
| `health ready` | reads | Locally verified | Locally verified |
| `search` | reads | Locally verified | Locally verified |
| `work-order list` | reads | Locally verified | Locally verified |
| `work-order get` | reads | Locally verified | Locally verified |
| `work-order create` | writes and uploads | Pending | Pending |
| `work-order assignment get` | reads | Locally verified | Locally verified |
| `work-order assignment set` | writes and uploads | Pending | Pending |
| `work-order schedule` | writes and uploads | Pending | Pending |
| `work-order scheduling-defaults` | reads | Locally verified | Locally verified |
| `work-order wait` | reads | Locally verified | Locally verified |
| `work-order line-items list` | reads | Locally verified | Locally verified |
| `work-order line-items update` | writes and uploads | Pending | Pending |
| `work-order accept` | writes and uploads | Pending | Pending |
| `work-order complete` | writes and uploads | Pending | Pending |
| `work-order cancel` | writes and uploads | Pending | Pending |
| `work-order unschedule` | writes and uploads | Pending | Pending |
| `work-order release` | writes and uploads | Pending | Pending |
| `work-order add-delay-reason` | writes and uploads | Pending | Pending |
| `work-order decline` | writes and uploads | Pending | Pending |
| `work-order add-note` | writes and uploads | Pending | Pending |
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
| `vehicle add-note` | writes and uploads | Pending | Pending |
| `vehicle list-checkouts` | reads | Locally verified | Locally verified |
| `vehicle check-out` | writes and uploads | Pending | Pending |
| `vehicle check-in` | writes and uploads | Pending | Pending |
| `vehicle-report create` | writes and uploads | Pending | Pending |
| `vehicle-report list` | reads | Locally verified | Locally verified |
| `vehicle-report get` | reads | Locally verified | Locally verified |
| `vehicle-report resolve-vehicle` | writes and uploads | Pending | Pending |
| `vehicle-report promote` | writes and uploads | Pending | Pending |
| `vehicle-report dismiss` | writes and uploads | Pending | Pending |
| `vehicle-report pull` | reads | Locally verified | Locally verified |
| `defect list` | reads | Locally verified | Locally verified |
| `defect get` | reads | Locally verified | Locally verified |
| `defect update` | writes and uploads | Pending | Pending |
| `defect list-comments` | reads | Locally verified | Locally verified |
| `defect catalog` | reads | Locally verified | Locally verified |
| `defect photos` | reads | Locally verified | Locally verified |
| `defect pull` | reads | Locally verified | Locally verified |
| `notification list` | reads | Locally verified | Locally verified |
| `notification unread-count` | reads | Locally verified | Locally verified |
| `notification read` | writes and uploads | Pending | Pending |
| `notification read-all` | writes and uploads | Pending | Pending |
| `notification preferences` | reads | Locally verified | Locally verified |
| `notification update-preferences` | writes and uploads | Pending | Pending |
| `notification turn-off-optional-delivery` | writes and uploads | Pending | Pending |
| `upload photo` | writes and uploads | Pending | Pending |
