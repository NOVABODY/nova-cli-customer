# Command reference

Generated from this release's `nova capabilities --json`. Use that command for full
input schemas, required arguments, examples and permissions. The table describes
client support; the server checks current account access.

| Command | Local MCP tool | Effect | Scope |
| --- | --- | --- | --- |
| `nova cmr-quote list` | `list_cmr_quotes` | remote_read | `nova:read` |
| `nova cmr-quote get` | `get_cmr_quote` | remote_read | `nova:read` |
| `nova cmr-quote submit` | `submit_cmr_quote` | remote_write | `nova:read nova:write` |
| `nova cmr-quote withdraw` | `withdraw_cmr_quote` | remote_write | `nova:read nova:write` |
| `nova cmr-quote dismiss` | `dismiss_cmr_quote_line` | remote_write | `nova:read nova:write` |
| `nova cmr-quote decide` | `decide_cmr_quote_line` | remote_write | `nova:read nova:write` |
| `nova skills list` | `list_skills` | remote_read | `nova:read` |
| `nova skills get` | `get_skill` | remote_read | `nova:read` |
| `nova body-repair repair-leads` | `list_body_repair_leads` | remote_read | `nova:read` |
| `nova body-repair quotes` | `list_body_repair_quotes` | remote_read | `nova:read` |
| `nova body-repair confirm-scope` | `confirm_body_repair_scope` | remote_write | `nova:read nova:write` |
| `nova body-repair submit-quote` | `submit_body_repair_quote` | remote_write | `nova:read nova:write` |
| `nova body-repair withdraw-quote` | `withdraw_body_repair_quote` | remote_write | `nova:read nova:write` |
| `nova bundle-shop fmc-pdf` | `get_bundle_fmc_packet_pdf` | remote_read, local_file_write | `nova:read` |
| `nova bundle-shop pickup` | `update_bundle_pickup` | remote_write | `nova:read nova:write` |
| `nova bundle-shop confirm-no-charge` | `confirm_bundle_no_charge` | remote_write | `nova:read nova:write` |
| `nova bundle-shop contact` | `request_bundle_contact` | remote_write | `nova:read nova:write` |

