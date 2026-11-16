# Customer Nova CLI

Keep this repository private until the owner explicitly authorizes publication.

This repository contains only the public customer client. Keep unrelated commands,
password/service authentication, maintainer records, credentials and
deployment tooling out of this repository and its distribution.

Reuse the existing browser/S256 login, transport and typed fleet behavior. Public
profiles, keyring service and locks use `nova-cli-public`; never fall back to another client's storage. The API owns authorization. Do not expand
available operations without a corresponding implemented API contract and tests.

Run Ruff, pytest and a wheel build before pushing. Verify installed entry points
and artifact contents when packaging changes. Keep tests synthetic; never commit
credentials or customer data. Public source does not authorize deployments or
package-registry publication.

Every CLI and local MCP tool must work through customer delegated authentication.
Align tool registration, canonical API operation names, request signatures,
discovery, scopes and consent with the native client allowance and hosted cohorts
in nova-john-app. Include the matching infrastructure PR when adding operations.
Validate the complete operation catalog, and bind transport mocks to the real
ApiClient.request signature. Internal service-account success is not customer
authorization evidence. Distinguish source tests, released packages, deployed
registrations and live workflow verification; do not claim availability before
the applicable release and authorization checks pass.
