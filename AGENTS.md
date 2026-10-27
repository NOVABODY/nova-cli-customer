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