| `nova bundle-fee get` | `get_admin_bundle` | remote_read | `nova:read` |
| `nova bundle-fee waive` | `waive_bundle_fee` | remote_write | `nova:read nova:write` |
| `nova bundle-address get` | `get_bundle_dropoff_address` | remote_read | `nova:read` |
| `nova bundle-address set` | `update_bundle_dropoff_address` | remote_write | `nova:read nova:write` |
| `nova bundle-schedules list` | `list_bundle_schedules` | remote_read | `nova:read` |
| `nova bundle-schedules decide` | `decide_bundle_schedule` | remote_write | `nova:read nova:write` |
| `nova bundle-sharing get` | `get_bundle_sharing` | remote_read | `nova:read` |
| `nova bundle-sharing set` | `set_bundle_sharing` | remote_write | `nova:read nova:write` |
| `nova vendor-agreement status` | `get_vendor_agreement_status` | remote_read | `nova:read` |
| `nova bundle-workflow list` | `list_bundle_offers` | remote_read | `nova:read` |
| `nova bundle-workflow report` | `get_bundle_offer_report` | remote_read | `nova:read` |
| `nova bundle-workflow vans` | `list_bought_bundle_vans` | remote_read | `nova:read` |
| `nova tire-vendor list` | `list_station_tire_vendors` | remote_read | `nova:read` |
| `nova tire-vendor add` | `add_station_tire_vendor` | remote_write | `nova:read nova:write` |
| `nova tire-vendor share-contact` | `share_tire_vendor_contact` | remote_write | `nova:read nova:write` |
| `nova tire-vendor requests` | `list_vendor_setup_requests` | remote_read | `nova:read` |
| `nova tire-vendor handle` | `handle_vendor_setup_request` | remote_write | `nova:read nova:write` |
| `nova inspection-confirmation settings` | `get_inspection_confirmation_settings` | remote_read | `nova:read` |
| `nova inspection-confirmation set-settings` | `update_inspection_confirmation_settings` | remote_write | `nova:read nova:write` |
| `nova inspection-confirmation get` | `get_inspection_confirmation` | remote_read | `nova:read` |
| `nova inspection-confirmation respond` | `respond_inspection_confirmation` | remote_write | `nova:read nova:write` |
| `nova announcements` | CLI setup | remote_read | None |
| `nova capabilities` | CLI setup | local_read | None |
| `nova profile set` | CLI setup | local_config_write | None |
| `nova profile use` | CLI setup | local_config_write | None |
| `nova profile show` | CLI setup | local_read | None |
| `nova profile remove` | CLI setup | local_config_write, local_credentials_delete | None |
| `nova profile list` | CLI setup | local_read | None |
| `nova auth login` | CLI setup | browser_handoff, remote_authorization, local_credentials_write | `nova:read` |
| `nova auth status` | CLI setup | local_credentials_read | None |
| `nova auth refresh` | CLI setup | remote_authorization, local_credentials_write | `nova:read` |
| `nova auth logout` | CLI setup | local_credentials_delete, remote_authorization | None |
| `nova auth whoami` | `whoami` | remote_read | `nova:read` |
| `nova capacity-evidence list` | `list_capacity_evidence` | remote_read | `nova:read` |
| `nova capacity-evidence get` | `get_capacity_evidence` | remote_read | `nova:read` |
| `nova capacity-evidence file` | `read_capacity_evidence_file` | remote_read | `nova:read` |
| `nova capacity-evidence review` | `review_capacity_evidence` | remote_write | `nova:read nova:write` |
| `nova capacity-evidence upload` | `upload_capacity_evidence` | remote_write | `nova:read nova:write` |
| `nova bundle-schedules list` | `list_bundle_schedules` | remote_read | `nova:read` |
| `nova bundle-schedules decide` | `decide_bundle_schedule` | remote_write | `nova:read nova:write` |
| `nova bundle-sharing get` | `get_bundle_sharing` | remote_read | `nova:read` |
| `nova bundle-sharing set` | `set_bundle_sharing` | remote_write | `nova:read nova:write` |
| `nova vendor-agreement status` | `get_vendor_agreement_status` | remote_read | `nova:read` |
| `nova inspection-confirmation settings` | `get_inspection_confirmation_settings` | remote_read | `nova:read` |
| `nova inspection-confirmation set-settings` | `update_inspection_confirmation_settings` | remote_write | `nova:read nova:write` |
| `nova inspection-confirmation get` | `get_inspection_confirmation` | remote_read | `nova:read` |
| `nova inspection-confirmation respond` | `respond_inspection_confirmation` | remote_write | `nova:read nova:write` |
| `nova daily-work scheduled` | `list_dsp_scheduled_work` | remote_read | `nova:read` |
| `nova daily-work summary` | `get_dsp_daily_work_summary` | remote_read | `nova:read` |
| `nova daily-work acknowledge` | `acknowledge_dsp_daily_work_summary` | remote_write | `nova:read nova:write` |
| `nova fleet-updates list` | `list_fleet_updates` | remote_read | `nova:read` |
| `nova fleet-issue resolve` | `resolve_fleet_issue` | remote_write | `nova:read nova:write` |
| `nova defect list-photos` | `list_defect_photos` | remote_read | `nova:read` |
| `nova defect list` | `list_defects` | remote_read | `nova:read` |
| `nova defect get` | `get_defect` | remote_read | `nova:read` |
| `nova defect list-comments` | `list_defect_comments` | remote_read | `nova:read` |
| `nova defect catalog` | `get_defect_catalog` | remote_read | `nova:read` |
| `nova defect photos` | `download_defect_photos` | remote_read, local_file_write | `nova:read` |
| `nova defect pull` | `pull_defects` | remote_read, local_file_write | `nova:read` |
| `nova defect create` | `create_defect` | remote_write | `nova:read nova:write` |
| `nova defect set-category` | `set_defect_category` | remote_write | `nova:read nova:write` |
| `nova defect update` | `update_defect_title` | remote_write | `nova:read nova:write` |
| `nova defect set-cost` | `set_defect_cost` | remote_write | `nova:read nova:write` |
| `nova inspection list` | `list_inspections` | remote_read | `nova:read` |
| `nova inspection get` | `get_inspection` | remote_read | `nova:read` |
| `nova body-repair pave-image` | `download_body_repair_pave_image` | remote_read, local_file_write | `nova:read` |
| `nova body-repair documentation` | `download_body_repair_documentation` | remote_read, local_file_write | `nova:read` |
| `nova body-repair invoice` | `download_body_repair_invoice` | remote_read, local_file_write | `nova:read` |
| `nova body-repair quote` | `download_body_repair_quote` | remote_read, local_file_write | `nova:read` |
| `nova body-repair scope` | `download_body_repair_scope` | remote_read, local_file_write | `nova:read` |
| `nova body-repair list` | `list_body_repair_requests` | remote_read | `nova:read` |
| `nova body-repair create` | `create_body_repair_request` | remote_write | `nova:read nova:write` |
| `nova body-repair add-inspection-link` | `add_body_repair_inspection_link` | remote_write | `nova:read nova:write` |
| `nova body-repair replace-inspection-link` | `replace_body_repair_inspection_link` | remote_write | `nova:read nova:write` |
| `nova body-repair request-inspection-link` | `request_body_repair_inspection_link` | remote_write | `nova:read nova:write` |
| `nova body-repair get` | `get_body_repair_request` | remote_read | `nova:read` |
| `nova body-repair pave-reports` | `list_body_repair_pave_reports` | remote_read | `nova:read` |
| `nova body-repair pave-comparison` | `compare_body_repair_pave_reports` | remote_read | `nova:read` |
| `nova vehicle pave-reports` | `list_vehicle_pave_reports` | remote_read | `nova:read` |
| `nova vehicle list` | `list_vehicles` | remote_read | `nova:read` |
| `nova vehicle get` | `get_vehicle` | remote_read | `nova:read` |
| `nova vehicle list-notes` | `list_vehicle_notes` | remote_read | `nova:read` |
| `nova vehicle list-checkouts` | `list_vehicle_checkouts` | remote_read | `nova:read` |
| `nova vehicle add-note` | `add_vehicle_note` | remote_write | `nova:read nova:write` |
| `nova vehicle check-out` | `check_out_vehicle` | remote_write, local_file_read | `nova:read nova:write` |
| `nova bundle-return record` | `record_bundle_return` | remote_write | `nova:read nova:write` |
| `nova vehicle check-in` | `check_in_vehicle` | remote_write, local_file_read | `nova:read nova:write` |
| `nova vehicle create` | `create_vehicle` | remote_write | `nova:read nova:write` |
| `nova vehicle decode-vin` | `decode_vehicle_vin` | remote_read | `nova:read` |
| `nova vehicle update` | `update_vehicle` | remote_write | `nova:read nova:write` |
| `nova vehicle update-note` | `update_vehicle_note` | remote_write | `nova:read nova:write` |
| `nova vehicle delete-note` | `delete_vehicle_note` | remote_write | `nova:read nova:write` |
| `nova vehicle set-fmc-company` | `set_vehicle_fmc_company` | remote_write | `nova:read nova:write` |
| `nova health check` | `health_check` | remote_read | None |
| `nova health ready` | `health_ready` | remote_read | None |
| `nova search` | `search` | remote_read | `nova:read` |
| `nova work-order list` | `list_work_orders` | remote_read | `nova:read` |
| `nova work-order get` | `get_work_order` | remote_read | `nova:read` |
| `nova work-order assignment get` | `get_work_order_assignment` | remote_read | `nova:read` |
| `nova work-order assignment set` | `set_work_order_assignment` | remote_write | `nova:read nova:write` |
| `nova work-order scheduling-defaults` | `get_work_order_scheduling_defaults` | remote_read | `nova:read` |
| `nova work-order wait` | `wait_work_order` | remote_read | `nova:read` |
| `nova work-order line-items list` | `list_work_order_line_items` | remote_read | `nova:read` |
| `nova work-order line-items update` | `update_work_order_line_item` | remote_write | `nova:read nova:write` |
| `nova work-order list-notes` | `list_work_order_notes` | remote_read | `nova:read` |
| `nova work-order activity` | `list_work_order_activity` | remote_read | `nova:read` |
| `nova work-order create` | `create_work_order` | remote_write | `nova:read nova:write` |
| `nova work-order schedule` | `schedule_work_order` | remote_write | `nova:read nova:write` |
| `nova work-order accept` | `accept_work_order` | remote_write | `nova:read nova:write` |
| `nova work-order complete` | `complete_work_order` | remote_write, local_file_read | `nova:read nova:write` |
| `nova work-order cancel` | `cancel_work_order` | remote_write | `nova:read nova:write` |
| `nova work-order unschedule` | `unschedule_work_order` | remote_write | `nova:read nova:write` |
| `nova work-order release` | `release_work_order` | remote_write | `nova:read nova:write` |
| `nova work-order add-delay-reason` | `add_work_order_delay_reason` | remote_write | `nova:read nova:write` |
| `nova work-order decline` | `decline_work_order` | remote_write | `nova:read nova:write` |
| `nova work-order add-note` | `add_work_order_note` | remote_write | `nova:read nova:write` |
| `nova team repair-bucket-defaults` | `get_repair_bucket_defaults` | remote_read | `nova:read` |
| `nova vehicle-report list` | `list_vehicle_reports` | remote_read | `nova:read` |
| `nova vehicle-report get` | `get_vehicle_report` | remote_read | `nova:read` |
| `nova vehicle-report pull` | `pull_vehicle_reports` | remote_read, local_file_write | `nova:read` |
| `nova vehicle-report create` | `create_vehicle_report` | remote_write, local_file_read | `nova:read nova:write` |
| `nova vehicle-report resolve-vehicle` | `resolve_vehicle_report` | remote_write | `nova:read nova:write` |
| `nova vehicle-report promote` | `promote_vehicle_report` | remote_write, local_file_read | `nova:read nova:write` |
| `nova vehicle-report dismiss` | `dismiss_vehicle_report` | remote_write | `nova:read nova:write` |
| `nova notification list` | `list_notifications` | remote_read | `nova:read` |
| `nova notification unread-count` | `get_notification_counts` | remote_read | `nova:read` |
| `nova notification preferences` | `get_notification_preferences` | remote_read | `nova:read` |
| `nova notification read` | `mark_notification_read` | remote_write | `nova:read nova:write` |
| `nova notification read-all` | `mark_all_notifications_read` | remote_write | `nova:read nova:write` |
| `nova notification update-preferences` | `update_notification_preferences` | remote_write, local_file_read | `nova:read nova:write` |
| `nova notification turn-off-optional-delivery` | `turn_off_optional_notifications` | remote_write | `nova:read nova:write` |
| `nova upload photo` | `upload_photo` | remote_write, local_file_read | `nova:read nova:write` |
| `nova events head` | `events_head` | remote_read | `nova:read` |
| `nova events init` | `events_init` | remote_read, local_file_write | `nova:read` |
| `nova events watch` | `events_watch` | remote_read, local_file_write | `nova:read` |
| `nova events ack` | `events_ack` | remote_read, local_file_write | `nova:read` |
| `nova fleet-import review` | `review_cortex_file` | remote_read, local_file_read | `nova:read` |
| `nova fleet-import preview` | `preview_fleet_import` | remote_read, local_file_read | `nova:read nova:write` |
| `nova fleet-import apply` | `apply_fleet_import` | remote_write, local_file_read | `nova:read nova:write` |
| `nova defect-routing shops` | `list_defect_routing_shops` | remote_read | `nova:read` |
| `nova defect-routing resume` | `route_repair_request` | remote_write | `nova:read nova:write` |
| `nova defect-review queue` | `list_defect_review_queue` | remote_read | `nova:read` |
| `nova defect-review history` | `list_defect_reviews` | remote_read | `nova:read` |
| `nova defect-review approve` | `approve_defect_review` | remote_write | `nova:read nova:write` |
| `nova defect-review reject` | `reject_defect_review` | remote_write | `nova:read nova:write` |
| `nova repair-request list` | `list_repair_requests` | remote_read | `nova:read` |
| `nova repair-request get` | `get_repair_request` | remote_read | `nova:read` |
| `nova repair-request external-vendor-options` | `list_repair_request_external_vendor_options` | remote_read | `nova:read` |
| `nova repair-request cancel` | `cancel_repair_request` | remote_write | `nova:read nova:write` |
| `nova repair-request dismiss-rental-routing` | `dismiss_rental_routing` | remote_write | `nova:read nova:write` |
| `nova repair-request preview-external-vendor-options` | `preview_repair_request_external_vendor_options` | remote_read | `nova:read` |
| `nova report work-order-completion` | `get_work_order_completion_report` | remote_read | `nova:read` |
| `nova report repair-metrics` | `get_repair_metrics_report` | remote_read | `nova:read` |
| `nova report inspection-compliance` | `get_inspection_compliance_report` | remote_read | `nova:read` |
| `nova report inspector-performance` | `list_inspector_performance` | remote_read | `nova:read` |
| `nova report driver-da-quality` | `list_driver_da_quality` | remote_read | `nova:read` |
| `nova vendor-scorecard pending-feedback` | `list_pending_vendor_feedback` | remote_read | `nova:read` |
| `nova vendor-scorecard problem-reports` | `list_vendor_problem_reports` | remote_read | `nova:read` |
| `nova vendor-scorecard get` | `get_vendor_scorecard` | remote_read | `nova:read` |
| `nova vendor-scorecard benchmarks` | `get_vendor_scorecard_benchmarks` | remote_read | `nova:read` |
| `nova fmc-company list` | `list_fmc_companies` | remote_read | `nova:read` |


