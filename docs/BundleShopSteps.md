# Shop steps without payment writes

## Bought bundle shop steps

These tools require the matching server operations. Client installation does
not prove that a server has these operations enabled.

Read `list_bought_bundle_vans` (`bundle-workflow vans REF`) first. Use the
per-van `workflow.action`. Keep the API's `browser_url` from offer rows, the
report root and every van, including lapsed vans. Open that exact URL to buy a
bundle, set initial pickup readiness, or change a payment method. These browser
actions can change payment state. There are no tools for bundle acceptance,
readiness or payment changes.

| Action | Tool | CLI command | Operation |
| --- | --- | --- | --- |
| `send_details` | `get_bundle_fmc_packet_pdf` | `bundle-shop fmc-pdf REF UNIT --out packet.pdf` | `capacity.fmc_packet.get.v1` |
| `change_schedule`; `book_pickup` for a paid/waived van | `update_bundle_pickup` | `bundle-shop pickup REF UNIT --start ISO --end ISO [--estimated-return-date YYYY-MM-DD]` | `capacity.pickup.update.v1` |
| `confirm_no_charge` | `confirm_bundle_no_charge` | `bundle-shop confirm-no-charge REF UNIT` | `capacity.no_charge.confirm.v1` |
| `contact_nova` | `request_bundle_contact` | `bundle-shop contact REF UNIT` | `capacity.contact.create.v1` |

Nova does not send the PDF to the FMC. Submit it through the shop's channel.
Use the existing `upload_capacity_evidence` / `capacity-evidence upload` with
`kind=pending` to record submission evidence. For `record_authorization`, use
`kind=authorization`, `authorization_number` and the file's `content_type` and
`content_base64`. The operation is `capacity.evidence.upload.v1`. CMR vans do
not use FMC packets, FMC evidence or the no-charge exit.

Pickup dates need UTC offsets. The API checks the future window, shop timezone,
six-day limit, return within 96 hours, live readiness and DSP approval. Initial
readiness for an unpaid van remains in the browser. The no-charge exit requires
reviewed declines and zero price; it refuses existing payment activity. Contact
requires a lapsed van with debt. Keep `requested` and `already_requested` distinct;
a repeated contact request does not create another notice or pay debt.

Writes require explicit write authority and the exact operation grant. The API
checks shop role, awarded organization, live policy and acting-user bindings.
Writes allow vendor administrators and service writers. Packet reads also allow
foremen, technicians and vendor viewers.
Existing hosted connections need fresh consent. A confirmed write refreshes
`GET /vans`. If the refresh fails, keep the receipt, report `refresh_required`
and read the vans before another step. Never repeat an uncertain write.

Errors retain localized API details and refusal codes. Reconnect after 401;
check consent, policy and principal after 403; 404 means the bundle/van or shop
role is unavailable. For 409, read the current state, price and deadline; use
`browser_url` for payment. Use a smaller evidence file after 413. Check fields,
file or window after 422. Existing idempotency refusals remain failures.

Consulta primero `list_bought_bundle_vans` y usa `workflow.action` de cada van.
Abre el `browser_url` de la API para comprar, configurar la recogida inicial o
cambiar el método de pago. Nova no envía el PDF a la FMC. Envíalo por el canal
del taller. Registra el envío con `kind=pending`. Para registrar autorización,
usa `upload_capacity_evidence` con `kind=authorization`, `authorization_number`
y un archivo. Las fechas deben incluir la zona horaria. La API conserva los
permisos, los plazos y la aprobación del DSP. No se hace ningún pago con estas
herramientas. `requested` indica una solicitud nueva; `already_requested`, una
solicitud existente. Consulta las vans después de cada cambio. Si el resultado
no se conoce, consulta el registro antes de otro intento.

Browser links must use HTTPS, the configured Nova web origin, and the matching
`/bundle-offers/{ref}` path. Unsafe links are removed with a bilingual note.
Pickup times must be ISO 8601 strings with a UTC offset. The return date must
use `YYYY-MM-DD`; timestamps and epoch numbers are not accepted.
Los enlaces deben usar HTTPS, el origen web configurado de Nova y la ruta del
paquete. Los enlaces no seguros se quitan con una nota bilingüe. Las horas deben
ser cadenas ISO 8601 con zona horaria. La fecha de regreso usa `YYYY-MM-DD`.


## Sliding prices and recipient details

Bundle report reads preserve saved sliding-price bands and optional recipient
VINs exactly as returned by the API. Public links and revoked recipients do not
receive this disclosure. Payment setup and readiness keep their browser handoff.

Las lecturas de informes conservan los precios por tramos y los VIN que la API
permite ver al destinatario. Los enlaces públicos y los destinatarios revocados
no reciben estos datos. El método de pago y la disponibilidad se confirman en el navegador.

### Configured PM/AMR transport pricing

`sliding_transport_v5` preserves the frozen marginal percentages and the separate
`transport_fee` in USD. Defaults are 5% / 4% / 3% across the first $1,000, next
$1,000 and remainder, plus $50 per van. The van price includes transport; defect
allocations exclude it. All released work has zero charge. Saved older offers
keep their original pricing. The server calculates prices and enforces access.

## Reject an accepted CMR bundle

Use `nova bundle-shop reject REF --reason "Cannot repair"` or the
`reject_cmr_bundle` tool to reject all remaining work before any van is collected
or work starts. The operation is `capacity.bundles.reject.v1`; delegated
connections need fresh explicit consent. A vendor admin or service writer must
belong to the awarded shop. PM/AMR bundles are excluded. The API rejects the
whole action if any van has started. Signed acceptance and applicable saved fee
terms remain. After a confirmed write, read the vans; do not retry an uncertain
write. Coordinate release with the API and web implementation.
