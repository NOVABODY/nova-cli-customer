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
customer/shop document and checks quote membership. Downloads have a 10 MiB cap.
Choose a new output path; an existing file is not overwritten. Output is metadata,
not PDF bytes. Local stdio MCP exposes `download_body_repair_quote` and
`download_body_repair_scope` with request_ref and optional quote for the quote
tool. No out/path input is accepted; these tools write no files. The result
contains an embedded application/pdf binary resource plus size, SHA-256 and
content-addressed URN metadata. Original bytes are base64 encoded, not rendered
as JSON text or returned through a file:// path. Local embedding has a 1 MiB
raw byte product limit; larger documents require the CLI --out download. This
limit is not a universal MCP host guarantee. Hosted MCP is not implemented here.
