# MCP tool review

> The reviews below predate the tool consolidation in 0.6.0: `download_document`,
> `extract_document_text` and `get_document_cover` are now `read_document`, `get_account_balance`,
> `get_depot_position` and `get_order_dimensions` were merged into `list_accounts`, `get_depot_positions` and
> `get_instrument`. See the [changelog](../../CHANGELOG.md).

This review uses the actual local CLI executable as a subprocess, with MCP JSON-RPC over stdin/stdout.
Live responses are inspected in memory only; no credentials, account identifiers, amounts, names, references
or documents are recorded here. The test is reproducible with `scripts/live_stdio_check.py`.

An earlier successful live data run (2026-10-10) completed the then-existing ten tools with one push-TAN login and exited with zero failing
checks. It covered every available account and depot, transaction filters and continuation, all three summary
groupings, compact/verbose outputs, document continuation, an already-read PDF download, invalid inputs,
logout, subsequent access rejection and repeat logout. No banking data was persisted.

An earlier live run found five failed checks caused by two defects: unsupported direction values and ignored
booking-date bounds. Both corrections now pass the live retest. That earlier session also remained usable after
620 seconds. The latest run skipped that waiting period; it does not repeat the expiry verification.
The expanded code passes 168 offline tests, Ruff, formatting and Mypy, including real subprocess tests in both
modern and legacy modes.

## New read tools and latest login attempt

Three read tools have since been added: `list_depot_transactions`, `get_wealth_overview`, `get_instrument`.
All thirteen tools pass subprocess tests with a synthetic bank in both protocol modes; the real CLI catalog,
schemas and unauthenticated guards also pass in both modes. New transport tests cover every wealth product
type, bank-supplied aggregates, missing/unknown fields, local depot date bounds, incomplete lists, compact/
verbose instrument metadata, fund fees/ratings and derivative fields.

The first new live login did not complete; the user clarified that they missed its approval window. A separately
approved second run allowed 60 seconds, completed login and exercised all thirteen tools. It exited with one
failed check: `list_depot_transactions` returned a tool error. The original checker discarded that error's details.
A separately authorized targeted run established that the bank's initial depot page is shorter than its
reported match count; unfiltered and date-filtered requests were rejected as incomplete, while ISIN filtering
passed. The client now follows bank pages using raw offsets and detects repeated/empty pages or changing
counts. This fix passes transport regressions. Its first live retest stopped at TAN confirmation (HTTP 400); the user
confirmed they had not approved the request. No data endpoint was reached. The checker now waits for an
explicit human approval by default. A separately authorized retest then completed one login after the user
confirmed approval in the app and exited with zero failing checks. It verified depot transaction schemas,
date and ISIN filters, first-page truncation and continuation against the complete sequence, followed by logout,
post-logout access rejection and repeat logout. The targeted checker emits only allowlisted error categories/HTTP
statuses; no banking data was persisted.

The wealth overview passed schema, compact/verbose agreement, masking and product-count checks. One product
had no known balance or currency, which is exposed through `missing_value_count`; no amount was invented.
EUR totals were not independently summed because individual values were incomplete. Instrument lookup passed
for all thirteen identifiable holdings in both compact and verbose modes. Logout and post-logout blocking passed.

## Results by tool

| Tool | Live review | Corrections / remaining improvements |
| --- | --- | --- |
| `login` | One push approval, modern multi-round-trip flow, schema accepted | Active-session login now fails before a new push; covered offline in both modes |
| `logout` | Explicit logout, subsequent data-call rejection and repeat logout | Remote revocation is best effort; this stdio test cannot inspect tokens |
| `list_accounts` | Every available account; decimal strings, type, masking, schema | Optional missing fields are supported; account identifiers stay available for follow-up calls |
| `list_transactions` | Every account; compact/verbose agreement, limits, pending, dates, directions and masking | Corrected direction translation and local date filtering pass live. Filtered `offset`/`next_offset` continuation matches the remaining sequence; transport and subprocess regressions cover it |
| `summarize_transactions` | Every account; all three groupings; independent transaction totals; bounded groups and merged remainder | Totals agree with independently listed, date-filtered transactions in all three groupings. Explain transfers between own accounts when interpreting income/expenses |
| `list_cards` | Card balances, decimal strings, schema and suffix-size check | Balances are available; individual card transactions are not supplied by this API. Improve identification when multiple cards lack a suffix |
| `list_depots` | Every available depot; display-number masking, schema | No dedicated single-depot lookup is needed for current tools |
| `get_depot_positions` | Every depot; instrument names, identifiers, decimal values and resolved quantity units | Compact default agrees with verbose fields and reduced the tested response size by about 55%. Consider allocation summaries |
| `list_documents` | Two pages, page-size/count consistency and schema | `has_more`/`next_index` agree with the next page. A one-record lookahead establishes continuation without inventing a total; `count` describes the returned page |
| `list_depot_transactions` | Corrected bank paging passed live; date/ISIN filters, schemas, truncation and continuation agree | Bank pages are followed using raw offsets; incomplete/stalled responses and changing counts are guarded by transport regressions |
| `get_wealth_overview` | Passed structure, masking, completeness and compact/verbose checks | All five product types, optional bank EUR totals, masking and completeness metadata tested offline; foreign currencies and loan signs are preserved |
| `get_instrument` | All thirteen identifiable holdings, compact/verbose and identity checks | Static/fund/derivative fields and comma-separated projection tested offline; omitted flags remain unknown |
| `download_document` | An already-read PDF; base64, URI, MIME type, PDF signature and size bound | Bounded text is available through `extract_document_text`; downloading marks an unread document as read |

