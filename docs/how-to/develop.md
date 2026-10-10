# Develop

How to set up the project, run the checks and verify changes. Architecture background:
[Design decisions](../explanation/design.md).

## Setup

```bash
git clone https://github.com/mad4ms/comdirect-mcp.git
cd comdirect-mcp
uv sync --all-extras        # creates .venv with the package (editable), dev tools and extras
uv run pre-commit install   # see below
# Configure credentials via the keychain, environment or explicit COMDIRECT_ENV_FILE.
```

## Project layout

```text
src/comdirect_mcp/
├── cli.py             # `comdirect-mcp` command: serve (default), configure
├── server.py          # MCP server (MCPServer, tools, login via elicitation)
├── views.py           # compact agent-facing views, masking, aggregation
├── credentials.py     # credential lookup: environment, OS keychain, .env
├── client.py          # ComdirectClient: API calls, token refresh
├── auth.py            # OAuth + session + 2FA flow (start/complete/refresh)
├── domain/            # frozen dataclasses and mappers from the generated models
├── utils.py           # interactive TAN callbacks for scripts
├── exceptions.py
└── _openapi/          # generated OpenAPI client - never edit by hand
tests/                 # unit tests; no test touches the real API
scripts/               # client regeneration, live check against the real API
examples/              # library examples
docs/                  # documentation
server.json            # MCP Registry metadata
```

## Checks

```bash
uv run pytest                    # tests
uv run ruff check .              # lint (pycodestyle, pyflakes, isort, pyupgrade, bugbear)
uv run ruff format --check .     # formatting
uv run mypy                      # types (package ships py.typed)
```

CI runs the same commands on Python 3.12, 3.13 and 3.14.

The test suite has three layers:

- `test_client.py`, `test_auth.py`: client and login logic with the generated APIs mocked
- `test_http_roundtrip.py`: the full stack down to urllib3 against a fake comdirect API that mirrors the real
  response shapes, catching incompatibilities of the generated code with pydantic/urllib3 upgrades
- `test_mcp_server.py`: the MCP server through the SDK's in-memory client, with both the 2026-07-28 protocol
  (multi round-trip requests) and the legacy protocol; validates every structured result against its output schema
- `test_stdio_server.py`: all twenty-one tools over actual subprocess pipes in both protocol modes, with synthetic
  credentials/authentication and the fake bank transport; no network
- `test_credentials.py`: credential precedence and `comdirect-mcp configure` (in-memory keychain, see `conftest.py`)
- `test_packaging.py`: `pyproject.toml`, `server.json` and README stay consistent

## Pre-commit hooks

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

The hooks run ruff (lint + format), basic file checks, gitleaks secret scanning and the tests before every
commit. Update hook versions with `uv run pre-commit autoupdate` (Dependabot does not cover them).

## Live check against the real API

Mocks only prove what we assumed about the API. Before a release, run the live check once:

```bash
uv run python scripts/live_check.py      # waits 20 s for the push approval; pass another number to change it
```

It uses the same credential lookup as the server (keychain or environment recommended; dotenv requires
`COMDIRECT_ENV_FILE`). It logs in (one push TAN, no retry), calls the tools through an in-process MCP client,
forces a token refresh
and logs out. It prints structure only - counts, which fields are set, format checks - never amounts, ids,
names, IBANs or payment texts, and writes nothing to disk. Error details are suppressed. Document download is
checked only when an already-read PDF is on the first page, so the check does not mark an unread document as read.
A failed check exits with a nonzero status.

### Review the real stdio process

```bash
uv run python scripts/live_stdio_check.py --offline     # both protocols; no login or bank access
uv run python scripts/live_stdio_check.py               # one live login; all tools, filters and consistency
uv run python scripts/live_stdio_check.py --depot-only   # targeted depot movement check
uv run python scripts/live_stdio_check.py --remaining-only  # single reads, order metadata, portfolio and text
```

This starts the installed local `comdirect-mcp` executable as a separate process and uses only MCP calls, with
no access to server internals. The live run covers all available accounts/depots, compact and verbose
transactions, date/direction filters, all summary groupings, wealth products/aggregates, depot movements,
compact/verbose metadata for every identifiable holding, document paging, an already-read PDF and invalid
arguments. It masks names and account numbers, suppresses stderr/details, and persists no financial data.
The expanded check also covers single account/position reads, order books and dimensions, portfolio consistency,
plain cover text and bounded PDF text. An empty order book cannot verify a successful individual-order lookup;
that is reported as skipped, with only the missing-id error tested. Cover-page HTTP 500 remains a failed check,
even when another document's cover works. No response content is persisted.
Use `--server-command /path/to/comdirect-mcp --offline` to check an isolated wheel installation without login.
Unexpected tool errors emit only allowlisted diagnostic categories or HTTP statuses; error bodies are never printed.
It keeps the session open for 620 seconds before another data call, then logs out and checks that further data
access requires login. This checks session continuity beyond the documented access-token lifetime; it does
not inspect token values or verify server-side revocation directly. Use `--refresh-wait 0` to skip the expiry
wait. Live approval is manual by default: approve the current photoTAN request, then enter `approved` in
the checker terminal, or enter `cancel` to decline. The client allows up to 300 seconds for this interaction.
For an explicitly timed check use `--no-manual-approval --wait 60`. There is no login retry.

## Running the server locally

```bash
uv run comdirect-mcp                                   # stdio, for MCP clients
npx @modelcontextprotocol/inspector uv run comdirect-mcp   # interactive testing with the MCP Inspector
```

This repository's [.vscode/mcp.json](../../.vscode/mcp.json) starts `.venv/bin/comdirect-mcp` with the credentials from `.env`.

## Releasing

See [Release a new version](release.md).

## Regenerating the OpenAPI client

See [Regenerate the OpenAPI client](regenerate-openapi-client.md).
