"""
Agent-facing views of the domain models for the MCP tools.

Tool results go into the model's context, so they are compact: null fields are omitted, rarely needed
references only appear in the verbose view, and aggregation happens here instead of in the model. Privacy
masking (IBANs, account numbers, optionally names) is applied when the views are built.
"""

import dataclasses
import hashlib
import hmac
import os
import secrets
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from .categories import CategoryRule, categorize
from .domain.models import (
    Account,
    AccountHolder,
    Card,
    Depot,
    DepotBalance,
    DepotPosition,
    DepotTransaction,
    Document,
    Instrument,
    Order,
    OrderDimensions,
    Transaction,
    WealthOverview,
)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


# Counterparty IBANs and own account numbers are masked unless explicitly disabled.
MASK_IBANS = not _env_flag("COMDIRECT_MCP_UNMASK_IBANS")
# Opt-in: replace counterparty names with stable pseudonyms (payment texts may still contain names).
MASK_NAMES = _env_flag("COMDIRECT_MCP_MASK_NAMES")

# Per process: pseudonyms are stable within a session but cannot be linked across sessions or reversed.
_PSEUDONYM_KEY = secrets.token_bytes(16)


def _is_none(value: Any) -> bool:
    return value is None


def optional(description: str | None = None) -> Any:
    """An optional field that is left out of the serialized result when it is null."""
    return Field(default=None, exclude_if=_is_none, description=description)


def mask_iban(iban: str | None) -> str | None:
    if not iban or not MASK_IBANS or len(iban) < 8:
        return iban
    return f"{iban[:2]}**...{iban[-4:]}"


def mask_number(number: str | None) -> str | None:
    if not number or not MASK_IBANS or len(number) <= 4:
        return number
    return f"...{number[-4:]}"


def counterparty_name(holder: AccountHolder | None) -> str | None:
    name = (holder.holder_name.strip() or None) if holder and holder.holder_name else None
    if not name or not MASK_NAMES:
        return name
    digest = hmac.new(_PSEUDONYM_KEY, name.casefold().encode(), hashlib.sha256).hexdigest()
    return f"Counterparty {digest[:6]}"


# --------- Accounts ---------


class AccountView(BaseModel):
    id: str | None = optional()
    type: str | None = optional("accountType key, e.g. CA = checking, DAS = Tagesgeld PLUS, SA = settlement")
    type_name: str | None = optional("e.g. Girokonto, Tagesgeld PLUS-Konto")
    number: str | None = optional("account number (masked)")
    iban: str | None = optional("IBAN (masked)")
    currency: str | None = optional()
    balance: Decimal | None = optional()
    available: Decimal | None = optional("balance plus credit line minus pending amounts")
    credit_limit: Decimal | None = optional()


def account_view(account: Account) -> AccountView:
    return AccountView(
        id=account.id,
        type=account.type,
        type_name=account.type_name,
        number=mask_number(account.display_id),
        iban=mask_iban(account.iban),
        currency=account.currency,
        balance=account.balance,
        available=account.available,
        credit_limit=account.credit_limit,
    )


# --------- Transactions ---------


class TransactionView(BaseModel):
    booking_date: date | None = optional("null for pending transactions")
    amount: Decimal | None = optional("negative = money out")
    currency: str | None = optional()
    direction: Literal["in", "out"] | None = optional()
    counterparty: str | None = optional("the other party (sender, recipient or collecting company)")
    purpose: str | None = optional("payment reference, cleaned up")
    type: str | None = optional("e.g. TRANSFER, DIRECT_DEBIT, CARD_TRANSACTION, SECURITIES")
    pending: bool | None = optional("true for not yet booked transactions")
    # verbose only
    valuta_date: str | None = optional("raw YYYY-MM-DD, may be a non-existent date")
    counterparty_iban: str | None = optional()
    reference: str | None = optional()
    end_to_end_reference: str | None = optional()
    direct_debit_creditor_id: str | None = optional()
    direct_debit_mandate_id: str | None = optional()
    new_transaction: bool | None = optional("not yet seen in the online banking")


