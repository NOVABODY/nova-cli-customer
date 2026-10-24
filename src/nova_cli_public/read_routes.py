"""Fixed customer GET routes. The server enforces each operation grant."""

import re

PDF_ROUTES = {
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}/invoice": "body_repair.documents.invoice.read.v1",
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}/quote": "body_repair.documents.quote.read.v1",
    r"/body-repair/requests/[A-Za-z0-9_-]{1,64}/scope": "body_repair.documents.scope.read.v1",
}

READ_ROUTES = {
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


READ_POST_ROUTES = {"/vehicles/fleet-import/parse": "vehicles.fleet_import.review.v1"}
