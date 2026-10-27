# Download Body repair PDFs

Use explicit browser consent for `body_repair.documents.quote.read.v1` and
`body_repair.documents.scope.read.v1`. Default login permissions do not grow.

```sh
nova auth login --operations 'body_repair.documents.quote.read.v1 body_repair.documents.scope.read.v1'
nova body-repair quote BRR-1 --quote BRQ-2 --out quote.pdf
nova body-repair scope BRR-1 --out scope.pdf
```

Use a request ID or order token from an accessible order. Optional quote references
accept numeric or BRQ IDs, not opaque tokens. The server chooses the permitted
customer/shop document. For fleet readers, the quote must belong to the order.
Shop readers always receive their own quote; the API ignores their quote selector.
Downloads have a 10 MiB cap.
Choose a new output path; an existing file is not overwritten. Output is metadata,
not PDF bytes. Local stdio MCP exposes `download_body_repair_quote` and
`download_body_repair_scope` with request_ref and optional quote for the quote
tool. No out/path input is accepted; these tools write no files. The result
contains an embedded application/pdf binary resource plus size, SHA-256 and
content-addressed URN metadata. Original bytes are base64 encoded, not rendered
as JSON text or returned through a file:// path. Local embedding has a 1 MiB
raw byte product limit; larger documents require the CLI --out download. This
limit is not a universal MCP host guarantee. The HTTP MCP service uses its own file limits.


## Invoice or receipt

Request explicit browser consent for `body_repair.documents.invoice.read.v1`.
Default login permissions do not grow. Then download the available document:

```sh
nova auth login --operations 'body_repair.documents.invoice.read.v1'
nova body-repair invoice BRR-1 --out invoice.pdf
```

The same command returns an invoice or receipt according to the server's payment
state; the chosen output name does not select the document type. Local MCP tool
`download_body_repair_invoice` accepts only request_ref, with no quote or out
argument. It returns the existing embedded PDF resource and descriptor without
writing a local file. The existing 10 MiB CLI / 1 MiB local embedding caps apply.
The server checks request ownership, billing/payment availability and the shop's
own invoice projection. No document, a foreign order or missing consent fails
without creating a download file. This client does not bill or pay an order.