def transaction_view(tx: Transaction, verbose: bool = False) -> TransactionView:
    view = TransactionView(
        booking_date=tx.booking_date,
        amount=tx.amount,
        currency=tx.currency,
        direction=tx.direction if tx.direction in ("in", "out") else None,  # type: ignore[arg-type]
        counterparty=counterparty_name(tx.counterparty),
        purpose=tx.purpose,
        type=tx.type,
        pending=True if tx.booking_status == "NOTBOOKED" else None,
    )
    if verbose:
        view = view.model_copy(
            update={
                "valuta_date": tx.valuta_date,
                "counterparty_iban": mask_iban(tx.counterparty.iban) if tx.counterparty else None,
                "reference": tx.reference,
                "end_to_end_reference": tx.end_to_end_reference,
                "direct_debit_creditor_id": tx.direct_debit_creditor_id,
                "direct_debit_mandate_id": tx.direct_debit_mandate_id,
                "new_transaction": tx.new_transaction,
            }
        )
    return view


# --------- Summaries ---------

GroupBy = Literal["month", "counterparty", "type", "category"]


class SummaryGroup(BaseModel):
    key: str = Field(description="YYYY-MM, counterparty name, transaction type or category")
    income: Decimal
    expenses: Decimal = Field(description="sum of outgoing amounts (negative)")
    net: Decimal
    count: int


class TransactionSummary(BaseModel):
    account_id: str
    currency: str | None = optional()
    min_booking_date: date | None = optional()
    max_booking_date: date | None = optional()
    group_by: GroupBy
    count: int
    income: Decimal
    expenses: Decimal
    net: Decimal
    groups: list[SummaryGroup]
    groups_truncated: bool = Field(description="True if smaller groups were merged into '(other)'")
    transactions_truncated: bool = Field(description="True if not all transactions in the range were summarized")


def _group_key(tx: Transaction, group_by: GroupBy, categories: Sequence[CategoryRule]) -> str:
    if group_by == "category":
        return categorize(tx, categories)
    if group_by == "month":
        return tx.booking_date.strftime("%Y-%m") if tx.booking_date else "(pending)"
    if group_by == "type":
        return tx.type or "(unknown)"
    return counterparty_name(tx.counterparty) or "(unknown)"


def _group(key: str, amounts: list[Decimal]) -> SummaryGroup:
    income = sum((a for a in amounts if a > 0), Decimal(0))
    expenses = sum((a for a in amounts if a < 0), Decimal(0))
    return SummaryGroup(key=key, income=income, expenses=expenses, net=income + expenses, count=len(amounts))


def summarize(
    account_id: str,
    transactions: Iterable[Transaction],
    group_by: GroupBy,
    max_groups: int,
    min_booking_date: date | None = None,
    max_booking_date: date | None = None,
    transactions_truncated: bool = False,
    categories: Sequence[CategoryRule] = (),
) -> TransactionSummary:
    """
    Sums incoming and outgoing amounts per group. Raises ValueError for mixed currencies.
    `categories` are the rules for group_by="category"; they see unmasked counterparty names.
    """
    amounts_by_key: dict[str, list[Decimal]] = defaultdict(list)
    currencies = set()
    for tx in transactions:
        if tx.amount is None or not tx.currency:
            raise ValueError("A transaction is missing its amount or currency; totals cannot be calculated.")
        currencies.add(tx.currency)
        amounts_by_key[_group_key(tx, group_by, categories)].append(tx.amount)
    if len(currencies) > 1:
        raise ValueError(f"The account has transactions in several currencies ({', '.join(sorted(currencies))}).")

    groups = [_group(key, amounts) for key, amounts in amounts_by_key.items()]
    if group_by == "month":
        groups.sort(key=lambda g: g.key)
    else:
        groups.sort(key=lambda g: (g.income - g.expenses, g.count), reverse=True)
    groups_truncated = len(groups) > max_groups
    if groups_truncated:
        rest = [amount for g in groups[max_groups - 1 :] for amount in amounts_by_key[g.key]]
        groups = [*groups[: max_groups - 1], _group("(other)", rest)]

    all_amounts = [amount for amounts in amounts_by_key.values() for amount in amounts]
    total = _group("total", all_amounts)
    return TransactionSummary(
        account_id=account_id,
        currency=next(iter(currencies), None),
        min_booking_date=min_booking_date,
        max_booking_date=max_booking_date,
        group_by=group_by,
        count=total.count,
        income=total.income,
        expenses=total.expenses,
        net=total.net,
        groups=groups,
        groups_truncated=groups_truncated,
        transactions_truncated=transactions_truncated,
    )


