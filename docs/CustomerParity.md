# Customer workflow coverage

This release supplies named customer commands and local MCP tools. Run
`nova capabilities --json` for current arguments, effects and permissions.
The [command reference](Commands.md) lists the commands in this release.
Availability in discovery does not grant account access.

| Workflow | Available actions |
| --- | --- |
| Fleet | List and read vans, decode VINs, create and update permitted van data, read fleet/rental companies, set a van's company. |
| Fleet updates | Read queues and resolve permitted fleet issues. |
| Reports | Read aggregate reports, repair ratings and problem queues, inspector/driver quality, scheduled fleet work, and daily work summaries; mark a daily summary as read. |
| Notes and custody | Read and manage permitted van notes; read checkout history; check vans in or out with required evidence. |
| Defects | Read catalog and defects, report and route a defect, read reviews, approve/reject a review, set cost, read photo references, and transfer permitted evidence. |
| CMR/CNMR quotes | List, read, submit, withdraw, dismiss a line, and approve or reject a line with the current amount. |
| Shop work | Read and create work orders; assign, schedule, accept, decline, release, cancel or complete eligible work; read activity and notes; manage supported repair-line fields. |
| Repair requests | Read requests and repair-provider choices; preview provider choices; cancel eligible requests; dismiss a rental-routing reminder. |
| Cortex | Review a source file with corrections, preview reviewed fleet rows, and apply permitted imports. |
| Body repair | List eligible leads and shop quotes; confirm reviewed scope, submit and withdraw a quote; read permitted orders, PAVE reports/comparisons and images; download quote, scope, invoice/receipt and documentation files. |
| Body repair | Select quotes without referral credit, confirm/accept pickup with the read version; read permitted orders, PAVE reports/comparisons and images; download quote, scope, invoice/receipt and documentation files. |
| Inspections | Read permitted inspection lists and details. Use the browser for inspection capture and submission. |
| Notifications and events | Read and manage supported notifications/preferences; consume workshop events with durable local acknowledgment. |
| Tire vendor setup | Read Station choices, add an eligible vendor, submit contacts, and handle requests as site admin. |
| Account | Manage local profiles, browser sign-in, credential status/refresh/logout, identity reads and health checks. |

## Permission and state limits

Each action keeps the server's role, organization, record and workflow-state
checks. A command can be listed but unavailable to your account. New permissions
need a new browser consent. Changes require write consent. Version conflicts and
missing evidence must be resolved before another attempt.

## Browser handoffs

Use the browser for sign-in, account security, required agreements, camera
capture, and payment authorization. A link starts a handoff; it does not complete
the business action. Broader web workflows without a listed command remain
unavailable through this client. Full web parity is not claimed.

File limits and transfers are described in the main guide and
[Body documents](BodyDocuments.md). Local MCP paths exist on the machine running
the CLI; they are not remote download links.

DSP quote selection and pickup use the [named decisions](../README.md#dsp-body-repair-decisions). Sign-off and payment remain browser handoffs. The shop records physical return; no DSP return command exists.

## CMR and CNMR quotes

CMR and CNMR are Nova repair-category terms. Use `cmr-quote list`, `get`,
`submit`, `withdraw`, `dismiss`, or `decide`. Amounts are integer cents.
Submit the quote as JSON with `--data`. Use `--expected-amount-cents` for a
line decision. The API checks the role, organization, amount, and quote state.

```sh
nova cmr-quote list --status all --defect-ids 7 --defect-ids 8
nova cmr-quote submit --data '{"vehicle_id":"VAN-2","lines":[{"defect_id":"FD-7","amount_cents":1250}]}' --idempotency-key 12345678-1234-4234-8234-123456789abc
nova cmr-quote decide 9 --defect-id FD-7 --decision approved --expected-amount-cents 1250
```

Each change sends one idempotency key and does not retry automatically. After
an unknown outcome, read the quote. Use the same key and input for the same
request; a new key can create another quote. Complete payment setup in Nova.
Listing a command or tool does not grant permission.

Cotizaciones CMR y CNMR: usa importes en centavos enteros. La API comprueba el
rol, la organización, el importe y el estado. Tras un resultado desconocido,
consulta la cotización. Reutiliza la misma clave y los mismos datos para la
misma solicitud. Termina la configuración del pago en Nova.

Quote reads require `cmr_quotes.list.v1` or `cmr_quotes.get.v1`. Changes require
write consent and the matching `cmr_quotes.submit.v1`, `withdraw.v1`, `dismiss.v1`,
or `decide.v1` operation. Add these permissions through browser consent.

Fleet repair valuation is available to site administrators through
`report fleet-repair-value` and `get_fleet_repair_value_report`. It uses the
existing Vehicle availability API with explicit delegated read consent; the API
rejects DSP/vendor principals and revoked connections. Values include fleet/DSP
subtotals and missing-estimate counts, with grounded vans included by default.
