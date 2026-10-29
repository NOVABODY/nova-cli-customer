# Command reference

Generated from this release's `nova capabilities --json`. Use that command for full
input schemas, required arguments, examples and permissions. The table describes
client support; the server checks current account access.

| Command | Local MCP tool | Effect | Scope |
| --- | --- | --- | --- |
| `nova vendor-agreement status` | `get_vendor_agreement_status` | remote_read | `nova:read` |
| `nova inspection-confirmation settings` | `get_inspection_confirmation_settings` | remote_read | `nova:read` |
| `nova inspection-confirmation set-settings` | `update_inspection_confirmation_settings` | remote_write | `nova:read nova:write` |
| `nova inspection-confirmation get` | `get_inspection_confirmation` | remote_read | `nova:read` |
| `nova inspection-confirmation respond` | `respond_inspection_confirmation` | remote_write | `nova:read nova:write` |
| `nova capabilities` | CLI setup | local_read | None |
| `nova profile set` | CLI setup | local_config_write | None |
| `nova profile use` | CLI setup | local_config_write | None |
| `nova profile show` | CLI setup | local_read | None |
| `nova profile remove` | CLI setup | local_config_write, local_credentials_delete | None |
| `nova profile list` | CLI setup | local_read | None |
| `nova auth login` | CLI setup | browser_handoff, remote_authorization, local_credentials_write | `nova:read` |
| `nova auth status` | CLI setup | local_credentials_read | None |
| `nova auth refresh` | CLI setup | remote_authorization, local_credentials_write | `nova:read` |
| `nova auth logout` | CLI setup | local_credentials_delete | None |
| `nova auth whoami` | `whoami` | remote_read | `nova:read` |
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
| `nova body-repair get` | `get_body_repair_request` | remote_read | `nova:read` |
| `nova body-repair pave-reports` | `list_body_repair_pave_reports` | remote_read | `nova:read` |
| `nova body-repair pave-comparison` | `compare_body_repair_pave_reports` | remote_read | `nova:read` |
| `nova vehicle pave-reports` | `list_vehicle_pave_reports` | remote_read | `nova:read` |
| `nova vehicle list` | `list_vehicles` | remote_read | `nova:read` |
| `nova vehicle get` | `get_vehicle` | remote_read | `nova:read` |
| `nova vehicle list-notes` | `list_vehicle_notes` | remote_read | `nova:read` |
| `nova vehicle list-checkouts` | `list_vehicle_checkouts` | remote_read | `nova:read` |
| `nova vehicle add-note` | `add_vehicle_note` | remote_write | `nova:read nova:write` |
| `nova vehicle check-out` | `check_out_vehicle` | remote_write | `nova:read nova:write` |
| `nova vehicle check-in` | `check_in_vehicle` | remote_write | `nova:read nova:write` |
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
| `nova work-order complete` | `complete_work_order` | remote_write | `nova:read nova:write` |
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
| `nova vehicle-report create` | `create_vehicle_report` | remote_write | `nova:read nova:write` |
| `nova vehicle-report resolve-vehicle` | `resolve_vehicle_report` | remote_write | `nova:read nova:write` |
| `nova vehicle-report promote` | `promote_vehicle_report` | remote_write | `nova:read nova:write` |
| `nova vehicle-report dismiss` | `dismiss_vehicle_report` | remote_write | `nova:read nova:write` |
| `nova notification list` | `list_notifications` | remote_read | `nova:read` |
| `nova notification unread-count` | `get_notification_counts` | remote_read | `nova:read` |
| `nova notification preferences` | `get_notification_preferences` | remote_read | `nova:read` |
| `nova notification read` | `mark_notification_read` | remote_write | `nova:read nova:write` |
| `nova notification read-all` | `mark_all_notifications_read` | remote_write | `nova:read nova:write` |
| `nova notification update-preferences` | `update_notification_preferences` | remote_write | `nova:read nova:write` |
| `nova notification turn-off-optional-delivery` | `turn_off_optional_notifications` | remote_write | `nova:read nova:write` |
| `nova upload photo` | `upload_photo` | remote_write, local_file_read | `nova:read nova:write` |
| `nova events head` | `events_head` | remote_read | `nova:read` |
| `nova events init` | `events_init` | remote_read, local_file_write | `nova:read` |
| `nova events watch` | `events_watch` | remote_read, local_file_write | `nova:read` |
| `nova events ack` | `events_ack` | remote_read, local_file_write | `nova:read` |
| `nova fleet-import review` | `review_cortex_file` | remote_read, local_file_read | `nova:read` |
| `nova fleet-import preview` | `preview_fleet_import` | remote_read, local_file_read | `nova:read nova:write` |
| `nova fleet-import apply` | `apply_fleet_import` | remote_write, local_file_read | `nova:read nova:write` |
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
