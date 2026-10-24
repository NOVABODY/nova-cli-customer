# Customer capability coverage

This is the broader web workflow inventory. The completed delivery scope is
[legacy customer CLI parity](LegacyCliParity.md): 67 accepted command outcomes,
with platform administration and private authentication modes excluded. This is
not full coverage of every web workflow below.

## Current availability

The client implements the accepted legacy commands: 52 business commands, nine
local auth/profile commands, two health commands, and four workshop-event commands.
MCP exposes the 58 legacy named tools plus Cortex file review, import preview/apply and direct defect reporting; local auth/profile setup uses the browser or local CLI.
The legacy ledger records compatibility tests and sampled real browser, installed
CLI, system credential store, and stdio MCP verification. Broader web-only actions
must not be inferred from these results or from a related command name.

Capability discovery reports `legacy_customer_parity: true` and keeps
`full_customer_parity: false` for this broader web inventory. Discovery does not
check authorization or deployment. The API checks every operation, role and record.
Matching API changes, review, merge, deployment and customer activation remain
separate gates. The repository remains private.

## Workflow table of contents

“DSP” and “shop” identify the customer audience, not blanket permission for every
member of that audience. The API checks the action and record on every request.
The source column names the web/API owner used to verify the existing workflow.
Use the legacy ledger for exact implemented commands. This table describes broader
web workflows; it is not a command availability or authorization table.

