from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Account:
    id: str | None
    currency: str | None
    balance: Decimal | None
    available: Decimal | None
    type: str | None = None  # accountType key, e.g. CA (checking), DAS (Tagesgeld PLUS), SA, FX, LLA
    type_name: str | None = None  # accountType text, e.g. "Girokonto"
    display_id: str | None = None  # account number
    iban: str | None = None
    credit_limit: Decimal | None = None


@dataclass(frozen=True)
class AccountHolder:
    holder_name: str | None
    iban: str | None
    bic: str | None


@dataclass(frozen=True)
class Transaction:
    account_id: str
    booking_date: date | None  # None for not yet booked transactions
    amount: Decimal | None
    currency: str | None
    purpose: str | None  # payment reference, SEPA line numbers removed (see mappers.normalize_purpose)
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

    new_transaction: bool | None = None

    # Counterparties
    remitter: AccountHolder | None = None
    debtor: AccountHolder | None = None
    creditor: AccountHolder | None = None

    # Derived: the other party of the transaction and the money flow, see mappers.map_transaction
    counterparty: AccountHolder | None = None
    direction: str | None = None  # "in" or "out"
    purpose_raw: str | None = None  # remittanceInfo as delivered by the API


@dataclass(frozen=True)
class Depot:
    id: str | None  # depotId
    display_id: str | None  # depotDisplayId
    client_id: str | None


@dataclass(frozen=True)
class DepotPosition:
    depot_id: str | None
    position_id: str | None
    wkn: str | None
    quantity: Decimal | None
    quantity_unit: str | None
    current_value: Decimal | None
    current_value_currency: str | None
    purchase_value: Decimal | None
    purchase_value_currency: str | None
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
    current_value_currency: str | None
    purchase_value: Decimal | None
    purchase_value_currency: str | None
    prev_day_value: Decimal | None
    prev_day_value_currency: str | None
    profit_loss_purchase_abs: Decimal | None
    profit_loss_purchase_rel: str | None
    profit_loss_prev_day_abs: Decimal | None
    profit_loss_prev_day_rel: str | None


@dataclass(frozen=True)
class Document:
    id: str | None
    name: str | None
    date_creation: str | None
    mime_type: str | None
    advertisement: bool | None
    already_read: bool | None = None


@dataclass(frozen=True)
class Card:
    id: str | None
    type: str | None  # cardType key, e.g. VISA_PREPAID
    type_name: str | None
    number_suffix: str | None  # last digits of the card number
    status: str | None
    balance: Decimal | None
    available: Decimal | None
    limit: Decimal | None
    currency: str | None


@dataclass(frozen=True)
class DepotTransaction:
    depot_id: str
    transaction_id: str | None = None
    booking_status: str | None = None
    booking_date: date | None = None
    business_date: date | None = None
    settlement_date: str | None = None
    instrument_id: str | None = None
    instrument_name: str | None = None
    isin: str | None = None
    wkn: str | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    execution_price: Decimal | None = None
    execution_price_currency: str | None = None
    transaction_value: Decimal | None = None
    transaction_value_currency: str | None = None
    direction: str | None = None
    type: str | None = None


@dataclass(frozen=True)
class FundDetails:
    status: str | None = None
    flags: tuple[str, ...] | None = None
    currency: str | None = None
    investment_category: str | None = None
    total_expense_ratio: Decimal | None = None
    regular_issue_surcharge: Decimal | None = None
    discount_issue_surcharge: Decimal | None = None
    reduced_issue_surcharge: Decimal | None = None
    individual_issue_surcharge: Decimal | None = None
    individual_issue_surcharge_corrected: bool | None = None
    bonification: Decimal | None = None
    morningstar_rating: str | None = None
    moodys_rating: str | None = None


@dataclass(frozen=True)
class DerivativeDetails:
    underlying_name: str | None = None
    underlying_isin: str | None = None
    underlying_wkn: str | None = None
    certificate_type: str | None = None
    warrant_type: str | None = None
    strike_price: Decimal | None = None
    strike_price_currency: str | None = None
    leverage: Decimal | None = None
    multiplier: Decimal | None = None
    expiry_date: date | None = None
    maturity_date: date | None = None
    yield_pa: Decimal | None = None
    remaining_term_in_years: Decimal | None = None
    nominal_rate: Decimal | None = None
    interest_payment_date: date | None = None
    interest_payment_interval: str | None = None
    morningstar_rating: str | None = None
    moodys_rating: str | None = None
    underlying_price: PriceSnapshot | None = None


@dataclass(frozen=True)
class Instrument:
    id: str | None = None
    name: str | None = None
    short_name: str | None = None
    isin: str | None = None
    wkn: str | None = None
    mnemonic: str | None = None
    type: str | None = None
    currency: str | None = None
    notation: str | None = None
    priips_relevant: bool | None = None
    kid_available: bool | None = None
    shipping_waiver_required: bool | None = None
    fund_redemption_limited: bool | None = None
    fund: FundDetails | None = None
    derivative: DerivativeDetails | None = None
    order_dimensions: OrderDimensions | None = None


@dataclass(frozen=True)
class ProductBalance:
    id: str | None = None
    type: str | None = None
    type_name: str | None = None
    display_id: str | None = None
    balance: Decimal | None = None
    currency: str | None = None
    available: Decimal | None = None
    available_currency: str | None = None
    connection_type: str | None = None
    target_client_id: str | None = None


@dataclass(frozen=True)
class WealthOverview:
    products: tuple[ProductBalance, ...]
    total_balance_eur: Decimal | None = None
    total_available_eur: Decimal | None = None
    reported_count: int | None = None


@dataclass(frozen=True)
class PriceSnapshot:
    type: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class OrderTypeDetails:
    limit_extensions: tuple[str, ...] | None = None
    trading_restrictions: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Venue:
    id: str | None = None
    name: str | None = None
    country: str | None = None
    type: str | None = None
    currencies: tuple[str, ...] | None = None
    sides: tuple[str, ...] | None = None
    validity_types: tuple[str, ...] | None = None
    order_types: tuple[tuple[str, OrderTypeDetails], ...] | None = None


@dataclass(frozen=True)
class OrderDimensions:
    venues: tuple[Venue, ...] | None = None


@dataclass(frozen=True)
class Execution:
    id: str | None = None
    number: int | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class Order:
    id: str | None = None
    depot_id: str | None = None
    instrument_id: str | None = None
    instrument_name: str | None = None
    isin: str | None = None
    wkn: str | None = None
    side: str | None = None
    type: str | None = None
    status: str | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    open_quantity: Decimal | None = None
    executed_quantity: Decimal | None = None
    cancelled_quantity: Decimal | None = None
    limit: Decimal | None = None
    limit_currency: str | None = None
    trigger_limit: Decimal | None = None
    trigger_limit_currency: str | None = None
    trailing_limit_distance: Decimal | None = None
    trailing_limit_distance_currency: str | None = None
    trailing_limit_percent: Decimal | None = None
    expected_value: Decimal | None = None
    expected_value_currency: str | None = None
    venue_id: str | None = None
    created_at: str | None = None
    validity_type: str | None = None
    validity: date | None = None
    best_execution: bool | None = None
    leg_number: int | None = None
    settlement_account_id: str | None = None
    limit_extension: str | None = None
    trading_restriction: str | None = None
    executions: tuple[Execution, ...] | None = None
    sub_orders: tuple[Order, ...] | None = None