Inspection confirmations are off until the DSP enables them. Enabling the DSP
setting does not enroll any recipient or alter other notification preferences.
Use `inspection-confirmation set-settings DSP-7 --enabled` to enable the DSP;
use `--no-enabled` to disable it. Recipient roles are `owners`, `dispatchers`,
or `owners_and_dispatchers`. Only supplied fields are sent.

Use `inspection-confirmation respond DVIC-7 --response Y --expected-scheduled-at
2026-10-28T02:00:00Z --expected-confirmation-id 17` to confirm one unchanged appointment. N declines that
occurrence only. A response does not record a key count or complete an inspection.
Read the confirmation before another attempt if the outcome is unknown. These
operations require new explicit assistant consent and the caller's live scope.

Use the `confirmation_id` from the current read as `--expected-confirmation-id`.
An old response cannot apply after the appointment changes, even if its time is restored.

## Vendor agreement

Run `nova vendor-agreement status` to read whether your organization must accept
an agreement. The result includes the version label and `review_url`. A vendor
administrator must open that link and sign personally. One signature applies to
the organization; a new published version requires a new signature. This command
and its local MCP tool cannot sign. New connections must consent to
`vendor_agreement.status.get.v1`; existing connections need renewed consent.

## Shared DSP bundle setting

`nova bundle-sharing get DSP-7` reads the one setting.
`nova bundle-sharing set DSP-7 --enabled` enables it; `--no-enabled` disables it
and withdraws open offers containing that DSP's vans. It defaults on. The DSP's
owner/admin or a site admin can change it. No second opt-in is required.

