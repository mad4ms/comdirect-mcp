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
| `get_account_balance(account_id) -> Account` | Dedicated single-account balance lookup |
| `list_transactions(account_id, with_account=False, paging_first=0, transaction_state=None, transaction_direction=None, min_booking_date=None, max_booking_date=None) -> list[Transaction]` | All matching transactions |
| `iter_all_transactions(...) -> Iterator[Transaction]` | Same arguments, fetches pages lazily (`transaction_state` defaults to `"BOOKED"`) |
| `list_depot_transactions(depot_id, isin=None, min_booking_date=None, max_booking_date=None) -> list[DepotTransaction]` | Securities movements with automatic bank paging and local date checks; dates are `date` objects |
| `get_wealth_overview() -> WealthOverview` | Unfiltered product report and bank-supplied EUR aggregates |
| `get_instrument(identifier, verbose=False, include_order_dimensions=False) -> Instrument` | WKN, ISIN or case-sensitive symbol; optional fund/derivative data and order dimensions |
| `get_order_dimensions(identifier, venue_id=None, side=None, order_type=None) -> OrderDimensions` | Read tradability metadata |
| `list_orders(depot_id, status=None, side=None, order_type=None, venue_id=None) -> list[Order]` | Complete reported bank pages with local filters; no writes |
| `get_order(order_id) -> Order` | Single order and optional executions/sub-orders |
| `list_cards() -> list[Card]` | Cards with balances (the API has no card transactions) |
| `list_depots() -> list[Depot]` | Securities accounts |
| `get_depot_positions(depot_id) -> tuple[DepotBalance, list[DepotPosition]]` | Balance and positions, including instrument data |
| `get_depot_position(depot_id, position_id) -> DepotPosition` | One position with instrument metadata |
| `list_documents(paging_first=0, paging_count=1000) -> list[Document]` | Postbox documents |
| `download_document(document_id, mime_type) -> bytes` | Raw document content; comdirect marks an unread document as read |
| `get_document_cover(document_id) -> bytes` | Raw HTML pre-document; the MCP view strips active content and bounds text |

Account transaction dates are passed as `YYYY-MM-DD` strings and filtering is enforced locally. `INCOMING`/`OUTGOING` are mapped
to the banking API's `CREDIT`/`DEBIT`; the Python client also accepts these native values. Date filters cannot
be combined with `NOTBOOKED`. All methods are thread-safe with respect to token refresh.

## Models

Frozen dataclasses in `comdirect_mcp.domain.models`. Amounts are `Decimal`, dates `datetime.date`. The comdirect
API guarantees no field, so fields are `None` when it omits them.

| Class | Fields |
| --- | --- |
| `Account` | `id`, `currency`, `balance`, `available`, `type` (e.g. `CA`), `type_name` (e.g. `Girokonto`), `display_id` (account number), `iban`, `credit_limit` |
| `Transaction` | `account_id`, `booking_date`, `valuta_date` (raw `str`, may be a non-existent date like `2019-02-30`), `amount`, `currency`, `purpose`, `type`, `reference`, `booking_status`, `direct_debit_creditor_id`, `direct_debit_mandate_id`, `end_to_end_reference`, `new_transaction`, `remitter`, `debtor`, `creditor`, `counterparty` (the other party, resolved from the SEPA roles), `direction` (`in`/`out`), `purpose_raw` (`purpose` is cleaned up, see `domain.mappers.normalize_purpose`) |
| `AccountHolder` | `holder_name`, `iban`, `bic` |
| `Depot` | `id`, `display_id`, `client_id` |
| `DepotBalance` | `depot_id`, `date_last_update`, `current_value`, `purchase_value`, `prev_day_value` (each with `*_currency`), `profit_loss_purchase_abs`, `profit_loss_purchase_rel`, `profit_loss_prev_day_abs`, `profit_loss_prev_day_rel` |
| `DepotPosition` | `depot_id`, `position_id`, `wkn`, `isin`, `instrument_name`, `quantity`, `quantity_unit` (`pieces`, `percent`, ... or a currency), `current_value`, `purchase_value` (each with `*_currency`), `profit_loss_*` as in `DepotBalance` |
| `Document` | `id`, `name`, `date_creation`, `mime_type`, `advertisement`, `already_read` |
| `Card` | `id`, `type`, `type_name`, `number_suffix`, `status`, `balance`, `available`, `limit`, `currency` |
| `TanChallenge` | `id`, `typ` (`P_TAN_PUSH`, `P_TAN`, `M_TAN`), `session_id`, `challenge` (base64 PNG for `P_TAN`) |

Relative values (`*_rel`) are percentages as strings, e.g. `"10.00"`.

