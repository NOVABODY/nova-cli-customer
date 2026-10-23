# Public Nova CLI

This repository contains only the public customer client. Keep operator commands,
password/service authentication, internal documents, private credentials and
backend-local tooling out of this repository and its distribution.

Reuse the existing browser/S256 login, transport and typed fleet behavior. Public
profiles, keyring service and locks use `nova-cli-public`; never fall back to the
private client's `nova-cli` storage. The API owns authorization. Do not expand
available operations without a corresponding implemented API contract and tests.

Run Ruff, pytest and a wheel build before pushing. Verify installed entry points
and artifact contents when packaging changes. Keep tests synthetic; never commit
credentials or customer data. Public source does not authorize deployments or
package-registry publication.
