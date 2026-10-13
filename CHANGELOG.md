# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (0.x: minor versions may break).

## [Unreleased]

### Added

- Prompts `monthly_review`, `find_subscriptions` and `tax_documents`: ready-made analyses that name the right
  tools and pitfalls (internal transfers, documents marked as read). The client can complete their arguments.
- Local category rules (`~/.config/comdirect-mcp/categories.toml`, `COMDIRECT_MCP_CATEGORIES`) and
  `summarize_transactions(group_by="category")`. The rules are applied on the server; the resource
  `comdirect://categories` shows their format and current content.
- `COMDIRECT_MCP_SKIP_ELICITATION=1` replaces the login confirmation dialog with the fixed approval window, for
  clients that decline the dialog without showing it (seen with Claude Code 2.1.296 on protocol 2026-07-28).

### Changed

- A login that is not approved now says whether the dialog was declined, cancelled or submitted without approval,
  and tells the agent not to retry without asking, since each attempt counts towards comdirect's lock after 5.
- The login logs the client's name, protocol version, elicitation capability and raw answer, and each challenge
  step. `COMDIRECT_MCP_LOG_FILE` and `COMDIRECT_MCP_LOG_LEVEL` set where and how much the server logs.

## [0.5.1] - 2026-10-10

### Fixed

- MCP Registry metadata: the `server.json` description fits the registry's 100-character limit, so the release
  is listed in the MCP Registry again (0.5.0 was published to PyPI only).

## [0.5.0] - 2026-10-10

### Changed (breaking)

- A `.env` file in the working directory is no longer read. Point `COMDIRECT_ENV_FILE` to a dotenv file if you
  need one; the OS keychain is recommended.
- Tool results are compact views: null fields are left out and details are behind `verbose: true`.
  `list_transactions` returns date, amount, direction, counterparty, purpose and type; references only verbose.
  `get_depot_positions` returns compact positions; `verbose=true` restores ids, purchase values and detailed
  profit/loss. All data tools use compact views, including depots and documents.

### Added

- `summarize_transactions`: income, expenses, net and count per month, counterparty or type, computed on the
  server, for cash flow questions without loading every transaction into the model's context.
- `list_cards`: card balances (e.g. Visa) from comdirect's balance report. The API has no card transactions.
- `list_depot_transactions`, `get_wealth_overview` and `get_instrument`, with compact/verbose views, local date
  checks and bank-supplied EUR totals. Instrument metadata optionally includes order dimensions and
  bank-supplied underlying-price snapshots.
- `get_account_balance`, `get_depot_position`, `summarize_portfolio` (allocation per currency, no FX
  conversion), read-only `list_orders`, `get_order` and `get_order_dimensions`, `get_document_cover` and
  isolated, bounded PDF text extraction (`extract_document_text`). Twenty-one tools in total.
- Continuation for filtered transactions (`offset`, `next_offset`) and documents (`has_more`, `next_index`).
  Order lists follow bank pages and enforce filters locally; partial position lists cannot be aggregated.
- Transactions have a resolved `counterparty` and a `direction`; comdirect's SEPA roles (remitter for direct
  debits, creditor for transfers) no longer need interpreting.
- Accounts have `type`/`type_name` (e.g. Girokonto, Tagesgeld PLUS), account number, IBAN and credit limit.
- `COMDIRECT_MCP_MASK_NAMES`: optional pseudonyms for counterparty names.
- `scripts/live_stdio_check.py`: real-process review of all MCP tools, filters and aggregate consistency;
  offline startup checks in both modes, one live login and optional token-expiry continuity check.
- Offline subprocess tests exercise all twenty-one tools over stdio in both protocol modes, with fake banking
  transport and authentication.
- Documentation: using the server with Ollama through the ollmcp client (no login dialog, fallback window).

### Changed

- `purpose` is cleaned up: SEPA line numbers removed, words split at the 35-character line boundary joined again,
  trailing reference block removed. `Transaction.purpose_raw` keeps the original.
- `quantity_unit` resolves comdirect's special units (`XXX` → `pieces`, ...).
- Own account numbers, IBANs and depot display numbers are masked like counterparty IBANs.
- Missing API amounts, currencies, identifiers and flags remain unknown instead of causing mapping/schema errors
  or becoming invented defaults. Summaries reject missing amounts/currencies and validate the date range.
- Authentication errors omit response bodies and arbitrary upstream descriptions.
- Regenerated the vendor client with the current generator after removing invented Boolean defaults.
- API coverage reference records missing read endpoints and intentionally excluded writes.
- Live checks suppress error details, return failure on login errors and download only already-read PDFs.

### Fixed

- Repeated `login` on an active session is rejected before sending another push TAN or replacing its tokens.
- Transaction direction filters translate MCP values to the banking API's `CREDIT`/`DEBIT` values.
- Booking-date filters are enforced locally because the account API ignores them; summaries use the same
  filtered transactions. Reversed ranges and date filters on pending transactions are rejected.
- Depot movements follow bank pages using raw offsets instead of rejecting an initial partial response;
  stalled/empty pages and changing match counts still fail explicitly.
- Single depot-position reads accept direct object responses as well as the specification's envelope;
  order-dimension lookups route ISIN/WKN/UUID identifiers to their correct filters.
