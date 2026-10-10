# Use the Python library

The MCP server is built on a typed Python client that you can use directly in scripts and notebooks.

```bash
uv add comdirect-mcp                # or: pip install comdirect-mcp
uv add "comdirect-mcp[phototan]"    # adds Pillow to display photoTAN images in default_photo_tan_callback
```

## Login

Credentials: [Get comdirect API access](get-comdirect-api-access.md). comdirect requires OAuth plus a 2FA
challenge for every session. You decide how the TAN is obtained by passing
callbacks for the TAN methods you use:

```python
import os

from dotenv import load_dotenv

from comdirect_mcp import ComdirectClient
from comdirect_mcp.utils import default_photo_tan_callback, default_push_tan_callback, default_sms_tan_callback

load_dotenv()

client = ComdirectClient(
    credentials={
        "client_id": os.environ["COMDIRECT_CLIENT_ID"],
        "client_secret": os.environ["COMDIRECT_CLIENT_SECRET"],
        "username": os.environ["COMDIRECT_USERNAME"],
        "password": os.environ["COMDIRECT_PASSWORD"],
    },
    tan_handlers={
        "push_tan_cb": default_push_tan_callback,  # approve in the app, then press Enter
        "photo_tan_cb": default_photo_tan_callback,  # shows the image, asks for the TAN (needs [phototan])
        "sms_tan_cb": default_sms_tan_callback,  # asks for the TAN from the SMS
    },
)
client.login()
```

All handlers are optional; a challenge for a method without handler raises `TanError`. A handler receives the
challenge (PNG bytes for photoTAN) and returns the TAN, or an empty string for push TAN.

### Two-step login

For UIs or services that collect the TAN asynchronously, split the login:

```python
challenge = client.start_login()  # triggers the push / SMS, challenge.typ is P_TAN_PUSH, M_TAN or P_TAN
# ... ask the user ...
client.complete_login(challenge, tan="")  # empty TAN for an approved push
```

### Sessions and tokens

Access tokens are refreshed automatically shortly before they expire. If comdirect ends the session (refresh
fails), requests raise `AuthenticationError` and you need to log in again. `client.is_logged_in` tells whether a
session is active, `client.logout()` drops it locally.

## Accounts and transactions

```python
for account in client.list_accounts():
    print(account.id, account.balance, account.available, account.currency)

transactions = client.list_transactions(
    account.id,
    min_booking_date="2026-09-01",
    max_booking_date="2026-09-30",
    transaction_direction="OUTGOING",  # or INCOMING, None for both
)
```

`iter_all_transactions()` yields transactions page by page, so you can stop early:

```python
for tx in client.iter_all_transactions(account.id, min_booking_date="2026-01-01"):
    print(tx.booking_date, tx.amount, tx.currency, tx.purpose)
```

Pending transactions use `transaction_state="NOTBOOKED"`; they have no `booking_date` and no paging.

## Depots

```python
for depot in client.list_depots():
    balance, positions = client.get_depot_positions(depot.id)
    print(depot.display_id, balance.current_value, balance.current_value_currency)
    for position in positions:
        print(position.instrument_name, position.isin, position.quantity, position.current_value)
```

## Postbox documents

```python
from pathlib import Path

for document in client.list_documents(paging_count=20):
    content = client.download_document(document.id, document.mime_type)
    suffix = ".pdf" if document.mime_type == "application/pdf" else ".html"
    Path(f"{document.id}{suffix}").write_bytes(content)
```

## Models and errors

All methods return frozen dataclasses with `Decimal` amounts and `date` dates; most fields can be `None`. Full
list of classes, methods, fields and exceptions: [Python API reference](../reference/python-api.md).

## Examples

- [examples/basic_example.py](../../examples/basic_example.py): tour through all endpoints
- [examples/advanced_example.py](../../examples/advanced_example.py): total wealth, 90-day cash flow, portfolio performance
