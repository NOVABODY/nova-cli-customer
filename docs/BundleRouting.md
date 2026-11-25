# Route repairs to a bundle vendor

Use the existing `route_repair_request` tool with an exact workshop. A bundle
vendor returns `routing_outcome: bundle_queue`. No new work order is created.
An empty work-order list is a valid queue result. Read the repair request after
an unknown outcome before another attempt. Existing role, tenant, scope,
consent, and revocation rules apply.

Only an explicit request to a selected shop receives priority and a requested
mark. Automatic routing keeps normal ranking. `create_admin_bundle` accepts
`requested_vendor_id` as the destination organization. It is independent of
`pricing_vendor_id`. The API owns the queue, ranking, eligibility and binding;
these client changes do not deploy the API or publish a package.

## Asigna reparaciones a un proveedor de paquetes

Usa `route_repair_request` con un taller concreto. Un proveedor de paquetes
devuelve `routing_outcome: bundle_queue`. No se crea una orden de trabajo.
Una lista de órdenes vacía es un resultado válido. Consulta la solicitud si el
resultado es desconocido antes de intentarlo otra vez. Se conservan las reglas
de función, organización, permisos, consentimiento y revocación.

Solo una solicitud explícita a un taller seleccionado recibe prioridad y la
marca de solicitado. La asignación automática conserva el orden normal.
`create_admin_bundle` acepta `requested_vendor_id` como la organización de
destino. Es independiente de `pricing_vendor_id`. La API controla la cola, el
orden, los requisitos y el destino. Estos cambios no despliegan la API ni
publican un paquete.
