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
not PDF bytes. These commands have no local or hosted MCP adapter in this slice.
