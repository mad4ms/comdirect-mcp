from datetime import date
from decimal import Decimal

from .models import (
    Account,
    AccountHolder,
    Depot,
    DepotBalance,
    DepotPosition,
    Document,
    Transaction,
)


def _get_val(obj, attr_name, key_name=None):
    """Helper to get attribute or dict key."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key_name or attr_name)
    return getattr(obj, attr_name, None)


def _to_decimal(amount_value) -> Decimal | None:
    """Helper to convert AmountValue (obj or dict) to Decimal; None if the value is missing."""
    val = _get_val(amount_value, "value")
    return Decimal(val) if val not in (None, "") else None


def _to_unit(amount_value) -> str:
    """Helper to get unit from AmountValue (obj or dict) safely."""
    return _get_val(amount_value, "unit") or ""


def _to_date(date_str) -> date | None:
    """Helper to convert date ISO string (YYYY-MM-DD) to date object; None if missing (e.g. unbooked)."""
    if not date_str:
        return None
    return date.fromisoformat(date_str)


def map_account(balance):
    return Account(
        id=balance.account_id,
        currency=balance.balance.unit,
        balance=Decimal(balance.balance.value),
        available=(Decimal(balance.available_cash_amount.value) if balance.available_cash_amount else None),
    )


def map_account_holder(info):
    if not info:
        return None
    return AccountHolder(
        holder_name=info.holder_name,
        iban=info.iban,
        bic=info.bic,
    )


def map_transaction(tx, account_id):
    return Transaction(
        account_id=account_id,
        booking_date=_to_date(tx.booking_date),
        amount=Decimal(tx.amount.value),
        currency=tx.amount.unit,
        purpose=tx.remittance_info,
        type=tx.transaction_type.key if tx.transaction_type else None,
        reference=tx.reference,
        booking_status=tx.booking_status,
        valuta_date=tx.valuta_date or None,
        direct_debit_creditor_id=tx.direct_debit_creditor_id,
        direct_debit_mandate_id=tx.direct_debit_mandate_id,
        end_to_end_reference=tx.end_to_end_reference,
        new_transaction=(tx.new_transaction if tx.new_transaction is not None else False),
        remitter=map_account_holder(tx.remitter),
        debtor=map_account_holder(tx.deptor),  # API field is 'deptor', not 'debtor' lol
        creditor=map_account_holder(tx.creditor),
    )


def map_depot(depot):
    return Depot(
        id=depot.depot_id,
        display_id=depot.depot_display_id,
        client_id=depot.client_id,
    )


def map_depot_position(pos):
    return DepotPosition(
        depot_id=pos.depot_id,
        position_id=pos.position_id,
        wkn=pos.wkn,
        quantity=_to_decimal(pos.quantity),
        quantity_unit=_to_unit(pos.quantity),
        current_value=_to_decimal(pos.current_value),
        current_value_currency=_to_unit(pos.current_value),
        purchase_value=_to_decimal(pos.purchase_value),
        purchase_value_currency=_to_unit(pos.purchase_value),
        profit_loss_purchase_abs=_to_decimal(pos.profit_loss_purchase_abs),
        profit_loss_purchase_rel=pos.profit_loss_purchase_rel,
        profit_loss_prev_day_abs=_to_decimal(pos.profit_loss_prev_day_abs),
        profit_loss_prev_day_rel=pos.profit_loss_prev_day_rel,
        instrument_name=pos.instrument.name if pos.instrument else None,
        isin=pos.instrument.isin if pos.instrument else None,
    )


def map_depot_balance(agg, depot_id: str):
    # agg is a dict (from API 'aggregated' field), not a model. The API nests the depot
    # ({"depot": {"depotId": ...}}) instead of setting the top-level depotId.
    agg = agg or {}
    return DepotBalance(
        depot_id=agg.get("depotId") or (agg.get("depot") or {}).get("depotId") or depot_id,
        date_last_update=agg.get("dateLastUpdate"),
        current_value=_to_decimal(agg.get("currentValue")),
        current_value_currency=_to_unit(agg.get("currentValue")),
        purchase_value=_to_decimal(agg.get("purchaseValue")),
        purchase_value_currency=_to_unit(agg.get("purchaseValue")),
        prev_day_value=_to_decimal(agg.get("prevDayValue")),
        prev_day_value_currency=_to_unit(agg.get("prevDayValue")),
        profit_loss_purchase_abs=_to_decimal(agg.get("profitLossPurchaseAbs")),
        profit_loss_purchase_rel=agg.get("profitLossPurchaseRel"),
        profit_loss_prev_day_abs=_to_decimal(agg.get("profitLossPrevDayAbs")),
        profit_loss_prev_day_rel=agg.get("profitLossPrevDayRel"),
    )


def map_document(doc):
    return Document(
        id=doc.document_id,
        name=doc.name,
        date_creation=doc.date_creation,
        mime_type=doc.mime_type,
        advertisement=(doc.advertisement if doc.advertisement is not None else False),
        already_read=doc.document_meta_data.already_read if doc.document_meta_data else None,
    )
