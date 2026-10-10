# Configuration

## Command line

| Command | Description |
| --- | --- |
| `comdirect-mcp` | Runs the MCP server over stdio (what MCP clients start) |
| `comdirect-mcp serve` | Same, explicit |
| `comdirect-mcp configure` | Stores the credentials in the OS keychain (prompts; Enter keeps a stored value) |
| `comdirect-mcp configure --delete` | Removes the stored credentials from the keychain |
| `comdirect-mcp --version` | Prints the version |
| `python -m comdirect_mcp [...]` | Same as `comdirect-mcp [...]` |

Run without installing: `uvx comdirect-mcp@0.4.0 [...]`.

## Credentials

| Variable / keychain entry | Description |
| --- | --- |
| `COMDIRECT_CLIENT_ID` | API client id (developer access, starts with `User_`) |
| `COMDIRECT_CLIENT_SECRET` | API client secret |
| `COMDIRECT_USERNAME` | Zugangsnummer |
| `COMDIRECT_PASSWORD` | PIN |

Lookup order per value: environment variable → OS keychain (service `comdirect-mcp`, entry = variable name) →
`.env` in the working directory. Details: [Manage credentials](../how-to/manage-credentials.md).

## Server options

Environment variables, read when the server starts:

| Variable | Default | Description |
| --- | --- | --- |
| `COMDIRECT_MCP_PUSH_TAN_WAIT` | `30` | Seconds to wait for the push TAN approval when the client cannot show a confirmation dialog |
| `COMDIRECT_MCP_UNMASK_IBANS` | unset | `true`, `1` or `yes` returns counterparty IBANs unmasked; otherwise they are masked (`DE**...3000`) |
| `COMDIRECT_MCP_MAX_DOCUMENT_BYTES` | `10485760` | Size limit for `download_document` in bytes |

## Protocol

| Property | Value |
| --- | --- |
| MCP specification | 2026-07-28; older revisions (2025-11-25 and earlier) via version negotiation |
| Transport | stdio |
| Server name / title | `comdirect` / `comdirect` |
| Capabilities used | tools (with annotations and output schemas), elicitation (form) for the login |
| Registry name | `io.github.mad4ms/comdirect-mcp` ([server.json](../../server.json)) |