MCP exposes `get_bundle_sharing` and `set_bundle_sharing` with a required boolean
`enabled` for writes. The API owns role, tenant, credential revocation and audit
checks. The server must support the shared setting. No second permission is required.

### Bundle pickup and return schedules

Use `nova bundle-schedules list` to read the pickup and return windows and the current
version. Pickup can use a shop-selected time window; the return window remains
midnight to 5 a.m. The API validates pickup dates and DSP approval versions. Use `nova bundle-schedules decide REF UNIT --version VERSION
--decision approved` (or `declined`) for that exact proposal. A changed schedule
needs a new decision. The same named MCP tools require the listed operation
permissions. Read the schedule again after a conflict or an unknown outcome.
permissions. Read the schedule again after a conflict or an unknown outcome.

### Bundle drop-off address

Change every van's drop-off address before any van in that bundle is scheduled or
charged. `bundle-address set REF --delivery-address ADDRESS --save-profile` also
saves the shop profile only when you have profile access. Without `--save-profile`,
the profile stays unchanged. Read after an uncertain outcome before trying again.
New connections need explicit consent. Service-account credentials can edit the
bundle destination, but cannot save the profile because its API does not admit them.


Use `defect-routing shops --vehicle-id VAN-7 --repair-type mechanical` to check the shop's
`eligible_for_repair_type` value. Use the existing `defect-review approve FD-7 --vendor-workshop-id 3`
for an unapproved defect. Use `defect-routing resume RR-7 --vendor-workshop-id 3` for an open request.
Both new tools require fresh consent for `vendor_workshops.list.v1` and `repair_requests.route.v1`.
A successful approval can wait for rental approval; inspect the returned routing state.

