# Documentation

The documentation follows the [Diátaxis](https://diataxis.fr) structure: a tutorial to learn, how-to guides for
tasks, reference for facts, and explanations for background.

## Tutorial

- [Getting started](tutorials/getting-started.md): from comdirect API access to your first question to an assistant

## How-to guides

Using the server:

- [Get comdirect API access](how-to/get-comdirect-api-access.md)
- [Manage credentials](how-to/manage-credentials.md): OS keychain, VS Code inputs, environment, `.env`
- [Configure MCP clients](how-to/configure-mcp-clients.md): Claude Desktop, Claude Code, VS Code, LM Studio, others
- [Use a local model](how-to/use-a-local-model.md)
- [Troubleshoot](how-to/troubleshoot.md)
- [Use the Python library](how-to/use-the-python-library.md)

Working on the project:

- [Develop](how-to/develop.md): setup, checks, live check against the real API
- [Release a new version](how-to/release.md)
- [Regenerate the OpenAPI client](how-to/regenerate-openapi-client.md)

## Reference

- [Tools](reference/tools.md): arguments, results and annotations of every MCP tool
- [Configuration](reference/configuration.md): commands, credentials, environment variables, protocol
- [Python API](reference/python-api.md): `ComdirectClient`, models, exceptions

## Explanation

- [Login and sessions](explanation/login-and-sessions.md): 2FA, elicitation, tokens, why only push TAN
- [Privacy and security](explanation/privacy-and-security.md): where your data goes, prompt injection
- [Design decisions](explanation/design.md): read-only, layers, the vendored client, live checks

Also: [SECURITY.md](../SECURITY.md) · [CONTRIBUTING.md](../CONTRIBUTING.md) · [CHANGELOG.md](../CHANGELOG.md) ·
[AGENTS.md](../AGENTS.md)