| Area | Existing customer workflow to cover | Audience | Web/API owner |
| --- | --- | --- | --- |
| Fleet reads | List and filter vehicles; read one vehicle. **Implemented**, subject to deployment access. | DSP and shop, within scope | `MyVehicles`; `api/vehicles.js`; `routes/vehicles.py` |
| Fleet management | Cortex file review/corrections are implemented for the public CLI and local MCP, subject to its separate API grant. Import dry run/apply are implemented in the public CLI and local MCP, with full consent and existing API business gates; hosted adapters remain pending. Add, update, deactivate and delete eligible vehicles; replacement; VIN decode; roster import preview and confirmation; history export. | Authorized DSP fleet roles | `MyVehicles`; `api/vehicles.js`; `routes/vehicle_replacements.py` |
| Fleet updates | Pending new-van and plate-mismatch records; suggestions; grouping/filtering; reconciliation. | Authorized DSP fleet roles | `UnlistedVehiclesTab`; `api/fleetUpdates.js`; `api/unlistedVehicleReports.js` |
| Vehicle notes and custody | Notes and permitted edits/deletion; checkout history and workshop choices; check-out/check-in with mileage, inspection or photo evidence. | DSP and shop, per action | `api/vehicles.js`; `routes/vehicles.py` |
| Grounding and vehicle evidence | Grounding reports and allowed decisions; vehicle PAVE reports and scan handoff. | Scoped customer roles | `api/grounding.js`; `routes/grounding.py`; `routes/vehicle_pave_reports.py` |
| Inspection catalog | Vehicle-class catalog, effective DSP checklist, targets, positions and criticality. | Authorized inspectors and fleet roles | `api/inspectionCatalog.js`; `routes/dvic_template.py` |
| Inspection draft | Start/resume/cancel own draft; checklist answers; tread depths; defects; open-defect checks; photo upload, commit and removal. | Authorized DSP/shop inspectors | `api/inspections.js`; `routes/inspections.py`; `routes/inspection_open_defect_check.py` |
| Inspection results | Submit a complete or permitted incomplete inspection; list/detail/latest results; export. | Authorized inspectors and readers | `LatestInspections`; `api/inspections.js` |
| Defect evidence | List/detail **implemented**, subject to deployment and `defects.list.v1` / `defects.get.v1` grants. Catalog, title updates, comment reads and photo downloads/uploads are also implemented. Direct defect reporting with optional shop routing is implemented beyond legacy parity under `defects.create.v1`; edits/deletion, comment writes/revisions and photo history remain outside the legacy scope. | DSP and shop with record access | `Defects`; `api/defects.js`; `routes/defect_comments.py` |
| Defect decisions | Approval/rejection; cost decisions; record work completed outside Nova. | Authorized DSP decision makers | `Defects`; `api/client.js: defectReviews`; `routes/defect_reviews.py` |
| Repair routing | Request detail and eligible destinations; send to shop or external provider; rental-routing decisions; cancel/defer/add defects. | Authorized DSP roles | `api/client.js: repairRequests`; `routes/repair_requests.py` |
| Shop intake and work | Work-order list/detail **implemented**, subject to deployment and grants. Manual intake, accept/decline/release, assignments, activity and notes are also implemented. Van board and export are outside the legacy scope. | Shop roles, per action and assignment | `WoV2Dashboard`; `api/workOrders.js`; `routes/work_orders/` |
| Shop scheduling | Schedule/unschedule; pickup requests and confirmation; batch scheduling; allowed DSP responses and rescheduling. | Shop coordinators and scoped DSP roles | `api/workOrders.js`; `routes/work_orders/pickup.py`; `routes/work_orders/schedule_batches.py` |
| Repair execution | Line-item add/update/remove/split/defer/progress; RO records; defect move/release/reject/delay; custody and completion evidence. | Assigned shop workers and coordinators | `api/workOrders.js`; `routes/work_orders/line_items.py`; `routes/work_orders/lifecycle.py` |
| Technician shifts | Current shift; start/end; status events with required location evidence. | Eligible shop technicians | `api/technicianShifts.js`; `routes/technician_shifts.py` |
| Inspection schedule | Read/create/cancel appointments; recurrence and overrides; fleet reschedule request; shop response and confirmation. | DSP and shop, per action | `VendorInspectionSchedule`; `api/dashboards.js`; `routes/dashboards/dvic_schedule.py` |
| Body request and scope | List/detail; create; select body defects; edit/replace/acknowledge scope; PAVE attachment/history/comparison; scope and document downloads. | Eligible DSP and body shop roles | `BodyRepairFlow`; `api/client.js: bodyRepair`; `routes/body_repair/` |
| Body quotes | Shop rates; quote drafts; submit/withdraw/renew; customer selection/decline; revision proposal/approval/decline; quote download. | Body shop writers and DSP decision makers | `routes/body_repair/quotes.py`; `routes/body_repair/revisions.py` |
| Body pickup | Details/defaults/history; propose/accept/withdraw time changes; readiness; failed-visit report and fleet dispute; inspection/custody handoff. | Assigned shop and scoped DSP roles | `routes/body_repair/pickup_negotiation.py`; `routes/body_repair/pickup_issues.py`; `routes/body_repair/inspection.py` |
| Body execution and return | Completion notes/photos; scope dispositions; complete; customer repair rejection; return/drop-off and confirmation; failed drop-off report, customer reply and dispute; allowed cancellation/withdrawal. | Assigned shop and scoped DSP roles | `routes/body_repair/lifecycle.py`; `routes/body_repair/dropoff_issues.py` |
| Body collaboration | Message threads, unread state, read markers, messages and attachments; warranty file/list/allowed resolution; shop on-time record. | Order participants within their projection | `routes/body_repair/messaging.py`; `routes/body_repair/warranty.py`; `routes/body_repair/on_time.py` |
| Body payment | Payment choice, preparation and status; invoice and documentation downloads; eligible referral credit application/removal. | Authorized fleet payer | `routes/body_repair/payments.py`; `api/client.js: bodyRepair` |
| Subscription billing | Subscription/payment-method reads; invoices; saved methods and allowed removal; checkout and portal handoff. | DSP owner | `api/client.js: billing`; `routes/billing.py` |
| Shop payment account | Payout status and onboarding handoff; customer-accessible payout statements and dispute evidence/actions. | Authorized shop financial roles | Customer money view; `api/client.js: stripe/finance` |
| DSP reports | Home summaries; daily work and acknowledgment; active/actionable/history defects; post-inspection; driver reports; vehicle availability; applicable exports. | DSP roles with corresponding grants | `api/dashboards.js`; `api/defects.js`; `routes/dashboards/` |
| Shop reports | Home/incoming work; operations/repair metrics; shifts; inspection consistency and authorized review; scorecard/problem reports; exports where offered. | Shop roles with corresponding grants | `api/dashboards.js`; `api/client.js: vendorScorecard` |
| Ratings | Eligible fleet repair rating and permitted updates; shop's released ratings and timeliness record. | Scoped fleet raters and shop readers | `api/client.js: vendorScorecard`; `routes/shop_ratings.py` |
| Rewards and referrals | Own referral link/rotation; program/credits; submit/list/recover own referrals; eligible vendor referral; shop rewards balance/ledger. | Eligible DSP/shop participants | `Rewards`; `api/client.js: rewards/vendorBucks` |
| Own organization | Profile and geography; allowed Station requests; vehicle/key locations; shop configuration and capabilities. | Authorized organization administrators | Organization settings; `api/directory.js`; `api/client.js: vendorWorkshops` |
| Own team | User directory and permitted edits; invitations, resend/revoke and supported bulk import; teams/members/leaders; repair defaults. | DSP owner/manager or shop administrator, per action | Team settings; `api/directory.js`; `api/client.js: invitations`; `routes/teams.py` |
| DSP settings | Station loadouts, inspection instructions, parking, team Station scope, vendors and contacts; billing contact; permitted checklist customization. | Authorized DSP settings roles | `api/client.js: dspSettings`; `routes/dsp_settings.py` |
| Personal account | Own profile/language/phone; password recovery; own sessions and MFA devices; browser security setup. | Signed-in customer | `UserSettingsPlaceholder`; `api/auth.js` |
| Notifications and support | List/count/read/resolve; preferences; customer-scoped event consumption; bug report and attachments. | Eligible signed-in customer | `api/notificationPreferences.js`; `api/bugReports.js`; notification API |
| Enrollment | Account and invitation completion; organization onboarding and required agreements. | Invited or eligible customer | Signup/onboarding web flow; `api/auth.js`; `api/contracts.js` |