# --------- Cards ---------


class CardView(BaseModel):
    type: str | None = optional("cardType key, e.g. VISA_PREPAID")
    type_name: str | None = optional()
    number_suffix: str | None = optional("last digits of the card number")
    status: str | None = optional()
    balance: Decimal | None = optional()
    available: Decimal | None = optional()
    limit: Decimal | None = optional()
    currency: str | None = optional()


def card_view(card: Card) -> CardView:
    return CardView(
        type=card.type,
        type_name=card.type_name,
        number_suffix=card.number_suffix,
        status=card.status,
        balance=card.balance,
        available=card.available,
        limit=card.limit,
        currency=card.currency,
    )


class DepotView(BaseModel):
    id: str | None = optional()
    display_id: str | None = optional()
    client_id: str | None = optional()


def depot_view(value: Depot) -> DepotView:
    data = dataclasses.asdict(value)
    data["display_id"] = mask_number(value.display_id)
    return DepotView(**data)


class DepotBalanceView(BaseModel):
    depot_id: str | None = optional()
    date_last_update: str | None = optional()
    current_value: Decimal | None = optional()
    current_value_currency: str | None = optional()
    purchase_value: Decimal | None = optional()
    purchase_value_currency: str | None = optional()
    prev_day_value: Decimal | None = optional()
    prev_day_value_currency: str | None = optional()
    profit_loss_purchase_abs: Decimal | None = optional()
    profit_loss_purchase_rel: str | None = optional()
    profit_loss_prev_day_abs: Decimal | None = optional()
    profit_loss_prev_day_rel: str | None = optional()


def depot_balance_view(value: DepotBalance) -> DepotBalanceView:
    data = dataclasses.asdict(value)
    return DepotBalanceView(**data)


class DepotPositionView(BaseModel):
    depot_id: str | None = optional()
    position_id: str | None = optional()
    wkn: str | None = optional()
    quantity: Decimal | None = optional()
    quantity_unit: str | None = optional()
    current_value: Decimal | None = optional()
    current_value_currency: str | None = optional()
    purchase_value: Decimal | None = optional()
    purchase_value_currency: str | None = optional()
    profit_loss_purchase_abs: Decimal | None = optional()
    profit_loss_purchase_rel: str | None = optional()
    profit_loss_prev_day_abs: Decimal | None = optional()
    profit_loss_prev_day_rel: str | None = optional()
    instrument_name: str | None = optional()
    isin: str | None = optional()


def depot_position_view(value: DepotPosition, verbose: bool = False) -> DepotPositionView:
    data = dataclasses.asdict(value)
    if not verbose:
        for field in (
            "depot_id",
            "position_id",
            "purchase_value",
            "purchase_value_currency",
            "profit_loss_purchase_abs",
            "profit_loss_purchase_rel",
            "profit_loss_prev_day_abs",
            "profit_loss_prev_day_rel",
        ):
            data.pop(field)
    return DepotPositionView(**data)


