# comdirect-mcp

<!-- mcp-name: io.github.mad4ms/comdirect-mcp -->

[![PyPI](https://img.shields.io/pypi/v/comdirect-mcp.svg)](https://pypi.org/project/comdirect-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/comdirect-mcp.svg)](https://pypi.org/project/comdirect-mcp/)
[![Tests](https://github.com/mad4ms/comdirect-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/mad4ms/comdirect-mcp/actions/workflows/tests.yml)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-blue)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Read-only [Model Context Protocol](https://modelcontextprotocol.io) server and typed Python client for the
[comdirect REST API](https://www.comdirect.de/cms/kontakt-zugaenge-api.html).**

Let Claude, GitHub Copilot or any other MCP client look at your accounts, transactions, securities depot and
postbox documents. The login is confirmed with your photoTAN app, and there is no tool that can move money.

> [!WARNING]
> This is an unofficial project, not affiliated with comdirect. It handles your banking credentials and sends
> your financial data to the AI model you connect it to. Read the warning below and [SECURITY.md](SECURITY.md).

## Warnung (in Deutsch weil Comdirect)

Leute es geht hier um euer Geld. Nutzt diese Bibliothek nur, wenn ihr den Code versteht und euch den Risiken bewusst seid.

Ich bin auch nicht perfekt, aber übernehme keine Haftung für Schäden, die durch die Nutzung dieser Software entstehen. Falls Euch was auffällt, gern PRs oder Issues.

Die API und damit das Repo hier nutzen aktuell nur lesende Endpunkte, aber Fehler können immer passieren. Comdirect kann die API ändern, Dependencies können im Zweifel auch Mist bauen ([Supply-Chain Attacks](https://docs.github.com/de/code-security/concepts/supply-chain-security/about-supply-chain-security)) und 2FA hilft zwar, ist aber kein Freifahrtschein.

Bitte:
- Nutzt das nur lokal auf eurem eigenen Rechner.
- Teilt eure Zugangsdaten mit niemandem.
- Packt Secrets in `.env` und committet die Datei nie.
- Nutzt die [Pre-Commit Hooks](docs/how-to/develop.md#pre-commit-hooks) um Secrets zu scannen. Gute Zeit bissel Devops-Kram zu lernen.
- Spielt Updates nicht blind ein (Lockfile/Pinning hilft) und schaut bei Änderungen kurz drüber.

**MCP-Server**: Wenn ihr den Server an einen nicht-lokalen AI-Client hängt, **gehen deine Daten raus**. Je nach Client/Setup können Kontodaten/Transaktionen in Logs/Telemetry landen oder durch Prompt-Injection aus Dokumenten/Verwendungszwecken in komische Richtungen gehen ([MCP Horror Stories: The GitHub Prompt Injection Data Heist](https://www.docker.com/blog/mcp-horror-stories-github-prompt-injection/)). Nutzt MCP nur, wenn ihr der Umgebung wirklich vertraut, und gebt nur die Daten frei, die ihr dafür braucht.

Da der gemeine r/finanzen User eh schon seine Kontoauszüge in ChatGPT kopiert, könnt ihr damit machen, was ihr wollt, **auf eure eigene Verantwortung**!

Idealerweise ohne unnötige personenbezogene Daten. (Hauptsache, ihr lasst 'nen Stern da.)

## Privacy: prefer a local model

The server runs on your machine, but **every tool result is sent to the language model behind your MCP client**.
With cloud assistants (Claude, GitHub Copilot, ChatGPT, ...) your balances, transactions and documents leave your
computer and are processed under that provider's data policy.

- **Most private:** use an MCP client with a **local model**, e.g. [LM Studio](https://lmstudio.ai) (supports MCP
  servers directly) or [Ollama](https://ollama.com) with the [ollmcp](https://github.com/jonigl/mcp-client-for-ollama)
  client. Then nothing leaves your machine
  except the requests to comdirect. Pick a model with good tool-calling support.
- **With a cloud assistant:** check its data retention and training settings, use an account where your data is
  not used for training, and ask only what you need.

Details: [Privacy and security](docs/explanation/privacy-and-security.md) ·
[Use a local model](docs/how-to/use-a-local-model.md)

## Features

- **MCP specification 2026-07-28** on the official MCP Python SDK v2, with fallback for older clients
- **Push TAN login via elicitation**: your client asks you to approve the login in the photoTAN app; the TAN never reaches the model
- **Credentials in the OS keychain**: `comdirect-mcp configure` stores them once, client configs contain no secrets
- **No tool can move money**: only read endpoints, truthful tool annotations, structured output with JSON schemas
- **Protects your access**: stops logging in before comdirect's lock after five unconfirmed TAN challenges, and
  revokes the session at comdirect on logout and shutdown so it cannot be extended
- **Built for agents**: compact results without empty fields, one `counterparty` instead of SEPA roles, cleaned-up
  payment texts, server-side summaries for cash flow questions
- **Privacy defaults**: IBANs and account numbers masked, optional name pseudonyms, documents size-limited,
  untrusted-content hint for the model
- **Automatic token refresh** and explicit session handling
- **Typed Python client** (`py.typed`) for scripts and notebooks, independent of MCP
- Listed in the [MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.mad4ms/comdirect-mcp`

### Tools

| Tool | Description |
| --- | --- |
| `login` | Starts a session; asks you to approve the push TAN |
| `logout` | Ends the session and revokes it at comdirect (no further refresh) |
| `list_accounts` | Accounts with type (Girokonto, Tagesgeld, ...) and balances |
| `get_wealth_overview` | All product balances with bank-supplied EUR totals, including loans and savings |
| `list_depot_transactions` | Securities purchases, sales and transfers with filters and continuation |
| `get_instrument` | Security metadata; optional fund fees/ratings and derivative details |
| `list_transactions` | Transactions with date, amount, counterparty and cleaned-up purpose; compact by default |
| `summarize_transactions` | Cash flow and spending per month, counterparty or type, computed on the server |
| `list_cards` | Card balances (Visa); the API has no card transactions |
| `list_depots` | Securities accounts |
| `get_depot_positions` | Positions (name, ISIN, WKN, values, P&L) and depot balance |
| `list_documents` | Postbox documents (statements, order confirmations, tax documents) |
| `download_document` | A document as embedded resource (comdirect marks it as read) |
| `get_account_balance` | Balance and masked static data for one account |
| `get_depot_position` | One securities position, with optional details |
| `summarize_portfolio` | Largest positions and allocation percentages per currency |
| `list_orders` / `get_order` | Read the order book and individual orders; never place or change orders |
| `get_order_dimensions` | Available trading venues, currencies and order types |
| `get_document_cover` | Bounded plain text from the document pre-page |
| `extract_document_text` | Bounded PDF text with page continuation; downloading marks it as read |

Arguments and results: [Tools reference](docs/reference/tools.md).

## Quickstart

New to this? Follow the [Getting started tutorial](docs/tutorials/getting-started.md).

### 1. Prerequisites

- [uv](https://docs.astral.sh/uv/) (provides `uvx`)
- comdirect API access: in the online banking under **Verwaltung → Entwicklerzugang** you get a Client ID and
  Client Secret ([step by step](docs/how-to/get-comdirect-api-access.md))
- **photoTAN Push** as your default TAN method

### 2. Store your credentials in the OS keychain

```bash
uvx comdirect-mcp@0.5.1 configure
```

Prompts for Client ID, Client Secret, Zugangsnummer and PIN and stores them in the macOS Keychain, Windows
Credential Manager or Linux Secret Service. Other options (VS Code inputs, environment, `.env`):
[Manage credentials](docs/how-to/manage-credentials.md).

### 3. Add the server to your MCP client

**Claude Desktop** (*Settings → Developer → Edit Config*) and **LM Studio** (*Program → Install → Edit mcp.json*):

```json
{
  "mcpServers": {
    "comdirect": {
      "command": "uvx",
      "args": ["comdirect-mcp@0.5.1"]
    }
  }
}
```

**Claude Code**

```bash
claude mcp add --transport stdio --scope user comdirect -- uvx comdirect-mcp@0.5.1
```

**VS Code** (*MCP: Open User Configuration*)

```json
{
  "servers": {
    "comdirect": {
      "type": "stdio",
      "command": "uvx",
      "args": ["comdirect-mcp@0.5.1"]
    }
  }
}
```

**Ollama** (via [ollmcp](https://github.com/jonigl/mcp-client-for-ollama))

```bash
uvx ollmcp mcp add --scope user comdirect -- uvx comdirect-mcp@0.5.1
uvx ollmcp -m <model>
```

Pinning the version (`@0.5.1`) means updates only happen when you decide. More clients:
[Configure MCP clients](docs/how-to/configure-mcp-clients.md).

### 4. Ask

> Wie haben sich meine Ausgaben im letzten Monat entwickelt, und welche Depotposition läuft am schlechtesten?

The assistant calls `login`, your phone receives the push TAN, you approve it and confirm the dialog in
your client. Then the assistant can use the other tools. Problems: [Troubleshoot](docs/how-to/troubleshoot.md).

## Python library

The same client is available for your own scripts:

```python
from comdirect_mcp import ComdirectClient
from comdirect_mcp.utils import default_push_tan_callback

client = ComdirectClient(
    {"client_id": "...", "client_secret": "...", "username": "...", "password": "..."},
    {"push_tan_cb": default_push_tan_callback},
)
client.login()  # approve the push TAN, then press Enter

for account in client.list_accounts():
    print(account.id, account.balance, account.currency)
```

See [Use the Python library](docs/how-to/use-the-python-library.md), the [Python API reference](docs/reference/python-api.md)
and the [examples](examples/).

## Documentation

The [documentation](docs/README.md) is organized as tutorial, how-to guides, reference and explanation:

| | |
| --- | --- |
| **Tutorial** | [Getting started](docs/tutorials/getting-started.md) |
| **How-to** | [API access](docs/how-to/get-comdirect-api-access.md) · [Credentials](docs/how-to/manage-credentials.md) · [MCP clients](docs/how-to/configure-mcp-clients.md) · [Local model](docs/how-to/use-a-local-model.md) · [Troubleshoot](docs/how-to/troubleshoot.md) · [Python library](docs/how-to/use-the-python-library.md) · [Develop](docs/how-to/develop.md) |
| **Reference** | [Tools](docs/reference/tools.md) · [Configuration](docs/reference/configuration.md) · [Python API](docs/reference/python-api.md) |
| **Explanation** | [Login and sessions](docs/explanation/login-and-sessions.md) · [Privacy and security](docs/explanation/privacy-and-security.md) · [Design](docs/explanation/design.md) |

[SECURITY.md](SECURITY.md) describes the threat model and how to report vulnerabilities, [CHANGELOG.md](CHANGELOG.md)
lists the changes per release.

## Contributing

Issues and pull requests are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). AI coding agents find their instructions in [AGENTS.md](AGENTS.md).

## Disclaimer

This project is not affiliated with, maintained, or endorsed by comdirect bank AG. Use it at your own risk.
There is no warranty and no liability for any financial losses or damages resulting from its use.

The software runs locally and does not send your credentials anywhere except to comdirect. Your MCP client
and its model provider receive the data the tools return.

## License

[MIT](LICENSE)
