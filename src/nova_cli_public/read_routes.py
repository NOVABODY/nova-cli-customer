"""Fixed customer GET routes. The server enforces each operation grant."""

import re

PDF_ROUTES = {
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}/invoice": "body_repair.documents.invoice.read.v1",
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}/quote": "body_repair.documents.quote.read.v1",
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}/scope": "body_repair.documents.scope.read.v1",
}

READ_ROUTES = {
    r"/inspection-confirmations/settings/(?:DSP-)?[0-9]{1,14}": "inspection_confirmations.settings.get.v1",
    r"/inspection-confirmations/(?:DVIC-)?[0-9]{1,14}": "inspection_confirmations.get.v1",
    r"/dashboards/dsp/(?:DSP-)?[0-9]{1,14}/daily-work-summary": "dashboards.dsp_daily_work_summary.get.v1",
    r"/dashboards/dsp/(?:DSP-)?[0-9]{1,14}/scheduled-work": "dashboards.dsp_scheduled_work.list.v1",
    r"/dashboards/inspector-performance": "reports.inspector_performance.list.v1",
    r"/dashboards/driver-da-quality": "reports.driver_da_quality.list.v1",
    r"/vendor-scorecard/pending-feedback": "vendor_scorecard.pending_feedback.list.v1",
    r"/vendor-scorecard/problem-reports": "vendor_scorecard.problem_reports.list.v1",
    r"/fmc-companies": "fmc_companies.list.v1",
    r"/vendor-scorecard/(?:VW-)?[0-9]{1,14}": "vendor_scorecard.get.v1",
    r"/vendor-scorecard/(?:VW-)?[0-9]{1,14}/benchmarks": "vendor_scorecard.benchmarks.get.v1",
    **{r"/dashboards/reports/" + name.replace("_", "-"): "reports." + name + ".get.v1"
       for name in ("work_order_completion", "repair_metrics", "inspection_compliance")},

    r"/fleet-updates": "fleet_updates.list.v1",
    r"/repair-requests": "repair_requests.list.v1",
    r"/repair-requests/(?:RR-)?[0-9]{1,14}": "repair_requests.get.v1",
    r"/repair-requests/(?:RR-)?[0-9]{1,14}/external-vendor-options": "repair_requests.external_vendor_options.list.v1",
    r"/vehicles/decode-vin/[A-HJ-NPR-Z0-9]{17}": "vehicles.decode_vin.v1",
    r"/inspections": "inspections.list.v1",
    r"/inspections/(?:INS-)?[0-9]{1,14}": "inspections.get.v1",
    r"/defect-reviews/queue": "defect_reviews.queue.list.v1",
    r"/defect-reviews/defect/(?:FD-)?[0-9]{1,14}": "defect_reviews.list.v1",
    r"/body-repair/pave/image": "body_repair.pave.images.read.v1",
    **PDF_ROUTES,
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}/documentation": "body_repair.documents.documentation.read.v1",
    r"/body-repair/requests": "body_repair.requests.list.v1",
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}": "body_repair.requests.get.v1",
    r"/vehicles/(?:VAN-)?[0-9]+/pave-reports": "vehicles.pave_reports.list.v1",
    r"/body-repair/requests/(?:BRR-)?[0-9]+/pave": "body_repair.pave.list.v1",
    r"/body-repair/requests/(?:BRR-)?[0-9]+/pave/comparison": "body_repair.pave.compare.v1",
    r"/workshop-events": "workshop_events.list.v1",
    r"/auth/me": "identity.get.v1",
    r"/search": "search.list.v1",
    r"/teams/repair-bucket-defaults": "teams.repair_bucket_defaults.v1",
    r"/vehicles": "vehicles.list_full.v1",
    r"/vehicles/(?:VAN-)?[0-9]+": "vehicles.get_full.v1",
    r"/vehicles/(?:VAN-)?[0-9]+/notes": "vehicles.notes.list.v1",
    r"/vehicles/(?:VAN-)?[0-9]+/checkouts": "vehicles.checkouts.list.v1",
    r"/work-orders": "work_orders.list.v1",
    r"/work-orders/(?:WO-)?[0-9]+": "work_orders.get.v1",
    r"/work-orders/(?:WO-)?[0-9]+/assignment": "work_orders.assignment.get.v1",
    r"/work-orders/(?:WO-)?[0-9]+/scheduling-defaults": "work_orders.scheduling_defaults.get.v1",
    r"/work-orders/(?:WO-)?[0-9]+/notes": "work_orders.notes.list.v1",
    r"/work-orders/(?:WO-)?[0-9]+/activity": "work_orders.activity.list.v1",
    r"/vehicle-reports": "vehicle_reports.list.v1",
    r"/vehicle-reports/(?:VR-)?[0-9]+": "vehicle_reports.get.v1",
    r"/defects": "defects.list.v1",
    r"/defects/(?:FD-)?[0-9]+": "defects.get.v1",
    r"/defects/(?:FD-)?[0-9]+/comments": "defects.comments.list.v1",
    r"/defects/(?:FD-)?[0-9]+/photos": "defects.photos.list.v1",
    r"/defect-catalog": "defect_catalog.get.v1",
    r"/notifications": "notifications.list.v1",
    r"/notifications/unread-count": "notifications.counts.get.v1",
    r"/notifications/preferences": "notifications.preferences.get.v1",
    # Existing projected fleet clients keep their original consent contract.
    r"/assistant/vehicles": "vehicles.list.v1",
    r"/assistant/vehicles/(?:VAN-)?[0-9]+": "vehicles.get.v1",
    r"/assistant/work-orders": "work_orders.list.v1",
    r"/assistant/work-orders/(?:WO-)?[0-9]+": "work_orders.get.v1",
    r"/assistant/defects": "defects.list.v1",
    r"/assistant/defects/(?:FD-)?[0-9]+": "defects.get.v1",
}
PUBLIC_READS = {"/health", "/health/ready"}


def admitted_read(path):
    return any(re.fullmatch(pattern, path) for pattern in READ_ROUTES)


READ_POST_ROUTES = {"/repair-requests/external-vendor-options/prepare": "repair_requests.external_vendor_options.preview.v1", "/vehicles/fleet-import/parse": "vehicles.fleet_import.review.v1"}