class DocumentView(BaseModel):
    document_id: str | None = optional()
    name: str | None = optional()
    date: str | None = optional()
    mime_type: str | None = optional()
    advertisement: bool | None = optional()
    already_read: bool | None = optional()


def document_view(value: Document) -> DocumentView:
    data = dataclasses.asdict(value)
    data["document_id"] = data.pop("id")
    data["date"] = data.pop("date_creation")
    return DocumentView(**data)


class DepotTransactionView(BaseModel):
    booking_date: date | None = optional()
    booking_status: str | None = optional()
    instrument_name: str | None = optional()
    isin: str | None = optional()
    wkn: str | None = optional()
    quantity: Decimal | None = optional()
    quantity_unit: str | None = optional()
    transaction_value: Decimal | None = optional()
    transaction_value_currency: str | None = optional()
    direction: str | None = optional()
    type: str | None = optional()
    transaction_id: str | None = optional()
    instrument_id: str | None = optional()
    business_date: date | None = optional()
    settlement_date: str | None = optional()
    execution_price: Decimal | None = optional()
    execution_price_currency: str | None = optional()


def depot_transaction_view(value: DepotTransaction, verbose: bool = False) -> DepotTransactionView:
    data = dataclasses.asdict(value)
    data.pop("depot_id")
    if not verbose:
        for field in (
            "transaction_id",
            "instrument_id",
            "business_date",
            "settlement_date",
            "execution_price",
            "execution_price_currency",
        ):
            data.pop(field)
    return DepotTransactionView(**data)


class FundDetailsView(BaseModel):
    status: str | None = optional()
    flags: tuple[str, ...] | None = optional()
    currency: str | None = optional()
    investment_category: str | None = optional()
    total_expense_ratio: Decimal | None = optional()
    regular_issue_surcharge: Decimal | None = optional()
    discount_issue_surcharge: Decimal | None = optional()
    reduced_issue_surcharge: Decimal | None = optional()
    individual_issue_surcharge: Decimal | None = optional()
    individual_issue_surcharge_corrected: bool | None = optional()
    bonification: Decimal | None = optional()
    morningstar_rating: str | None = optional()
    moodys_rating: str | None = optional()


class PriceSnapshotView(BaseModel):
    type: str | None = optional()
    price: Decimal | None = optional()
    currency: str | None = optional()
    quantity: Decimal | None = optional()
    quantity_unit: str | None = optional()
    timestamp: str | None = optional("Bank-supplied snapshot timestamp; not a live price feed.")


class OrderTypeView(BaseModel):
    limit_extensions: tuple[str, ...] | None = optional()
    trading_restrictions: tuple[str, ...] | None = optional()


class VenueView(BaseModel):
    id: str | None = optional()
    name: str | None = optional()
    country: str | None = optional()
    type: str | None = optional()
    currencies: tuple[str, ...] | None = optional()
    sides: tuple[str, ...] | None = optional()
    validity_types: tuple[str, ...] | None = optional()
    order_types: dict[str, OrderTypeView] | None = optional()


class OrderDimensionsView(BaseModel):
    count: int | None = optional("Unknown if the bank omitted venues.")
    venues: list[VenueView] | None = optional()


def dimensions_view(value: OrderDimensions) -> OrderDimensionsView:
    if value.venues is None:
        return OrderDimensionsView()
    venues = []
    for venue in value.venues:
        data = dataclasses.asdict(venue)
        data["order_types"] = (
            {key: OrderTypeView(**dataclasses.asdict(details)) for key, details in venue.order_types}
            if venue.order_types is not None
            else None
        )
        venues.append(VenueView(**data))
    return OrderDimensionsView(count=len(venues), venues=venues)


