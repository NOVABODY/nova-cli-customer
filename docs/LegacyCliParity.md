# Command compatibility

Use `nova capabilities --json` for the commands, arguments, tool names, effects,
scopes and operation permissions supplied by this release. Discovery is offline;
the server checks whether your account can run each operation.

The command aliases `nova-cli`, `wo`, `work-orders`, `defects` and `notifications`
remain available. Use the primary command names shown by `nova --help` in new
scripts. The `defect list --status` filter applies to the returned page.

A read grant does not permit changes. List and detail permissions are separate.
Request the full operation list when you sign in again; an existing connection
does not gain permissions when the client is upgraded.

File commands keep their documented output and cursor behavior. They do not
overwrite an existing download. A failed output write does not advance an export
cursor. Workshop events use explicit local acknowledgment. Unknown change
outcomes require a read before another attempt; changes are not retried
automatically.

Browser sign-in, account security, camera capture and payment authorization use
their supported browser flows. This client does not collect passwords or accept
service keys. It does not provide every action in the Nova web application. See
[workflow coverage](CustomerParity.md) and the [command reference](Commands.md).