## Role and state boundaries

- DSP roles are `dsp_owner`, `dsp_manager`, `dsp_dispatcher` and `dsp_viewer`.
  The last is the DSP Inspector role: it can conduct its own draft inspections;
  it is not universally read-only. It cannot edit another inspector's draft or
  historical inspection evidence merely because it can inspect.
- Shop roles are `vendor_admin`, `service_writer`, `foreman`, `technician` and
  `vendor_viewer`. Assignment, workshop and team restrictions still apply.
- DSP billing is owner-only. DSP managers have some team-management authority,
  but that does not confer every owner action. Dispatchers can perform several
  pickup and rating actions without gaining all body-repair decisions.
- Nova Body and Nova Basic have different workflow availability. Body-only shops
  also have a different workspace. A role label alone cannot establish parity.
- Station scope, organization relationships, record ownership, server grants,
  feature availability and workflow state may narrow every listed capability.
  A preferred-shop relationship alone does not grant access to every defect.
- Preserve stale-version and conflict responses. Do not automatically reread and
  overwrite a changed decision. Photo evidence, inspection completeness and
  payment state remain server-enforced prerequisites.

## Browser handoffs

Browser authorization, MFA and passkeys require the user's browser interaction.
Stripe checkout, billing portal, payout onboarding and payment authorization
remain hosted flows. PAVE capture uses its inspection link and camera flow.
Signup, onboarding and agreement acceptance must preserve the required user
interaction. The CLI can expose a documented handoff where authorized; it must
not claim that producing a link completes the workflow.

Other missing operations are implementation gaps, not automatically browser-only
features. File uploads, downloads and machine-readable results should be supported
where the reviewed customer API contract permits them.

## Exclusions

Platform administration, impersonation, other organizations' security lifecycle,
global configuration, recovery administration, staff financial controls and staff
adjudication are outside this customer client. Developer simulation and backend
maintenance are also excluded. No arbitrary API-path command is planned.

Customer-owned organization and team administration remains in scope. A web
section named “Admin” does not make its customer actions platform administration.
Every operation needs an individual customer contract; shared API modules contain
more authority than a customer client should expose.

## Implementation sequence and acceptance

1. Ship and deploy the browser authorization/consent foundation, including the
   pending API dependency. Establish explicit operation scopes and enforcement,
   revocation, customer response projections and negative authorization tests.
2. Ship capability discovery from one allowlisted registry, used by both human
   TOC and machine JSON. Distinguish implemented, unavailable and browser handoff;
   distinguish static client support from the current account's live authority.
3. Add fleet context, search, notifications and customer reports as read slices.
   Each slice needs pagination, filters, projection and cross-tenant denial tests.
4. Add fleet updates, notes/custody/grounding and inspections as separate complete
   workflows, including uploads, draft recovery, conflicts and submission gates.
5. Add defect decisions/routing, then shop intake, scheduling, assignment and
   execution. Verify role and state restrictions at each consequential action.
6. Add body scope/quotes, logistics, execution/collaboration and payment handoffs
   in separate slices that preserve version and consent requirements.
7. Add own-team/settings, billing, rewards and account workflows with their
   narrower role boundaries. Finish enrollment and external-provider handoffs.
8. Reconcile every table row against shipped commands and MCP tools, verify each
   critical workflow with synthetic end-to-end evidence, and refresh this matrix.
   Full parity is complete only when these outcomes work, not when listed here.

Each delivered operation should identify its stable ID, command/tool, input and
output schema, read/write effect, audience and scope, prerequisites, conflict
fields, file behavior and handoff requirements. Keep destructive or financial
effects explicit. Do not describe unavailable operations as callable tools.

## Verification sources

Inventory checked on 2026-10-23 against Nova API/web source revision
`9f0356ab3c3ab71e4dda037dfd05827b65c59593` (`origin/master` at inspection).
Source owners above are relative to `nova-fora-demo/src/` for web files and
`apps/api/app/` for route files in the Nova application source. The maintained
workflow and endpoint references were cross-checked with current code; navigation
alone was not treated as proof of write authority. Important role sources are
`lib/permissions.js`, `lib/rolePermissions.js` and `lib/navigationAccess.js`.
These source references document the audit; users do not need source access to
use the CLI. Later API changes require revalidation of the affected rows.

### PAVE read adapter slice

The public CLI and local MCP now expose van PAVE history, Body Repair report
lists and report comparison through three explicit read grants. See
[consent and commands](../README.md#pave-report-reads). API role, tenant and
held-report projections remain authoritative. This slice does not add scan,
attachment, report mutation or file-download support. Source SDK tests prove
adapter behavior; they do not prove an installed client joined to a deployed API.