class DerivativeDetailsView(BaseModel):
    underlying_name: str | None = optional()
    underlying_isin: str | None = optional()
    underlying_wkn: str | None = optional()
    certificate_type: str | None = optional()
    warrant_type: str | None = optional()
    strike_price: Decimal | None = optional()
    strike_price_currency: str | None = optional()
    leverage: Decimal | None = optional()
    multiplier: Decimal | None = optional()
    expiry_date: date | None = optional()
    maturity_date: date | None = optional()
    yield_pa: Decimal | None = optional()
    remaining_term_in_years: Decimal | None = optional()
    nominal_rate: Decimal | None = optional()
    interest_payment_date: date | None = optional()
    interest_payment_interval: str | None = optional()
    morningstar_rating: str | None = optional()
    moodys_rating: str | None = optional()
    underlying_price: PriceSnapshotView | None = optional()


class InstrumentView(BaseModel):
    id: str | None = optional()
    name: str | None = optional()
    isin: str | None = optional()
    wkn: str | None = optional()
    type: str | None = optional()
    currency: str | None = optional()
    short_name: str | None = optional()
    mnemonic: str | None = optional()
    notation: str | None = optional()
    priips_relevant: bool | None = optional()
    kid_available: bool | None = optional()
    shipping_waiver_required: bool | None = optional()
    fund_redemption_limited: bool | None = optional()
    fund: FundDetailsView | None = optional()
    derivative: DerivativeDetailsView | None = optional()
    order_dimensions: OrderDimensionsView | None = optional()


def instrument_view(value: Instrument, verbose: bool = False) -> InstrumentView:
    data = dataclasses.asdict(value)
    data["order_dimensions"] = dimensions_view(value.order_dimensions) if value.order_dimensions is not None else None
    if not verbose:
        for field in (
            "short_name",
            "mnemonic",
            "notation",
            "priips_relevant",
            "kid_available",
            "shipping_waiver_required",
            "fund_redemption_limited",
            "fund",
            "derivative",
        ):
            data.pop(field)
    return InstrumentView(**data)


class ExecutionView(BaseModel):
    id: str | None = optional()
    number: int | None = optional()
    quantity: Decimal | None = optional()
    quantity_unit: str | None = optional()
    price: Decimal | None = optional()
    currency: str | None = optional()
    timestamp: str | None = optional()


class OrderView(BaseModel):
    id: str | None = optional()
    depot_id: str | None = optional()
    instrument_id: str | None = optional()
    instrument_name: str | None = optional()
    isin: str | None = optional()
    wkn: str | None = optional()
    side: str | None = optional()
    type: str | None = optional()
    status: str | None = optional()
    quantity: Decimal | None = optional()
    quantity_unit: str | None = optional()
    open_quantity: Decimal | None = optional()
    executed_quantity: Decimal | None = optional()
    cancelled_quantity: Decimal | None = optional()
    limit: Decimal | None = optional()
    limit_currency: str | None = optional()
    trigger_limit: Decimal | None = optional()
    trigger_limit_currency: str | None = optional()
    trailing_limit_distance: Decimal | None = optional()
    trailing_limit_distance_currency: str | None = optional()
    trailing_limit_percent: Decimal | None = optional()
    expected_value: Decimal | None = optional()
    expected_value_currency: str | None = optional()
    venue_id: str | None = optional()
    created_at: str | None = optional()
    validity_type: str | None = optional()
    validity: date | None = optional()
    best_execution: bool | None = optional()
    leg_number: int | None = optional()
    settlement_account_id: str | None = optional()
    limit_extension: str | None = optional()
    trading_restriction: str | None = optional()
    executions: list[ExecutionView] | None = optional()
    sub_orders: list["OrderView"] | None = optional()


def order_view(value: Order, verbose: bool = False) -> OrderView:
    data = dataclasses.asdict(value)
    if not verbose:
        for field in (
            "depot_id",
            "cancelled_quantity",
            "trailing_limit_distance",
            "trailing_limit_distance_currency",
            "trailing_limit_percent",
            "expected_value",
            "expected_value_currency",
            "best_execution",
            "leg_number",
            "settlement_account_id",
            "limit_extension",
            "trading_restriction",
            "executions",
        ):
            data.pop(field)
    data["sub_orders"] = (
        [order_view(order, verbose) for order in value.sub_orders] if value.sub_orders is not None else None
    )
    return OrderView(**data)


