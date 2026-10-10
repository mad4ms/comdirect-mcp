# Security Policy

This project handles banking credentials and financial data. Please treat security issues accordingly.

## Reporting a vulnerability

**Do not open a public issue.** Report vulnerabilities privately via
[GitHub private vulnerability reporting](https://github.com/mad4ms/comdirect-mcp/security/advisories/new)
or by email to m@ad4ms.de. You will get an answer within a few days.

Only the latest release is supported with fixes.

## Threat model

`comdirect-mcp` runs locally as a stdio process started by your MCP client. It talks to
`api.comdirect.de` only and has no network listener.

| Asset | Protection |
| --- | --- |
| Credentials (client id/secret, Zugangsnummer, PIN) | Read from the OS keychain, the environment or an explicitly named dotenv file (`COMDIRECT_ENV_FILE`); never logged or returned by tools |
| Session activation | Requires the push TAN to be approved in the photoTAN app (2FA). The TAN never passes through the language model |
| Money | The server uses read-only endpoints only. There is no tool that can place orders or transfer money |
| Access tokens | Kept in memory only; refreshed automatically. On `logout` and server shutdown the session is revoked at comdirect: it cannot be extended, the last access token expires within 10 minutes |
| Online banking access | Logins stop after three unconfirmed TAN challenges, before comdirect locks the access at five |

## Known risks when used with AI assistants

- **Data leaves your machine.** Account data, transactions and documents are sent to the model
  provider of your MCP client and may end up in logs or telemetry. Use a client with a local model to
  keep them on your machine (see [Use a local model](docs/how-to/use-a-local-model.md)).
- **Prompt injection.** Payment references, counterparty names and documents are third-party
  content. They can contain text that tries to manipulate the assistant. The server marks them as
  untrusted in its instructions, but no model is immune.
- **Personal data.** Counterparty IBANs and account numbers are masked by default, names only on request
  (`COMDIRECT_MCP_MASK_NAMES`); amounts and payment texts are not.
- **Supply chain.** Pin the version you run (for example `uvx comdirect-mcp@0.5.1`) instead of
  always pulling the latest release, and review changes before upgrading.

## Safeguards in this repository

- Secret scanning with gitleaks in CI and as a pre-commit hook.
- GitHub Actions pinned to commit SHAs, minimal workflow permissions, Dependabot updates.
- Releases via PyPI trusted publishing (OIDC), no long-lived tokens.
- Tests never touch the real API; `scripts/live_check.py` prints structure only, never values.
