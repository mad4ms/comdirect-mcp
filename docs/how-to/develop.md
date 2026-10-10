# Develop

How to set up the project, run the checks and verify changes. Architecture background:
[Design decisions](../explanation/design.md).

## Setup

```bash
git clone https://github.com/mad4ms/comdirect-mcp.git
cd comdirect-mcp
uv sync --all-extras        # creates .venv with the package (editable), dev tools and extras
uv run pre-commit install   # see below
cp .env.example .env        # only needed for examples and the live check
```

## Project layout

```text
src/comdirect_mcp/
├── cli.py             # `comdirect-mcp` command: serve (default), configure
├── cli.py             # `comdirect-mcp` command: serve (default), configure
├── server.py          # MCP server (MCPServer, tools, login via elicitation)
├── credentials.py     # credential lookup: environment, OS keychain, .env
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

It logs in (one push TAN, no retry), calls every tool through an in-process MCP client, forces a token refresh
and logs out. It prints structure only - counts, which fields are set, format checks - never amounts, ids,
names, IBANs or payment texts, and writes nothing to disk.

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