class PortfolioPositionView(BaseModel):
    name: str | None = optional()
    isin: str | None = optional()
    wkn: str | None = optional()
    value: Decimal
    weight_percent: Decimal | None = optional()


class PortfolioCurrencyView(BaseModel):
    currency: str
    total_value: Decimal
    count: int
    positions: list[PortfolioPositionView]
    omitted_count: int
    omitted_value: Decimal
    omitted_weight_percent: Decimal | None = optional()


class PortfolioSummary(BaseModel):
    depot_id: str
    count: int
    currencies: list[PortfolioCurrencyView]


def summarize_portfolio(depot_id: str, positions: list[DepotPosition], limit: int) -> PortfolioSummary:
    grouped: dict[str, list[tuple[DepotPosition, Decimal]]] = defaultdict(list)
    for position in positions:
        if position.current_value is None or not position.current_value_currency:
            raise ValueError("Portfolio contains missing values/currencies. Inspect `get_depot_positions` instead.")
        if not position.current_value.is_finite() or position.current_value < 0:
            raise ValueError(
                "Portfolio allocation requires finite, nonnegative values. Inspect `get_depot_positions`."
            )
        grouped[position.current_value_currency].append((position, position.current_value))
    currencies = []
    for currency, holdings in sorted(grouped.items()):
        ranked = sorted(holdings, key=lambda item: item[1], reverse=True)
        total = sum((value for _, value in ranked), Decimal(0))
        omitted = sum((value for _, value in ranked[limit:]), Decimal(0))
        currencies.append(
            PortfolioCurrencyView(
                currency=currency,
                total_value=total,
                count=len(ranked),
                positions=[
                    PortfolioPositionView(
                        name=p.instrument_name,
                        isin=p.isin,
                        wkn=p.wkn,
                        value=value,
                        weight_percent=value / total * 100 if total else None,
                    )
                    for p, value in ranked[:limit]
                ],
                omitted_count=max(0, len(ranked) - limit),
                omitted_value=omitted,
                omitted_weight_percent=omitted / total * 100 if total else None,
            )
        )
    return PortfolioSummary(depot_id=depot_id, count=len(positions), currencies=currencies)


class ProductBalanceView(BaseModel):
    id: str | None = optional()
    type: str | None = optional()
    type_name: str | None = optional()
    display_id: str | None = optional()
    balance: Decimal | None = optional()
    currency: str | None = optional()
    available: Decimal | None = optional()
    available_currency: str | None = optional()
    connection_type: str | None = optional()
    target_client_id: str | None = optional()


class WealthOverviewView(BaseModel):
    count: int
    total_balance_eur: Decimal | None = optional("Bank-supplied aggregate; product signs are not reinterpreted.")
    total_available_eur: Decimal | None = optional()
    reported_count: int | None = optional()
    products_complete: bool | None = optional("Whether the returned count matches the bank's reported count.")
    missing_value_count: int
    products: list[ProductBalanceView]


def wealth_overview_view(value: WealthOverview, verbose: bool = False) -> WealthOverviewView:
    products = []
    for product in value.products:
        data = dataclasses.asdict(product)
        data["display_id"] = mask_number(product.display_id)
        if not verbose:
            data.pop("target_client_id")
        products.append(ProductBalanceView(**data))
    return WealthOverviewView(
        count=len(products),
        total_balance_eur=value.total_balance_eur,
        total_available_eur=value.total_available_eur,
        reported_count=value.reported_count,
        products_complete=len(products) == value.reported_count if value.reported_count is not None else None,
        missing_value_count=sum(p.balance is None or p.currency is None for p in value.products),
        products=products,
    )
