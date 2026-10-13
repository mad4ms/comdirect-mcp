# comdirect API coverage

The server implements a subset of the comdirect REST API, not every operation or every response field.
The baseline is *REST API - Schnittstellenspezifikation*, April 2020. A local, git-ignored PDF may be present
in this directory; it must not be committed or redistributed. The table describes coverage against that
version, not a guarantee that the bank has added no operations since then.

## Implemented operations

| Specification section | Python client | MCP tool / behavior |
| --- | --- | --- |
| 2.1-2.5: OAuth, session status, session TAN and secondary token | `login`, `start_login`, `complete_login` | `login`, explicit photoTAN push; elicitation or fallback approval window |
| 3.1.1: token refresh | `refresh_token`, automatic refresh before expiry | Automatic, without a new login |
| 3.1.2: token revocation | `logout` | `logout` and shutdown cleanup |
| 4.1.1: all account balances | `list_accounts` | `list_accounts`, including type and masked display number / IBAN |
| 4.1.2: one account balance | `get_account_balance` | Python only; `list_accounts` already returns every balance |
| 4.1.3: account transactions | `list_transactions`, `iter_all_transactions` | `list_transactions` and `summarize_transactions`; booked paging (stops at the date filter), pending transactions, date/direction filters, internal transfers |
| 5.1.1: depots | `list_depots` | `list_depots` |
| 5.1.2: depot balance and positions | `get_depot_positions` | `get_depot_positions`, with instrument names and ISINs |
| 5.1.3: one depot position | `get_depot_position` | Python only; `get_depot_positions` filters by ISIN |
| 9.1.1: postbox listing | `list_documents` | `list_documents`, one page per call |
| 9.1.2: document content | `download_document` | `read_document` (bounded PDF/HTML text, or a link to the resource `comdirect://documents/{id}`); marks the document as read |
| 9.1.3: document pre-page | `get_document_cover` | `read_document(format="cover")`, bounded plain text from HTML; active content is discarded |
| 5.1.4: depot transactions | `list_depot_transactions` | `list_depot_transactions`, date/ISIN filters and bounded continuation |
| 6.1.1: instrument lookup | `get_instrument` | Static/fund/derivative details, underlying price snapshot when supplied, optional order dimensions |
| 7.1.1: order dimensions | `get_order_dimensions` | `get_instrument(include_order_dimensions=true)`: venue/currency/side/order-type metadata; no order submission |
| 7.1.2-7.1.3: order book and one order | `list_orders`, `get_order` | Read-only order views, filters, paging, optional executions and sub-orders |
| 10.1.1: product balance report | `list_cards`, `get_wealth_overview` | Card balances and full product report with bank-supplied EUR aggregates |

## Read coverage boundaries

The previously listed read-operation gaps in this specification baseline are implemented. This does not
mean every response field is exposed or every response variant has been observed live. Instrument snapshots
are bank-supplied metadata, not a real-time or historical market-data feed. Cost-indication and quote workflows
that require POST remain excluded. Portfolio allocation and bounded PDF text are derived MCP features.

The April 2020 specification defines card balances but no endpoint for individual card transactions.
Account settlements/top-ups are not a substitute for a card spending ledger.

## Intentionally excluded operations

Order creation, modification, cancellation, validation and quote workflows (chapters 7-8), and other operations
that move money or initiate trading, are outside this server's scope. Generated vendor methods are not an
indication of support in the public Python client or MCP tools.

## Field and output policy

Domain models preserve only the fields listed in [Python API](python-api.md). MCP tools expose the views listed
in [Tools](tools.md); optional missing fields are omitted, identifiers needed for subsequent calls remain usable,
and account/depot display numbers and IBANs are masked by default. Transaction references and detailed position values/ids require `verbose`.
Transaction and document lists expose continuation metadata; continuation is not a snapshot.
Unknown amounts and currencies are never replaced with zero or an empty currency. Summaries refuse incomplete
financial values and mixed currencies. The transaction limit and summary truncation flags describe incomplete
results; a successful result does not imply complete API coverage.
