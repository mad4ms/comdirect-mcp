# Tools

All tools return structured content with a JSON output schema (except `download_document`, which returns an
embedded resource). Amounts are decimal strings (`"1234.56"`) to avoid floating point rounding, dates are
`YYYY-MM-DD`, and missing values are `null`. Errors are returned as tool results with `isError: true` and a message
the assistant can act on (e.g. "call `login`").

| Tool | Annotations |
| --- | --- |
| [`login`](#login) | `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: false`, `openWorldHint: true` |
| [`logout`](#logout) | `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: true` |
| [`download_document`](#download_document) | `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: true` |
| all other tools | `readOnlyHint: true`, `openWorldHint: true` |

No tool can move money or change orders. The only state change at comdirect besides the session is that
`download_document` marks an unread document as read.

## login

Starts a new session: comdirect sends a push TAN to the photoTAN app, the client asks the user to confirm the
approval (elicitation). See [Login and sessions](../explanation/login-and-sessions.md).

- Arguments: none
- Result: `status`: `"logged_in"`

## logout

Ends the session and revokes it at comdirect: the refresh token stops working immediately, the last access token
expires within 10 minutes (comdirect does not invalidate it right away). The server does the
same when it shuts down.

- Arguments: none
- Result: `status`: `"logged_out"`

## list_accounts

- Arguments: none
- Result: `accounts[]` with `id`, `currency`, `balance`, `available`

## list_transactions

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `account_id` | string | required | `id` from `list_accounts` |
| `transaction_state` | `BOOKED` \| `NOTBOOKED` | `BOOKED` | `NOTBOOKED` are pending transactions (no paging, no booking date) |
| `transaction_direction` | `INCOMING` \| `OUTGOING` \| null | null | Filter by direction |
| `min_booking_date` | date \| null | null | Earliest booking date, inclusive |
| `max_booking_date` | date \| null | null | Latest booking date, inclusive |
| `limit` | integer 1-2000 | 250 | Maximum number of transactions |

Result: `account_id`, `count`, `truncated` (more transactions exist beyond `limit`), `transactions[]` with

- `account_id`, `booking_date`, `valuta_date` (raw string: comdirect may return non-existent dates such as
  `2019-02-30`), `amount`, `currency`, `type` (e.g. `TRANSFER`, `DIRECT_DEBIT`, `SECURITIES`),
  `booking_status`, `purpose` (payment reference), `reference`, `end_to_end_reference`, `new_transaction`
- `remitter`, `debtor`, `creditor`: `holder_name`, `iban` (masked by default), `bic`
- `direct_debit_creditor_id`, `direct_debit_mandate_id`

## list_depots

- Arguments: none
- Result: `depots[]` with `id`, `display_id`, `client_id`

## get_depot_positions

| Argument | Type | Description |
| --- | --- | --- |
| `depot_id` | string, required | `id` from `list_depots` |

Result:

- `depot_id`
- `balance`: `current_value`, `purchase_value`, `prev_day_value` (each with `*_currency`),
  `profit_loss_purchase_abs`/`_rel`, `profit_loss_prev_day_abs`/`_rel`, `date_last_update`
- `positions[]`: `instrument_name`, `isin`, `wkn`, `quantity`, `quantity_unit`, `current_value`,
  `purchase_value` (each with `*_currency`), `profit_loss_purchase_abs`/`_rel`, `profit_loss_prev_day_abs`/`_rel`,
  `position_id`, `depot_id`

Relative values (`*_rel`) are percentages as strings, e.g. `"10.00"`. Units (`quantity_unit`, `*_currency`) are
ISO 4217 currency codes or comdirect's special units: `XXX` pieces, `XXC` percent, `XXM` per mille, `XXP` points,
`XXU` unknown.

## list_documents

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `paging_first` | integer >= 0 | 0 | Index of the first document |
| `paging_count` | integer 1-1000 | 200 | Maximum number of documents |

Result: `count`, `documents[]` with `document_id`, `name`, `date`, `mime_type` (`application/pdf` or
`text/html`), `advertisement`, `already_read`

## download_document

| Argument | Type | Description |
| --- | --- | --- |
| `document_id` | string, required | from `list_documents` |
| `mime_type` | string, required | from `list_documents` |

Result: an embedded resource `comdirect://documents/{document_id}` with the document as base64 `blob` and its
`mimeType`. Documents above `COMDIRECT_MCP_MAX_DOCUMENT_BYTES` (default 10 MB) are rejected.

comdirect marks an unread document as read when it is downloaded, which is why this tool is not annotated
read-only.
