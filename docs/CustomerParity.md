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
| Shop work | Read and create work orders; assign, schedule, accept, decline, release, cancel or complete eligible work; read activity and notes; manage supported repair-line fields. |
| Repair requests | Read requests and repair-provider choices; preview provider choices; cancel eligible requests; dismiss a rental-routing reminder. |
| Cortex | Review a source file with corrections, preview reviewed fleet rows, and apply permitted imports. |
| Body repair | Read permitted orders, PAVE reports/comparisons and images; download quote, scope, invoice/receipt and documentation files. |
| Inspections | Read permitted inspection lists and details. Use the browser for inspection capture and submission. |
| Notifications and events | Read and manage supported notifications/preferences; consume workshop events with durable local acknowledgment. |
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
