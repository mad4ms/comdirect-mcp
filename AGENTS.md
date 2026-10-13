# AGENTS.md

Instructions for AI coding agents working on this repository. Humans: see [docs/how-to/develop.md](docs/how-to/develop.md).

## Project

`comdirect-mcp` is a read-only MCP server (spec 2026-07-28, MCP Python SDK v2 `MCPServer`, stdio) plus a typed
Python client for the comdirect banking REST API. Python 3.12+, managed with uv.

```text
src/comdirect_mcp/cli.py        `comdirect-mcp` command: serve (default), configure (OS keychain)
src/comdirect_mcp/server.py     MCP tools, login via elicitation (Resolve/Elicit -> input_required)
src/comdirect_mcp/views.py      compact agent-facing views, masking, summarize_transactions aggregation
src/comdirect_mcp/credentials.py  credential lookup: environment -> OS keychain -> .env
src/comdirect_mcp/client.py     ComdirectClient: API calls, token refresh (thread-safe)
src/comdirect_mcp/auth.py       OAuth + session + 2FA (start/complete/refresh)
src/comdirect_mcp/domain/       frozen dataclasses + mappers from generated models
src/comdirect_mcp/_openapi/     GENERATED vendor code - never edit
tests/                          unit tests, no network
scripts/live_check.py           manual check against the real API (needs a human)
docs/                           Diátaxis: tutorials/, how-to/, reference/, explanation/
server.json                     MCP Registry metadata
```

## Commands

```bash
uv sync --all-extras            # set up .venv
uv run pytest                   # all tests must pass
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

Run all four before you report a change as done. Use `uv add` / `uv lock` for dependencies, never pip.

## Hard rules

### Security (banking credentials and financial data)

- **Never read, print, copy or edit `.env`** or any file with credentials, and never read or write the OS keychain
  (`keyring`, `security`, `comdirect-mcp configure`). To check configuration, only test whether values are set,
  never output them. Tests use the in-memory keychain from `tests/conftest.py`.
- **Never run `scripts/live_check.py` or anything else that logs in to the real API** unless the user asks for
  it in this conversation. A login sends a push TAN to the user's phone and failed attempts can lock the
  account. One attempt, no automatic retries.
- Never print, log or persist real account data (amounts, IBANs, account/depot ids, names, payment texts,
  documents). Live checks output structure only.
- Never add tools or API calls that move money or write: orders, transfers, document deletion. Annotations must
  stay truthful (`read_document` marks documents as read, so it is not `readOnlyHint`).
- Never weaken defaults that protect data (IBAN masking, document size limit, untrusted-content instructions).

### Code

- The authoritative API description is comdirect's PDF *REST API – Schnittstellenspezifikation*. A local copy may
  exist in `docs/reference/` (git-ignored, copyrighted - never commit it or quote large parts). Its rules beat
  the Swagger file: e.g. no TAN header for push, 9-digit request ids, max. 5 unconfirmed challenges.
- Never weaken the login protections: `MAX_UNCONFIRMED_CHALLENGES`, explicit `P_TAN_PUSH`, revoke on logout and
  shutdown. Never add retries around login or TAN confirmation.

- Never edit `src/comdirect_mcp/_openapi/`. Fix schema problems in `scripts/patch_openapi.py` and regenerate
  (`docs/how-to/regenerate-openapi-client.md`), map fields in `domain/mappers.py`.
- The comdirect spec declares **no field as required**. Mappers must handle every field being absent; use
  `X | None` in domain models rather than inventing defaults (no `0`, no `1970-01-01`).
- Domain models are frozen dataclasses with `Decimal` amounts and `date` dates. Never expose generated models.
- MCP tools return views from `views.py`, not domain models: compact (optional fields via `optional()` are left
  out when null), details behind `verbose`, aggregation on the server. Keep results small - they fill the model's
  context.
- MCP tools: return pydantic models (structured output), raise `ToolError` with an actionable message
  (e.g. "call `login`"), set `ToolAnnotations`. Tool output must validate against its output schema - a
  `None` in a non-optional field makes the client reject the whole result.
- Data tools never log in implicitly; only the `login` tool triggers 2FA.
- Keep comments sparse and factual; English in code and docs. New docs go into the matching Diátaxis section
  (`docs/README.md` lists them); update `docs/reference/` when tools, options or the Python API change. The German warning section in `README.md` stays
  German and keeps its wording.

### Tests

- No test may touch the network. Mock at the level the test is about: generated APIs (`test_client.py`), the
  urllib3 transport (`test_http_roundtrip.py`), or the server state (`test_mcp_server.py`).
- When the real API behaves differently from the spec, change `FakeComdirect` in `test_http_roundtrip.py` to
  the real shape and add a regression test.
- MCP behavior is tested through `mcp.client.Client` against the in-process server, for both the 2026-07-28
  protocol (`mode="auto"`) and the legacy protocol (`mode="legacy"`).

### Releases and metadata

- Version lives in `pyproject.toml` **and** `server.json` (top level and package); `tests/test_packaging.py`
  enforces it. Add user-facing changes to `CHANGELOG.md` under `Unreleased`.
- Keep the `mcp-name: io.github.mad4ms/comdirect-mcp` marker in `README.md` (MCP Registry ownership check).
- GitHub Actions are pinned to full commit SHAs with the version as comment; keep it that way.
- Do not commit, push, tag or publish unless the user asks.
- No AI attribution in commit messages or pull request descriptions (no `Co-Authored-By` trailers for
  agents, no "Generated with ..." lines).
