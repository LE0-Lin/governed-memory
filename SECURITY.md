# Security and trust boundaries

Governed Memory is an experimental developer tool for trusted local hosts and
controlled self-hosting. It is not an authenticated public HTTP service, a
general prompt-injection defense or a production security guarantee.

The host, database credentials and operator credential are trusted. Bind only
a separate agent credential to MCP. Proposed/source/model text is data and
cannot grant approval or change caller identity. OpenFGA intersects local grants;
OPA governs operator decisions. Do not expose development Compose credentials
or ports to an untrusted network.

Withdrawal hides evidence through normal retrieval and invalidates bound
derivations; it does not physically erase audit rows or backups. Keep backups
protected like the original ledger. See [design](docs/design.md) and
[recovery](docs/deployment.md) for the exact supported behavior.

## Reporting a sensitive finding

If GitHub offers **Report a vulnerability** on this repository's Security tab,
use that private channel. Otherwise open an issue requesting a private reporting
channel without the exploit details, real credentials, database dumps or private
source text. Do not paste secrets into a public issue.

Include the release/commit, relevant configuration with secrets removed,
prerequisites, expected/observed behavior and a synthetic reproduction where
possible. No response-time SLA is promised. Current maintenance targets the
latest release; use its tag and backup instructions when upgrading.