Usa `defect-routing shops` para comprobar los talleres elegibles. Usa `defect-review approve` para
aprobar un defecto pendiente y `defect-routing resume` para asignar una solicitud abierta.
Los permisos existentes no incluyen estas operaciones nuevas. Autoriza la conexión de nuevo.

| Command | MCP tool | Effects | Scope |
| --- | --- | --- | --- |
| `nova pave-scan request` | `request_vehicle_pave_scan` | remote_write | `nova:read nova:write` |
| `nova pave-scan cancel-request` | `cancel_vehicle_pave_scan_request` | remote_write | `nova:read nova:write` |
| `nova pave-scan upcoming` | `list_dsp_pave_scans` | remote_read | `nova:read` |
| `nova pave-scan request-change` | `request_pave_scan_schedule_change` | remote_write | `nova:read nova:write` |
| `nova pave-scan platform-list` | `list_platform_pave_scans` | remote_read | `nova:read` |
| `nova pave-scan workshop-list` | `list_workshop_pave_scans` | remote_read | `nova:read` |
| `nova pave-scan platform-schedule` | `set_platform_pave_scan_schedule` | remote_write | `nova:read nova:write` |
| `nova pave-scan workshop-schedule` | `set_workshop_pave_scan_schedule` | remote_write | `nova:read nova:write` |
| `nova pave-scan platform-cancel` | `cancel_platform_pave_scan` | remote_write | `nova:read nova:write` |
| `nova pave-scan workshop-cancel` | `cancel_workshop_pave_scan` | remote_write | `nova:read nova:write` |
| `nova inspection-recap report` | `get_first_inspection_recap_report` | remote_read | `nova:read` |
| `nova vendor-referral list` | `list_vendor_referrals` | remote_read | `nova:read` |
| `nova vendor-referral submit` | `submit_vendor_referral` | remote_write | `nova:read nova:write` |

