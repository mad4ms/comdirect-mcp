from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Account:
    id: str
    currency: str
    balance: Decimal
    available: Decimal | None


@dataclass(frozen=True)
class AccountHolder:
    holder_name: str | None
    iban: str | None
    bic: str | None


@dataclass(frozen=True)
class Transaction:
    account_id: str
    booking_date: date | None  # None for not yet booked transactions
    amount: Decimal
    currency: str
    purpose: str | None
    type: str | None  # This is transaction_type.key from API

    # Extended fields
    reference: str | None = None
    booking_status: str | None = None
    # Raw YYYY-MM-DD: comdirect can return dates that do not exist, e.g. 2019-02-30 (API docs 4.2.3)
    valuta_date: str | None = None

    # DirectDebit specific
    direct_debit_creditor_id: str | None = None
    direct_debit_mandate_id: str | None = None
    end_to_end_reference: str | None = None

    new_transaction: bool = False

    # Counterparties
    remitter: AccountHolder | None = None
    debtor: AccountHolder | None = None
    creditor: AccountHolder | None = None


@dataclass(frozen=True)
class Depot:
    id: str  # depotId
    display_id: str | None  # depotDisplayId
    client_id: str | None


@dataclass(frozen=True)
class DepotPosition:
    depot_id: str
    position_id: str
    wkn: str | None
    quantity: Decimal | None
    quantity_unit: str
    current_value: Decimal | None
    current_value_currency: str
    purchase_value: Decimal | None
    purchase_value_currency: str
    profit_loss_purchase_abs: Decimal | None
    profit_loss_purchase_rel: str | None  # Keeping as string for now as it's pre-formatted often
    profit_loss_prev_day_abs: Decimal | None
    profit_loss_prev_day_rel: str | None
    instrument_name: str | None
    isin: str | None = None


@dataclass(frozen=True)
class DepotBalance:
    depot_id: str
    date_last_update: str | None
    current_value: Decimal | None
    current_value_currency: str
    purchase_value: Decimal | None
    purchase_value_currency: str
    prev_day_value: Decimal | None
    prev_day_value_currency: str
    profit_loss_purchase_abs: Decimal | None
    profit_loss_purchase_rel: str | None
    profit_loss_prev_day_abs: Decimal | None
    profit_loss_prev_day_rel: str | None


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    date_creation: str
    mime_type: str
    advertisement: bool
    already_read: bool | None = None