## Remaining read operations and release preparation

Eight further tools bring the catalog to twenty-one. A full live stdio round completed one approved login,
exercised every tool and logged out. It found incorrect identifier routing in `get_order_dimensions` (ISINs
were sent as UUID filters), and the live single-position endpoint returned a direct object rather than the
PDF's described `values` envelope. The initial round exited with 27 failed checks. Both client assumptions
were corrected and added to the synthetic transport regressions; direct and enveloped position responses
are supported, and ISIN/WKN/UUID filters are selected explicitly.

A separate targeted round then completed one approved login and passed the corrected single-position and
order-dimension lookups for every available identifiable position. Dimension venue identities agreed with
the explicitly requested instrument projection. Single-account balances, portfolio currency totals, omitted
remainder and allocation weights, order-book schemas, bounded PDF text and page continuation passed live.
The original tools also passed during the full round.

| New tool | Live result | Boundary |
| --- | --- | --- |
| `get_account_balance` | Every available account; schema, masking, identity/currency agreement | Balances can change between calls |
| `get_depot_position` | Every available identified position after the response-shape correction | Sparse and enveloped variants also tested offline |
| `summarize_portfolio` | Independent position-value totals, remainder and weights agree | Mixed currencies, missing/negative values and zero totals tested offline; no FX conversion |
| `list_orders` | Empty order-book schemas accepted in compact/verbose modes | Paging, filters, executions and combination orders tested with synthetic orders |
| `get_order` | Missing-id error path reached | No existing order id was available; successful real-order retrieval is not live-verified |
| `get_order_dimensions` | All available identifiable holdings; venue count and instrument-projection identity agree after identifier correction | WKN and UUID routing covered offline |
| `extract_document_text` | Already-read PDF; bounded text, untrusted notice and page continuation accepted | No content persisted; scans/encryption/invalid PDFs and safety limits covered offline |
| `get_document_cover` | One already-read document's plain-text result/schema passed | Other tested documents returned upstream HTTP 500; actionable fallback is exposed, no automatic retry |

The final targeted round exited with one failed check, exclusively the bank's HTTP 500 for one cover page.
This is not an all-green live report. The same endpoint succeeded for another document; no general cover-page
availability is assumed. Both rounds logged out and verified post-logout blocking. No banking data was persisted.

Version metadata and pinned examples are prepared for 0.5.0; change notes remain under `Unreleased` until the
release is finalized. Wheel and source distribution build successfully. The isolated installed wheel passes
catalog/schema/annotation/login-guard checks in both protocol modes, without a bank login. Neither artifact
packages a dotenv file or a PDF. No commit, push, tag or publication has been performed.

## Validation boundaries

Successful live runs cover the account filters, continuation, compact-depot corrections and corrected depot-transaction paging.
The expanded thirteen-tool run and the final targeted depot run are separate sessions; no single all-thirteen-tool
run has been repeated after the paging fix. Active-login protection and
unnamed-counterparty handling are covered offline, including both protocol modes. There is no automatic
login retry. The live run uses modern negotiation; legacy login and all tools are exercised with a synthetic
bank through real subprocess pipes.

The live expiry check calls data again after more than ten minutes in the same process/session. Success
establishes session continuity beyond the documented access-token lifetime; it does not inspect token values.


Empty pending-transaction results validate the response shape but cannot establish every real pending-data
variant. Large-document rejection, mixed currencies, missing values, declined approvals and TAN-limit behavior
are verified with synthetic tests to avoid account side effects.

## Continuation boundaries

Transaction offsets count the locally filtered sequence. Each page scans from the beginning, which can cost
more bank requests for later pages. New bookings between calls can shift the sequence; it is not a snapshot.
Document continuation uses an additional one-record request when a page is full. Postbox changes can shift
indices between calls, and no total is exposed.

## Next priorities

1. Successfully live-verify individual-order details when a genuine existing order is available; do not create
   an order merely for testing.
2. Track document-specific HTTP 500 responses from comdirect's pre-document service; use bounded PDF text or
   document download when no cover is available.
3. Optional portfolio asset-class classification would require an explicit, trustworthy classification source.

The previous read-operation gaps are implemented and documented in [API coverage](api-coverage.md).
Card identification uses the supplied opaque id when suffixes are missing; no labels/numbers are invented.
Server instructions and the tool reference explain that cash-flow totals include transfers between own accounts.