| `nova defect opportunities` | `list_defect_opportunities` | remote_read | `nova:read` |
| `nova defect accept` | `accept_defect` | remote_write | `nova:read nova:write` |
| `nova defect reject` | `reject_defect` | remote_write | `nova:read nova:write` |

See [Body quote workflow](BodyQuotes.md) for shop quote commands and permissions.
See [bought bundle shop steps](BundleShopSteps.md) for safe actions and browser handoffs.
Consulta los [pasos del paquete](BundleShopSteps.md) para las acciones y el enlace al navegador.
| `nova vendor-scorecard rate-work-order` | `rate_work_order` | remote_write | `nova:read nova:write` |
| `nova vendor-scorecard request-correction` | `request_work_order_correction` | remote_write | `nova:read nova:write` |
| `nova vendor-scorecard rate-body-repair` | `rate_body_repair` | remote_write | `nova:read nova:write` |

## Shop ratings

Read `list_pending_vendor_feedback` and select exactly one repair. Confirm the
rating with the user before sending. Use `rate_work_order` to approve work,
`request_work_order_correction` to ask the shop to fix it again, or
`rate_body_repair` for a body repair. Confirm a correction request separately:
it reopens the work order or creates correction work. A correction needs a reason.

The local correction tool is listed only after this client completes consent
for correction. Existing connections must sign in again to record this consent.
This local record is a discovery hint; the API checks live grants on every write.

Ordinary ratings require `vendor_scorecard.feedback.submit.v1`; correction
requests require `vendor_scorecard.feedback.correction.v1` instead. Delegated
connections need write scope and fresh explicit consent. Existing grants do not
gain permissions. The API checks role, tenant, bound acting user and Station.
DSP owners, managers and dispatchers rate their own fleet. Site admins can rate
work orders but cannot rate body repairs. Machine access retains native key,
role, tenant, acting-user and Station checks.

Work orders accept optional `reason`, `escalate`, `impressive_attribute` and
`negative_attribute`. Attributes are `turnaround_time`, `communication`,
`professionalism`, `work_quality` or `price`. The approval tool fixes vote/decision
to `up`/`approved`; the correction tool fixes them to `down`/`correction_requested`.
Body repairs accept integer `stars` (1–5), unique `tags` and optional `reason`.
Tag topics are `repair_quality`, `van_condition`, `communication`, `pickup_return`.
Use `good_` tags for 5 stars, either prefix for 4, and `problem_` tags for 1–3.
Ratings of 1 or 2 stars escalate automatically. Subject fields cannot be mixed.
Reasons accept at most 1000 characters. Body ratings need completed hand-back,
custody, eligibility, the enabled rating setting and the 14-day change window.

`escalate` defaults to false. If true, this rating counts toward the second-vendor
trigger. It can open a `SCORECARD_SECOND_VENDOR` case for Nova platform staff.
Get the user's explicit approval before setting it to true.
`reason` explains the rating. `impressive_attribute` selects a strong point;
`negative_attribute` selects a weak point. Attribute choices are turnaround time,
communication, professionalism, work quality and price.

`escalate` tiene el valor predeterminado false. Con true, la calificación cuenta
para el criterio de un segundo proveedor. Puede abrir un caso
`SCORECARD_SECOND_VENDOR` para el personal de la plataforma Nova. Obtén la
aprobación explícita del usuario antes de usar true. `reason` explica la
calificación; `impressive_attribute` indica un punto positivo y
`negative_attribute` un punto negativo.

Errors preserve the distinction between invalid choices (400), sign-in (401),
permission refusal (403), missing repair (404), repair state/custody/deadline
conflict (409), schema errors (422), and unavailable body ratings (503). Repeated
submissions use native update/supersession; there is no duplicate-rating error.
An uncertain response requires reading the repair before another attempt. Writes
are never retried automatically.

Confirma la calificación con el usuario antes de enviarla. Para pedir al taller
que repare el trabajo de nuevo, confirma también la solicitud de corrección.
Esta solicitud vuelve a abrir la orden o crea trabajo de corrección y requiere
un motivo y el permiso de corrección. Las calificaciones normales usan el permiso
de envío. Usa un máximo de 1000 caracteres para el motivo. No mezcles los campos
de carrocería con los de una orden de trabajo. Consulta la reparación después
de un resultado desconocido antes de intentar de nuevo.

