# Python API

Public API of the `comdirect_mcp` package. Usage examples: [Use the Python library](../how-to/use-the-python-library.md).

## `ComdirectClient`

```python
from comdirect_mcp import ComdirectClient

ComdirectClient(credentials: dict, tan_handlers: dict | None = None)
```

- `credentials`: `client_id`, `client_secret`, `username` (Zugangsnummer), `password` (PIN)
- `tan_handlers` (all optional):
  `push_tan_cb() -> str`, `photo_tan_cb(png: bytes) -> str`, `sms_tan_cb() -> str`

| Member | Description |
| --- | --- |
| `login()` | Full login, resolves the TAN through the handlers |
| `start_login(tan_type=None) -> TanChallenge` | Starts a login and triggers the 2FA challenge; `tan_type` requests `P_TAN_PUSH`, `P_TAN` or `M_TAN` instead of the preferred method |
| `complete_login(challenge, tan="")` | Confirms the challenge (empty TAN for an approved push) |
| `is_logged_in: bool` | Whether a session is active |
| `refresh_token()` | Refreshes the access token now (normally automatic) |
| `logout()` | Revokes the session at comdirect (best effort; the refresh token stops working, the last access token expires within 10 minutes) and drops it locally |
| `list_accounts() -> list[Account]` | Accounts with balances |
| `list_transactions(account_id, with_account=False, paging_first=0, transaction_state=None, transaction_direction=None, min_booking_date=None, max_booking_date=None) -> list[Transaction]` | All matching transactions |
| `iter_all_transactions(...) -> Iterator[Transaction]` | Same arguments, fetches pages lazily (`transaction_state` defaults to `"BOOKED"`) |
| `list_depots() -> list[Depot]` | Securities accounts |
| `get_depot_positions(depot_id) -> tuple[DepotBalance, list[DepotPosition]]` | Balance and positions, including instrument data |
| `list_documents(paging_first=0, paging_count=1000) -> list[Document]` | Postbox documents |
| `download_document(document_id, mime_type) -> bytes` | Raw document content; comdirect marks an unread document as read |

Dates are passed as `YYYY-MM-DD` strings. All methods are thread-safe with respect to token refresh.

## Models

Frozen dataclasses in `comdirect_mcp.domain.models`. Amounts are `Decimal`, dates `datetime.date`. The comdirect
API guarantees no field, so fields are `None` when it omits them.

| Class | Fields |
| --- | --- |
| `Account` | `id`, `currency`, `balance`, `available` |
| `Transaction` | `account_id`, `booking_date`, `valuta_date` (raw `str`, may be a non-existent date like `2019-02-30`), `amount`, `currency`, `purpose`, `type`, `reference`, `booking_status`, `direct_debit_creditor_id`, `direct_debit_mandate_id`, `end_to_end_reference`, `new_transaction`, `remitter`, `debtor`, `creditor` |
| `AccountHolder` | `holder_name`, `iban`, `bic` |
| `Depot` | `id`, `display_id`, `client_id` |
| `DepotBalance` | `depot_id`, `date_last_update`, `current_value`, `purchase_value`, `prev_day_value` (each with `*_currency`), `profit_loss_purchase_abs`, `profit_loss_purchase_rel`, `profit_loss_prev_day_abs`, `profit_loss_prev_day_rel` |
| `DepotPosition` | `depot_id`, `position_id`, `wkn`, `isin`, `instrument_name`, `quantity`, `quantity_unit`, `current_value`, `purchase_value` (each with `*_currency`), `profit_loss_*` as in `DepotBalance` |
| `Document` | `id`, `name`, `date_creation`, `mime_type`, `advertisement`, `already_read` |
| `TanChallenge` | `id`, `typ` (`P_TAN_PUSH`, `P_TAN`, `M_TAN`), `session_id`, `challenge` (base64 PNG for `P_TAN`) |

Relative values (`*_rel`) are percentages as strings, e.g. `"10.00"`.

## Exceptions

| Exception | Raised when |
| --- | --- |
| `ComdirectError` | Base class of the exceptions below |
| `AuthenticationError` | Login, TAN confirmation or token refresh failed; network errors during login |
| `TanError` (subclass of `AuthenticationError`) | Unknown TAN type, no handler for the requested method, or a handler raised |
| `ApiException` | Any other HTTP error from the API; `.status`, `.reason`, `.body` |

## TAN helpers

`comdirect_mcp.utils` has interactive handlers for scripts: `default_push_tan_callback` (waits for Enter),
`default_sms_tan_callback`, `default_photo_tan_callback` (shows the image, needs the `phototan` extra).
