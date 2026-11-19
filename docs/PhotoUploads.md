# Photo uploads

Requires the coordinated API release; do not release this client ahead of it.
These instructions describe the coordinated candidate release.

Upload custody photos with `vehicle_checkout` and the **vehicle ID**, such as
`VAN-0001`. Keep the returned `storage_key`, `content_type` and `size_bytes`.
Pass that metadata in the custody command's `--field 'photos=[{...}]'` list.
Use at most 12 photos per custody request. Custody requires a user connection;
service accounts cannot check out or check in a van. Inspection policy still
applies. Photos cannot replace a required submitted inspection.

To upload a local file during a custody command, repeat `--photo-file`:

```sh
nova vehicle check-out VAN-0001 --vendor-workshop-id 3 --mileage 100 --photo-file ./out.png
nova vehicle check-in VAN-0001 --mileage 100 --photo-file ./return.png
nova work-order complete WO-00001 --last-mileage 100 --odometer-photo-path ./odometer.png --work-photo-path ./repair.png
```

The named completion photo arguments accept local files or existing Nova keys.
Local photos must be regular files of at most 50 MiB. The image bytes must match
the file extension and any explicit content type. Final symbolic links are refused.
Enter mileage and select an applicable evidence mode before custody uploads.
`--field` values remain API payloads; they do not select local files. Upload with
`work_order` and the Work Order ID when supplying existing keys. For a new defect,
create the defect first, then use its returned ID:

```sh
nova upload photo ./damage.png --kind defect --parent-id FD-0001 --commit
```

The API accepts JPEG, PNG, WebP, HEIC and HEIF, up to 50 MiB (52,428,800 bytes)
per image, subject to its configured storage limit. Send raw bytes to the signed
URL without a Nova bearer credential or cookies. Upload URLs must use HTTPS
and the API origin, the matching Nova object-storage origin, or an exact
origin in `NOVA_UPLOAD_ORIGINS`. The official production and staging API
profiles each allow only their own object bucket by default. No environment
variable is needed for those buckets. For a custom deployment, set
`NOVA_UPLOAD_ORIGINS` to the exact storage origins approved by its operator
(a comma-separated list such as `https://storage.example,https://uploads.example`). Entries are
trimmed, scheme and host are converted to lowercase, and one trailing slash is
removed. Entries with paths, credentials, queries or fragments are refused.
HTTP is allowed only for the exact API origin when the API uses a permitted
loopback host (`localhost`, `127.0.0.1` or `[::1]`). Redirects are refused.
Do not change returned URLs or keys.

Delegated workflows need `uploads.presign.v1` plus `vehicles.check_out.v1`,
`vehicles.check_in.v1`, `work_orders.complete.v1`, or both `defects.create.v1`
and `defects.photos.create.v1`, as applicable. Request `nova:read nova:write`.
Existing grants need new consent. Role, tenant, station, assignment, shift,
location, approval and evidence checks remain at the API.

Read stable API error codes and structured details. Keep
`wo_technician_evidence_required`, `capacity_transport_required`, and
`mileage_confirmation_required`. Review `submitted_mileage`, `expected_floor`
and `floor_sources` before explicitly supplying `confirmed_mileage_floor`.
Never invent a confirmation or retry an unknown mutation outcome.

## Attach a photo to an existing defect

Use the existing defect ID. Do not create the defect again. Sign in with
`uploads.presign.v1` and `defects.photos.create.v1`, and request
`nova:read nova:write`. Then run:

```sh
nova upload photo ./damage.png --kind defect --parent-id FD-0001 --commit
```

Check that the result has `committed: true`. Use the defect photo list or open
the same defect in the app to check the attachment. A storage key alone does
not mean that the photo is attached. Read the record before another attempt
if the outcome is unknown.

## Español

Carga fotos de custodia con `vehicle_checkout` y el ID del van. Usa un máximo
de 12 fotos. Repite `--photo-file` para cargar archivos locales. Los argumentos
`--odometer-photo-path` y `--work-photo-path` aceptan archivos o claves de Nova.
Para un defecto nuevo, usa el ID devuelto y `--kind defect --commit`.
La custodia requiere una conexión de usuario. Una foto no sustituye una
inspección enviada obligatoria. Solicita permiso nuevo para las operaciones
indicadas. Revisa el millaje antes de confirmar el mínimo. No repitas una
operación con resultado desconocido.

## Customer stdio MCP

Use the existing `upload_photo`, `check_out_vehicle`, `check_in_vehicle` and
`complete_work_order` tools. The custody `photo_file` list and named completion
file arguments require the operator's `--file-root`. Inputs are snapshotted
inside that folder without following symbolic links. Storage keys do not need
a file root. This package has no machine credential mode and no base64 upload
tool; it retains the existing local-file workflow.

En MCP, la lista `photo_file` y los archivos de fotos de finalización requieren
la carpeta indicada con `--file-root`. Las claves guardadas no requieren esa
carpeta. Este paquete conserva la carga de archivos locales.

En producción y staging, cada perfil de API de Nova permite su propio depósito
de fotos sin configurar `NOVA_UPLOAD_ORIGINS`. Para una instalación diferente,
configura los orígenes exactos autorizados por su operador. Para adjuntar una
foto a un defecto existente, usa su ID con `--kind defect --commit` y los
permisos `uploads.presign.v1` y `defects.photos.create.v1`. Comprueba que el
resultado tenga `committed: true` y consulta las fotos del defecto. No crees
el defecto de nuevo. Si el resultado es desconocido, consulta el registro antes
de otro intento.
