# comdirect-mcp

<!-- mcp-name: io.github.mad4ms/comdirect-mcp -->

[![PyPI](https://img.shields.io/pypi/v/comdirect-mcp?cacheSeconds=3600)](https://pypi.org/project/comdirect-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/comdirect-mcp?cacheSeconds=3600)](https://pypi.org/project/comdirect-mcp/)
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

## Warnung (auf Deutsch, weil comdirect)

Leute, hier geht es um euer Geld. Nutzt diese Bibliothek nur, wenn ihr den Code versteht und die Risiken kennt.

Die Software steht unter der [MIT-Lizenz](LICENSE): Jeder darf damit machen, was er/sie will (auch ihr, comdirect 👀), aber ohne jede Gewährleistung. Ich übernehme keine Haftung für Schäden durch ihre Nutzung. Wenn euch etwas auffällt: PRs und Issues sind willkommen.

Transparenz: Ein Teil des Codes stammt von Opus 5.5 und gpt-6.1-sol, ich habe reviewed, getestet und weise genickt. Genau deshalb steht oben, dass ihr den Code verstehen solltet. Den MCP-Server selbst habe ich lokal mit einem Modell über Ollama getestet, ganz ohne Cloud.

Das Repo nutzt aktuell nur lesende Endpunkte der API, aber Fehler passieren trotzdem. comdirect kann die API jederzeit ändern, Dependencies können kompromittiert werden ([Supply-Chain-Angriffe](https://docs.github.com/de/code-security/concepts/supply-chain-security/about-supply-chain-security)), und 2FA hilft zwar, ist aber nun wirklich kein Freifahrtschein.

Deshalb bitte:

- Nutzt das Ganze nur lokal auf eurem eigenen Rechner.
- Gebt eure Zugangsdaten niemandem weiter.
- Legt eure Zugangsdaten im OS-Schlüsselbund ab (`comdirect-mcp configure`). Falls ihr doch eine `.env` nutzt: Dort steht das Passwort im Klartext, also committet sie niemals.
- Nutzt bei Clones/Forks die [Pre-Commit-Hooks](docs/how-to/develop.md#pre-commit-hooks), um nach Secrets zu scannen. 
- Spielt Updates nicht blind ein (Lockfile und Pinning helfen) und schaut euch Änderungen kurz an.

**MCP-Server**: Sobald ihr den Server an einen AI-Client hängt, der nicht lokal läuft, **verlassen eure Daten euren Rechner**. Je nach Client und Setup können Kontodaten und Umsätze in Logs/Telemetrie im Ausland landen. Außerdem können (wenn auch unwahrscheinlich) Dokumente oder Verwendungszwecke Prompt-Injections enthalten, die das Modell in komische Richtungen lenken ([MCP Horror Stories: The GitHub Prompt Injection Data Heist](https://www.docker.com/blog/mcp-horror-stories-github-prompt-injection/)). Nutzt deshalb den MCP nur in Umgebungen, denen ihr wirklich vertraut, und gebt nur die Daten frei, die ihr tatsächlich braucht.

Da der gemeine r/finanzen - User seine Kontoauszüge eh schon in ChatGPT kopiert: Macht damit, was ihr wollt, aber **auf eigene Verantwortung**! Aber endlich könnt ihr eurem Date per Claude erstelltes Chart vorrechnen, was der erste Beziehungsmonat gegenüber dem letzten Singlemonat gekostet hat ([Kontext](https://www.reddit.com/r/Finanzen/comments/imznol/neue_freundin_und_umfeld_durchkreuzen_meine/)). (Hauptsache, ihr lasst 'nen Stern da.)

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
| `list_transactions` | Transactions with date, amount, counterparty and cleaned-up purpose; the merchant instead of PayPal; transfers between your own accounts are marked |
| `summarize_transactions` | Cash flow and spending per month, counterparty, type or your own categories, for one or all accounts, computed on the server; transfers between your own accounts are reported separately |
| `find_recurring_payments` | Subscriptions, contracts and standing orders with rhythm, price changes and yearly cost (last 180 days, all the API returns) |
| `list_cards` | Card balances (Visa); the API has no card transactions |
| `get_wealth_overview` | All product balances with bank-supplied EUR totals, including loans and savings |
| `list_depots` | Securities accounts |
| `get_depot_positions` | Positions (name, ISIN, WKN, values, P&L) and depot balance, optionally for one security |
| `list_depot_transactions` | Securities purchases, sales and transfers with filters and continuation |
| `summarize_portfolio` | Largest positions and allocation percentages per currency |
| `get_instrument` | Security metadata; optional fund fees/ratings, derivative details and trading venues |
| `list_orders` / `get_order` | Read the order book and individual orders; never place or change orders |
| `list_documents` | Postbox documents (statements, order confirmations, tax documents) |
| `read_document` | A document as bounded text, its cover page, or a link to the PDF; comdirect marks it as read |

Arguments and results: [Tools reference](docs/reference/tools.md).

### Prompts

Ready-made analyses you start yourself, e.g. as slash command in Claude Code and VS Code:

| Prompt | Description |
| --- | --- |
| `monthly_review` | Income and expenses of a month compared with the previous month |
| `find_subscriptions` | Recurring payments with projected yearly costs and cancellation candidates |
| `tax_documents` | Tax documents of a year in the postbox, listed before anything is opened |

Categories for `summarize_transactions` come from a local rules file:
[Categorize transactions](docs/how-to/categorize-transactions.md).

## Quickstart

New to this? Follow the [Getting started tutorial](docs/tutorials/getting-started.md).

### 1. Prerequisites

- [uv](https://docs.astral.sh/uv/) (provides `uvx`)
- comdirect API access: in the online banking under **Verwaltung → Entwicklerzugang** you get a Client ID and
  Client Secret ([step by step](docs/how-to/get-comdirect-api-access.md))
- **photoTAN Push** as your default TAN method

### 2. Store your credentials in the OS keychain

```bash
uvx comdirect-mcp@0.6.0 configure
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
      "args": ["comdirect-mcp@0.6.0"]
    }
  }
}
```

**Claude Code**

```bash
claude mcp add --transport stdio --scope user comdirect -- uvx comdirect-mcp@0.6.0
```

**VS Code** (*MCP: Open User Configuration*)

```json
{
  "servers": {
    "comdirect": {
      "type": "stdio",
      "command": "uvx",
      "args": ["comdirect-mcp@0.6.0"]
    }
  }
}
```

**Ollama** (via [ollmcp](https://github.com/jonigl/mcp-client-for-ollama))

```bash
uvx ollmcp mcp add --scope user comdirect -- uvx comdirect-mcp@0.6.0
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
