"""Fixed delegated customer write routes and separately consented photo commits."""

import re

WRITE_ROUTES = {
    ("PATCH", r"/inspection-confirmations/settings/(?:DSP-)?[0-9]{1,14}"): "inspection_confirmations.settings.update.v1",
    ("POST", r"/inspection-confirmations/(?:DVIC-)?[0-9]{1,14}/respond"): "inspection_confirmations.respond.v1",
    ("POST", r"/dashboards/dsp/(?:DSP-)?[0-9]{1,14}/daily-work-summary/[0-9]{4}-[0-9]{2}-[0-9]{2}/acknowledge"): "dashboards.dsp_daily_work_summary.acknowledge.v1",
    ("PUT", r"/vehicles/(?:VAN-)?[0-9]{1,14}/fmc-company"): "vehicles.fmc_company.update.v1",
    ("POST", r"/repair-requests/(?:RR-)?[0-9]{1,14}/dismiss-rental-routing"): "repair_requests.rental_routing.dismiss.v1",
    ("POST", r"/fleet-issues/[0-9]{1,14}/resolve"): "fleet_issues.resolve.v1",

    ("POST", r"/repair-requests/(?:RR-)?[0-9]{1,14}/cancel"): "repair_requests.cancel.v1",
    ("PATCH", r"/vehicles/(?:VAN-)?[0-9]{1,14}/notes/[0-9]{1,14}"): "vehicles.notes.update.v1",
    ("DELETE", r"/vehicles/(?:VAN-)?[0-9]{1,14}/notes/[0-9]{1,14}"): "vehicles.notes.delete.v1",
    ("POST", r"/defects/(?:FD-)?[0-9]{1,14}/cost"): "defects.cost.set.v1",
    ("POST", r"/vehicles"): "vehicles.create.v1",
    ("PATCH", r"/vehicles/(?:VAN-)?[0-9]{1,14}"): "vehicles.update.v1",
    ("POST", r"/defect-reviews/defect/(?:FD-)?[0-9]{1,14}/approve"): "defect_reviews.approve.v1",
    ("POST", r"/defect-reviews/defect/(?:FD-)?[0-9]{1,14}/reject"): "defect_reviews.reject.v1",
    ("POST", r"/defects"): "defects.create.v1",
    ("POST", r"/vehicles/bulk-upsert"): "vehicles.fleet_import.apply.v1",
    ("POST", r"/work-orders/manual"): "work_orders.create.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/assignment"): "work_orders.assignment.update.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/schedule"): "work_orders.schedule.update.v1",
    ("PATCH", r"/work-orders/(?:WO-)?[0-9]+/line-items/[0-9]+"): "work_orders.line_items.update.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/accept"): "work_orders.accept.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/complete"): "work_orders.complete.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/cancel"): "work_orders.cancel.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/unschedule"): "work_orders.unschedule.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/release"): "work_orders.release.v1",
    (
        "POST",
        r"/work-orders/(?:WO-)?[0-9]+/defects/(?:FD-)?[0-9]+/delay-reasons",
    ): "work_orders.delay_reasons.create.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/decline"): "work_orders.decline.v1",
    ("POST", r"/work-orders/(?:WO-)?[0-9]+/notes"): "work_orders.notes.create.v1",
    ("POST", r"/vehicles/(?:VAN-)?[0-9]+/notes"): "vehicles.notes.create.v1",
    ("POST", r"/vehicles/(?:VAN-)?[0-9]+/check-out"): "vehicles.check_out.v1",
    ("POST", r"/vehicles/(?:VAN-)?[0-9]+/check-in"): "vehicles.check_in.v1",
    ("POST", r"/vehicle-reports"): "vehicle_reports.create.v1",
    (
        "POST",
        r"/vehicle-reports/(?:VR-)?[0-9]+/resolve-vehicle",
    ): "vehicle_reports.resolve_vehicle.v1",
    ("POST", r"/vehicle-reports/(?:VR-)?[0-9]+/promote"): "vehicle_reports.promote.v1",
    ("POST", r"/vehicle-reports/(?:VR-)?[0-9]+/dismiss"): "vehicle_reports.dismiss.v1",
    ("PATCH", r"/defects/(?:FD-)?[0-9]+"): "defects.title.update.v1",
    ("PATCH", r"/notifications/[0-9]+/read"): "notifications.mark_read.v1",
    ("POST", r"/notifications/read-all"): "notifications.mark_all_read.v1",
    ("PUT", r"/notifications/preferences"): "notifications.preferences.update.v1",
    ("POST", r"/uploads/presigned"): "uploads.presign.v1",
    ("POST", r"/defects/(?:FD-)?[0-9]+/photos"): "defects.photos.create.v1",
    ("POST", r"/inspections/(?:INS-)?[0-9]+/photos"): "inspections.photos.create.v1",
    ("POST", r"/vehicle-reports/(?:VR-)?[0-9]+/photos"): "vehicle_reports.photos.create.v1",
}


def admitted_write(method, path):
    return any(method == verb and re.fullmatch(pattern, path) for verb, pattern in WRITE_ROUTES)


PHOTO_COMMIT_GRANTS = {
    "defect": "defects.photos.create.v1",
    "inspection": "inspections.photos.create.v1",
    "vehicle_report": "vehicle_reports.photos.create.v1",
}