Commands: `nova vendor-scorecard rate-work-order WO-7`,
`nova vendor-scorecard request-correction WO-7 --reason "Repair the finish"`,
and `nova vendor-scorecard rate-body-repair BRR-7 --stars 5 --tags good_repair_quality`.
Repeat `--tags` for multiple tags. Read each command's `--help` for optional fields.

## Team and Roger setup

| Command | MCP tool | Effects | Scope |
| --- | --- | --- | --- |
| `nova team-invitation list` | `list_team_invitations` | remote_read | `nova:read` |
| `nova team-invitation invite` | `invite_team_member` | remote_write | `nova:read nova:write` |
| `nova team-invitation resend` | `resend_team_invitation` | remote_write | `nova:read nova:write` |
| `nova team-invitation revoke` | `revoke_team_invitation` | remote_write | `nova:read nova:write` |
| `nova roger status` | `get_slack_status` | remote_read | `nova:read` |
| `nova roger start` | `start_slack_setup` | remote_write | `nova:read nova:write` |
| `nova roger channel` | `set_roger_intake_channel` | remote_write | `nova:read nova:write` |

| `nova body-repair select-quote` | `select_body_repair_quote` | remote_write | `nova:read nova:write` |
| `nova body-repair confirm-pickup` | `confirm_body_repair_pickup` | remote_write | `nova:read nova:write` |
| `nova body-repair accept-pickup` | `accept_body_repair_pickup` | remote_write | `nova:read nova:write` |