## Exceptions

| Exception | Raised when |
| --- | --- |
| `ComdirectError` | Base class of the exceptions below |
| `AuthenticationError` | Login, TAN confirmation or token refresh failed; network errors during login |
| `TanError` (subclass of `AuthenticationError`) | Unknown TAN type, no handler for the requested method, or a handler raised |
| `TransactionFilterError` | Invalid filter, or missing date/amount needed to apply a filter honestly |
| `DataError` | Ambiguous single-object lookup, incomplete/unstable bank paging, excessive order nesting or bounded PDF extraction failure |
| `ApiException` | Any other HTTP error from the API; `.status`, `.reason`, `.body` |

## TAN helpers

`comdirect_mcp.utils` has interactive handlers for scripts: `default_push_tan_callback` (waits for Enter),
`default_sms_tan_callback`, `default_photo_tan_callback` (shows the image, needs the `phototan` extra).

## Additional read models

- `DepotTransaction`: required request `depot_id`; optional `transaction_id`, `booking_status`, `booking_date`,
  `business_date`, `settlement_date` (raw timestamp), `instrument_id`, `instrument_name`, `isin`, `wkn`, `quantity`,
  `quantity_unit`, `execution_price`, `execution_price_currency`, `transaction_value`, `transaction_value_currency`,
  `direction` (`IN`/`OUT`, securities direction), `type` (key of EnumText or the string returned by the bank).
- `ProductBalance`: optional `id`, `type`, `type_name`, `display_id`, `balance`, `currency`, `available`,
  `available_currency`, `connection_type`, `target_client_id`. Python values are unmasked; MCP masks display ids.
- `WealthOverview`: immutable `products` tuple and optional `total_balance_eur`, `total_available_eur`,
  `reported_count`. Aggregates are preserved only for explicit EUR units; missing totals are not reconstructed.
- `Instrument`: optional `id`, `name`, `short_name`, `isin`, `wkn`, `mnemonic`, `type`, `currency`, `notation`,
  `priips_relevant`, `kid_available`, `shipping_waiver_required`, `fund_redemption_limited`, `fund`, `derivative`,
  `order_dimensions`.
- `FundDetails`: optional `status`, immutable `flags` tuple, `currency`, `investment_category`,
  `total_expense_ratio`, `regular_issue_surcharge`, `discount_issue_surcharge`, `reduced_issue_surcharge`,
  `individual_issue_surcharge`, `individual_issue_surcharge_corrected`, `bonification`, `morningstar_rating`,
  `moodys_rating`.
- `DerivativeDetails`: optional `underlying_name`, `underlying_isin`, `underlying_wkn`, `certificate_type`,
  `warrant_type`, `strike_price`, `strike_price_currency`, `leverage`, `multiplier`, `expiry_date`, `maturity_date`,
  `yield_pa`, `remaining_term_in_years`, `nominal_rate`, `interest_payment_date`, `interest_payment_interval`,
  `morningstar_rating`, `moodys_rating`, `underlying_price` (`PriceSnapshot`).
- `PriceSnapshot`: optional `type`, `price`, `currency`, `quantity`, `quantity_unit`, `timestamp`.
- `OrderDimensions`: optional immutable `venues` tuple. `Venue`: optional `id`, `name`, `country`, `type`,
  immutable `currencies`, `sides`, `validity_types` tuples and immutable `order_types` pairs of name and
  `OrderTypeDetails` (optional `limit_extensions`, `trading_restrictions` tuples).
- `Order`: optional `id`, `depot_id`, `instrument_id`, `instrument_name`, `isin`, `wkn`, `side`, `type`, `status`,
  `quantity`, `quantity_unit`, `open_quantity`, `executed_quantity`, `cancelled_quantity`, `limit`, `limit_currency`,
  `trigger_limit`, `trigger_limit_currency`, `trailing_limit_distance`, `trailing_limit_distance_currency`,
  `trailing_limit_percent`, `expected_value`, `expected_value_currency`, `venue_id`, `created_at`, `validity_type`,
  `validity` (`date`), `best_execution`, `leg_number`, `settlement_account_id`, `limit_extension`,
  `trading_restriction`, immutable `executions` and `sub_orders` tuples. No order mutation API is exposed.
- `Execution`: optional `id`, `number`, `quantity`, `quantity_unit`, `price`, `currency`, `timestamp`.

All new models are frozen dataclasses. Numeric fees/ratios and amounts are `Decimal`; actual date fields are
`date`. The new read endpoints decode JSON before mapping because the generated schema loses polymorphic
product balance fields, models a depot transaction type as a string instead of EnumText, and invents defaults
for optional instrument flags. Generated models remain unchanged and are never exposed.