- An unnamed counterparty with an IBAN/BIC is retained for verbose output; whitespace-only names are omitted.

## [0.4.0] - 2026-10-10

The project is now published as **`comdirect-mcp`** (previously `comdirect-api-wrapper`) and
focuses on the MCP server, while keeping the typed Python client.

### Changed (breaking)

- Renamed the PyPI distribution to `comdirect-mcp` and the import package to `comdirect_mcp`.
- The generated OpenAPI client is vendored as `comdirect_mcp._openapi` instead of a top-level
  `openapi_client` package, so it cannot clash with other generated clients.
- MCP server rebuilt on the MCP Python SDK v2 (`MCPServer`), implementing the MCP specification
  2026-07-28; older clients are supported through version negotiation.
- Login is an explicit `login` tool. The push TAN is confirmed through an MCP elicitation dialog
  (multi round-trip request) instead of a fixed 10 s wait. Other tools no longer log in implicitly.
- `mcp` is a regular dependency, `pillow` moved to the `phototan` extra.
- Missing values are `None` instead of `1970-01-01` or `0` (`Transaction.booking_date`,
  depot and position values, `Transaction.type`, `Depot.display_id`).
- The repository root `mcp_server.py` is gone; start the server with `comdirect-mcp` or
  `python -m comdirect_mcp`.

### Added

- Credentials in the OS keychain: `comdirect-mcp configure` stores them (macOS Keychain, Windows Credential
  Manager, Secret Service); lookup order environment → keychain → `.env`. MCP client configs need no secrets.
- `comdirect-mcp` command line: `serve` (default), `configure [--delete]`, `--version`.
- Automatic access token refresh (`ComdirectClient.refresh_token()`, refresh before expiry).
- Two-step login API: `ComdirectClient.start_login()` / `complete_login()`.
- MCP tool annotations (`readOnlyHint` etc.), structured output with output schemas, and proper
  `isError` results.
- `download_document` returns an embedded resource; size limit via `COMDIRECT_MCP_MAX_DOCUMENT_BYTES`.
- Counterparty IBANs are masked by default (`COMDIRECT_MCP_UNMASK_IBANS`).
- `DepotPosition.isin`; instrument names are now actually returned (`with-attr=instrument`).
- `Document.already_read` / `already_read` in `list_documents`.
- `logout` (and server shutdown) revokes the session at comdirect (`DELETE /oauth/revoke`): the refresh token is
  rejected right away, so the session cannot be extended; the last access token stays valid until it expires
  (at most 10 minutes; measured live, the API documentation claims immediate invalidation).
- The MCP server refuses new logins after three unconfirmed TAN challenges; comdirect locks the online access
  after five.
- Logins request photoTAN Push explicitly (`ComdirectClient.start_login(tan_type=...)`).
- `server.json` for the official MCP Registry and automated registry publishing on release.
- `py.typed` marker, `python -m comdirect_mcp`, `scripts/live_check.py`.
- Documentation in `docs/` following Diátaxis (tutorial, how-to guides, reference, explanation), including how
  to get comdirect API access and how to use a local model.
- `AGENTS.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue forms and a pull request template.

### Fixed

Compared against comdirect's PDF documentation (*REST API – Schnittstellenspezifikation*, April 2020):

- A non-existent valuta date such as `2019-02-30` (documented by comdirect) made the whole transaction list fail;
  `Transaction.valuta_date` is now the raw string.
- `download_document` was annotated read-only although comdirect marks the document as read.
- Push TAN confirmation no longer sends a `x-once-authentication` header (the CLI callback sent a dummy TAN).
- Request ids are 9-digit `HHmmssSSS` numbers and client session ids are hex, as specified.

- Depot balance mapping: the API nests the depot id (`aggregated.depot.depotId`); found in a live test.
- Depot positions had no instrument names because instrument data was never requested.
- `truncated` was reported for transaction lists with exactly `limit` items.
- Lists no longer crash when the API omits `values`.

### Tooling

- uv_build backend, dependency groups, ruff (replaces flake8 and black), mypy in CI.
- CI on Python 3.12-3.14, actions pinned to commit SHAs, Dependabot, release tag/version check,
  `gitleaks-action` v3 (v2 stopped working when GitHub removed Node 20).

## [0.3.1] - 2026-01-25

- Release fixes and documentation updates.

## [0.3] - 2026-01-24

- First MCP server (`mcp_server.py`), VS Code MCP configuration, secret scanning and test workflows.

## [0.2] - 2026-01-18

- Postbox document download; spec patch for document names longer than 50 characters.

## [0.1] - 2026-01-18

- Initial release: OAuth + 2FA login, accounts, transactions, depots.

[Unreleased]: https://github.com/mad4ms/comdirect-mcp/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/mad4ms/comdirect-mcp/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/mad4ms/comdirect-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/mad4ms/comdirect-mcp/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/mad4ms/comdirect-mcp/compare/v0.3...v0.3.1
[0.3]: https://github.com/mad4ms/comdirect-mcp/compare/v0.2...v0.3
[0.2]: https://github.com/mad4ms/comdirect-mcp/compare/v0.1...v0.2
[0.1]: https://github.com/mad4ms/comdirect-mcp/releases/tag/v0.1