See [DSP Body repair decisions](../README.md#dsp-body-repair-decisions) for quote selection, versioned pickup, and browser sign-off/payment.

`nova auth login` includes `announcements` with current public features and repair
offers. Run `nova announcements --json` or MCP `get_announcements` to refresh it.
The feed needs no credentials and never grants permissions or authorizes a repair.
Local MCP initialization includes the same bilingual feed. Check promotion expiry
and all terms before acting. An unavailable feed does not stop login or connection.

The feed also advertises Nova's Markdown skill library through `skill_library_url`.
The link is permanent and can be shown with an empty news feed. No skill content
is fetched, installed or generated. The initial index contains no skills; creating
a skill requires explicit user authorization for that skill or workflow.

Site admins can read a PM/AMR bundle with `bundle-fee get REF`, then waive its
whole fee with `bundle-fee waive REF --reason "Approved waiver" --revision N`.
The waiver works before sending or after award, cannot be undone, and does not
refund a started charge. `get_admin_bundle` and `waive_bundle_fee` are the same
operations in local MCP. Delegated clients need fresh
`capacity.offers.staff.get.v1` and `capacity.fee.waive.v1` consent. The API keeps
role/tenant checks and records the actual principal. After an unknown outcome,
read the bundle before trying again. The API owns role and tenant authorization.
### Repair category corrections

`nova defect set-category FD-42 --repair-group CMR --expected-updated-at 2026-11-10T12:00:00Z` requires site-admin access.
Read the defect first and use its exact `updated_at` value. The MCP tool is `set_defect_category`, available through local stdio and hosted MCP.
The dedicated consent is `defects.category.update.v1`; existing title-edit consent does not permit category changes.
Supported values: AMR, CMR, CNMR, Body, PM, Tires, Detailing, Netradyne. A correction does not reroute work or rewrite quotes or billing.

Solo los administradores del sitio pueden cambiar la categoría de reparación. Consulta primero el defecto y usa su valor exacto de `updated_at`.
El permiso es `defects.category.update.v1`. El cambio queda registrado y no cambia el taller, los presupuestos ni la facturación existentes.


### Inspection quality review / Revisión de calidad de inspecciones

| Command | MCP tool | Effects | Scope |
|---|---|---|---|
| `nova inspection-review queue` | `list_inspection_reviews` | remote_read | `nova:read` |
| `nova inspection-review show` | `get_inspection_review` | remote_read | `nova:read` |
| `nova inspection-review start` | `start_inspection_review` | remote_write | `nova:read nova:write` |
| `nova inspection-review set` | `set_inspection_review_item` | remote_write | `nova:read nova:write` |
| `nova inspection-review unset` | `unset_inspection_review_item` | remote_write | `nova:read nova:write` |
| `nova inspection-review preview` | `preview_inspection_review` | remote_read | `nova:read` |
| `nova inspection-review complete` | `complete_inspection_review` | remote_write | `nova:read nova:write` |
| `nova inspection-review quality` | `get_inspector_quality` | remote_read | `nova:read` |
| `nova inspection-review feedback` | `list_inspection_review_feedback` | remote_read | `nova:read` |
| `nova inspection-review feedback-summary` | `get_inspection_review_feedback_summary` | remote_read | `nova:read` |
| `nova inspection-review feedback-seen` | `mark_inspection_review_feedback_seen` | remote_write | `nova:read nova:write` |

Site admins can review platform inspections. `set REVIEW OBSERVATION --verdict ...`
saves the verdict and an optional comment as a draft: nothing changes for the DSP or
shop until you complete the review. `--comment ""` clears a saved comment and
`unset REVIEW OBSERVATION` clears the draft. `preview REVIEW [--confirm-remaining]`
lists what completing will do (DSP queue removals, shop request withdrawals, group
changes, comments and who can read them, ungrounding, and the inspector's score
change) and changes nothing. `complete REVIEW [--confirm-remaining]` fetches a
preview, prints its effects, then completes with that preview's token; add
`--preview-token TOKEN` to complete a preview you already read. Every defect needs a
decision, and `--confirm-remaining` confirms the undecided ones. If a defect changed
after the preview, nothing is applied, the new effects are printed and the command
stops; it never retries. The `complete_inspection_review` tool requires the
`preview_token` from `preview_inspection_review`, so show its effects before
completing. A stale preview returns `inspection_review_preview_stale` with the new
effects and no token.

An invalid finding after the decision window closes affects only the score. Category
changes preserve routing and prices. Inspectors can read their own quality and
feedback. `feedback-summary` returns the unseen count, latest review and score shown
on the Home card. `feedback-seen ITEM` is the Got it action: only the inspector who
owns the item can use it, and Nova sends no push or email. Each command needs its
dedicated operation consent. Read the review before another attempt when a change
outcome is unknown.

Los administradores del sitio pueden revisar inspecciones de la plataforma. `set`
guarda el resultado y un comentario opcional como borrador: nada cambia para el DSP ni
el taller hasta que completes la revisión. `--comment ""` borra el comentario y
`unset` borra el borrador. `preview` muestra lo que hará completar la revisión sin
cambiar nada. `complete` obtiene una vista previa, muestra sus efectos y completa con
su token; usa `--preview-token` para completar una vista previa que ya revisaste. Si
un defecto cambió después de la vista previa, no se aplica nada, se muestran los
nuevos efectos y el comando se detiene sin reintentar. La herramienta
`complete_inspection_review` requiere el `preview_token` de
`preview_inspection_review`. Un hallazgo no válido después del plazo de decisión solo
afecta la puntuación. Los cambios de categoría mantienen el taller y los precios.
Cada inspector puede consultar su propia calidad y comentarios. `feedback-summary`
devuelve los comentarios sin ver, la última revisión y la puntuación. `feedback-seen`
marca un comentario propio como visto; no se envían notificaciones push ni correos.
Cada comando requiere su permiso específico. Consulta la revisión antes de otro
intento si no se conoce el resultado de un cambio.


Inspection queue filters: `--status unreviewed|in_progress|completed|all`,
`--dsp-id`, `--inspector-id`, `--station-code`, `--submitted-since` (a time with a time
zone), `--has-critical`, `--limit` (default 50, maximum 200), and `--offset` (default 0).
Feedback accepts `--inspector-id`, `--days` (default 30), `--verdict
corrections|confirmed|all` (default `corrections`), `--unseen`, `--limit` (default 100),
and `--offset`. Quality also defaults to 30 days. Feedback summary
accepts `--inspector-id` and `--days`; site admins must give `--inspector-id`, and
inspectors read their own. Only the inspector who owns an item can mark it seen
(admins and service accounts get 403). Use `offset + limit` to request
the next page. MCP uses the same field names with underscores, for example
`submitted_since` and `inspector_id`.

Filtros de la cola: `--status unreviewed|in_progress|completed|all`, `--dsp-id`,
`--inspector-id`, `--station-code`, `--submitted-since` (con zona horaria),
`--has-critical`, `--limit` (50 por defecto, máximo 200) y `--offset` (0 por defecto).
Los comentarios aceptan `--inspector-id`, `--days` (30 por defecto), `--verdict`
(`corrections` por defecto), `--unseen`, `--limit` y `--offset`. La calidad también usa
30 días por defecto. El resumen acepta `--inspector-id` y
`--days`; los administradores deben indicar `--inspector-id`. Solo el inspector al que
pertenece un comentario puede marcarlo como visto. Usa `offset + limit` para solicitar la página siguiente.
Las herramientas MCP usan los mismos nombres de campo con guiones bajos.
