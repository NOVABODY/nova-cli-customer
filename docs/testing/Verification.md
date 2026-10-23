# Public/private split verification

October 23, 2026. The public and private wheels were installed in the same fresh
Python environment. Public `nova`, `nova-cli` and `nova-mcp` resolve to
`nova_cli_public`; private operator/adapter commands resolve to `nova_cli`.
No script names or import packages collide. Public wheel contents contain only
the public package and distribution metadata. No private history or documents
were copied into this repository.

- Public suite: 75 tests passed, including real MCP SDK stdio.
- Internal suite: 422 passed, one skipped, both from source and installed wheel.
- Ruff and both distribution builds passed.
- Real macOS Keychain: same profile name in both packages retained separate
  credentials. Public deletion preserved the private entry. Separate profile
  files and selection were verified. All synthetic credentials were removed.
- Installed public CLI browser journey: S256 consent, list/detail reads, foreign
  record denial, refresh, local logout and server disconnect passed.
- Installed public MCP journey: typed discovery and reads, CLI/MCP shared refresh,
  and browser disconnect denying an already-running MCP session passed.
- Audit: seven attributed successful reads, three connections, all revoked;
  foreign reads produced no success audit.

The browser journeys used the real OS Keychain, a local HTTPS proxy, PostgreSQL,
Redis and API source `c91b3261a9532defb8e7e4875e1f4dcd63549652`, with synthetic
accounts and fleet records. `source-sha256.json` identifies the public source.
Private runtime credentials, TLS/signing keys and account setup are excluded.
These checks do not certify a hosted assistant or deploy/activate customer access.

A profile-removal regression first failed because nested refresh locks blocked
the command. The final command holds one lock while deleting the public credential
and profile; the regression verifies the internal credential remains untouched.
