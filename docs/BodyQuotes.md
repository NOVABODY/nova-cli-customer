# Submit a Body repair quote

Read the request detail and current scope revision. Show the user the current
scope changes and get their go-ahead before `confirm_body_repair_scope`.
Confirmation is a separate action with `confirm:true`; it records that an agent
reviewed the scope. Submission never confirms scope.

Read eligible work with `list_body_repair_leads` and your shop's quotes with
`list_body_repair_quotes`. Reuse `list_body_repair_requests` and
`get_body_repair_request` for the queue and current scope. Submit with
`submit_body_repair_quote`; correct an active offer through
`withdraw_body_repair_quote` and a new submission before selection.

Use USD cents, rates in cents per hour, and labor time in hours. Inputs are closed
and strict, including line items and issue answers. Use the current
`based_on_scope_revision` and returned totals: the server reprices structured
lines. Guided lines must cover the scope. Leads omit duration, repair dates,
pickup window and `grade_days`; fleet-picks leads require guided scope.
Omit `grade_days` for all submissions. The API checks dates, pricing, scope,
audience, shop role and request state.

Request fresh consent for `body_repair.repair_leads.list.v1`,
`body_repair.quotes.list.v1`, `body_repair.scope.confirm.v1`,
`body_repair.quotes.submit.v1`, and `body_repair.quotes.withdraw.v1`.
The three writes require full write consent. Existing grants do not expand.
Machine writes also require a bound acting user; an unbound account receives 403.
Reads keep their existing binding rules.

400 means invalid business input; 401 means invalid, revoked or expired identity;
403 means missing consent, scope, policy, shop authority or machine user binding;
404 means absent or hidden records; 409 means changed scope or state; 422 means
invalid schema or scope coverage; 429 means the request limit was reached.
After 409, read the current request and quotes and review changes before another
attempt. No write is retried automatically. After an unknown outcome, read first.
Selection, selected-quote revisions, payment and payouts remain separate actions.

Muestra los cambios actuales del alcance al usuario y obtén su aprobación antes
de confirmar la revisión. Envía la cotización en una acción separada. Usa centavos
de USD, tarifas en centavos por hora y tiempo en horas. Consulta el estado actual
después de un conflicto o resultado desconocido antes de otro intento. Las
escrituras de máquina requieren un usuario vinculado; la API conserva los
permisos y el alcance del taller.

Commands: `nova body-repair repair-leads`, `quotes REQUEST`,
`confirm-scope REQUEST --based-on-scope-revision N --confirm`,
`submit-quote REQUEST --data JSON`, and `withdraw-quote REQUEST QUOTE`.
`--data` is the quote body with its revision, lines and issue answers.
