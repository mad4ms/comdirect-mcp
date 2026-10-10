import re
from datetime import date
from decimal import Decimal

from .models import (
    Account,
    AccountHolder,
    Card,
    Depot,
    DepotBalance,
    DepotPosition,
    DepotTransaction,
    DerivativeDetails,
    Document,
    Execution,
    FundDetails,
    Instrument,
    Order,
    OrderDimensions,
    OrderTypeDetails,
    PriceSnapshot,
    ProductBalance,
    Transaction,
    Venue,
    WealthOverview,
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


def _to_unit(amount_value) -> str | None:
    """Helper to get unit from AmountValue (obj or dict) safely."""
    return _get_val(amount_value, "unit")


def _to_date(date_str) -> date | None:
    """Helper to convert date ISO string (YYYY-MM-DD) to date object; None if missing (e.g. unbooked)."""
    if not date_str:
        return None
    return date.fromisoformat(date_str)


# Line length of remittanceInfo; booked transactions prefix each line with a 2-digit number (API docs 4.2.3).
PURPOSE_LINE_LENGTH = 35

# Labels after which comdirect appends references that the API also returns in dedicated fields.
_REFERENCE_LABELS = re.compile(r"\s*\b(?:End-to-End-Ref\.?|Mandatsref\.?|Gl(?:ä|ae)ubiger-ID)\s*:", re.IGNORECASE)

# Special units of AmountValue (API docs 3.4.1); everything else is an ISO 4217 currency.
_UNITS = {"XXX": "pieces", "XXC": "percent", "XXM": "per mille", "XXP": "points", "XXU": "unknown"}


def _split_numbered_lines(text: str) -> list[str] | None:
    """Splits "01<35 chars>02<35 chars>..." into lines; None if the text does not follow this format exactly."""
    if not text.startswith("01"):
        return None
    step = 2 + PURPOSE_LINE_LENGTH
    lines = []
    for number, start in enumerate(range(0, len(text), step), start=1):
        if text[start : start + 2] != f"{number:02d}":
            return None
        lines.append(text[start + 2 : start + step])
    return lines


def normalize_purpose(raw: str | None, numbered: bool = True) -> str | None:
    """
    Makes the payment reference readable: removes the line numbers of booked transactions (`numbered`), joins the
    35-character lines - a full line continues the word on the next line, e.g. "Gmb" + "H" - and drops the trailing
    reference block (end-to-end reference, mandate reference, creditor id), which the API returns in dedicated
    fields as well. Text that does not follow the numbered format is only trimmed.
    """
    if not raw:
        return None
    lines = _split_numbered_lines(raw) if numbered else None
    if lines is None:
        text = raw
    else:
        text = "".join(
            line if len(line) == PURPOSE_LINE_LENGTH and not line.endswith(" ") else line.rstrip() + " "
            for line in lines
        )
    reference = _REFERENCE_LABELS.search(text)
    if reference and reference.start() > 0:
        text = text[: reference.start()]
    text = " ".join(text.split())
    return text or None


def _unit_name(amount_value) -> str | None:
    unit = _to_unit(amount_value)
    return _UNITS.get(unit, unit) if unit is not None else None


def _counterparty(amount: Decimal | None, remitter, debtor, creditor):
    """
    The other party of a transaction. comdirect fills the roles by SEPA semantics: for an outgoing transfer the
    recipient is the creditor, for a direct debit the collecting company is the remitter (Auftraggeber); for
    incoming money the sender is the remitter.
    """
    if amount is None:
        return None
    roles = (creditor, remitter, debtor) if amount < 0 else (remitter, debtor, creditor)
    return next((holder for holder in roles if holder and (holder.holder_name or holder.iban or holder.bic)), None)


def map_account(balance):
    account = _get_val(balance, "account")
    account_type = _get_val(account, "account_type", "accountType")
    credit_limit = _get_val(account, "credit_limit", "creditLimit")
    amount = _get_val(balance, "balance")
    return Account(
        id=_get_val(balance, "account_id", "accountId"),
        currency=_to_unit(amount),
        balance=_to_decimal(amount),
        available=_to_decimal(_get_val(balance, "available_cash_amount", "availableCashAmount")),
        type=_get_val(account_type, "key"),
        type_name=_get_val(account_type, "text"),
        display_id=_get_val(account, "account_display_id", "accountDisplayId"),
        iban=_get_val(account, "iban"),
        credit_limit=_to_decimal(credit_limit),
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
    amount = _to_decimal(tx.amount)
    remitter = map_account_holder(tx.remitter)
    debtor = map_account_holder(tx.deptor)  # API field is 'deptor', not 'debtor'
    creditor = map_account_holder(tx.creditor)
    return Transaction(
        account_id=account_id,
        booking_date=_to_date(tx.booking_date),
        amount=amount,
        currency=_to_unit(tx.amount),
        # Only booked transactions carry line numbers (API docs 4.2.3)
        purpose=normalize_purpose(tx.remittance_info, numbered=tx.booking_status != "NOTBOOKED"),
        type=tx.transaction_type.key if tx.transaction_type else None,
        reference=tx.reference,
        booking_status=tx.booking_status,
        valuta_date=tx.valuta_date or None,
        direct_debit_creditor_id=tx.direct_debit_creditor_id,
        direct_debit_mandate_id=tx.direct_debit_mandate_id,
        end_to_end_reference=tx.end_to_end_reference,
        new_transaction=tx.new_transaction,
        remitter=remitter,
        debtor=debtor,
        creditor=creditor,
        counterparty=_counterparty(amount, remitter, debtor, creditor),
        direction=("in" if amount > 0 else "out" if amount < 0 else None) if amount is not None else None,
        purpose_raw=tx.remittance_info,
    )


def map_depot(depot):
    return Depot(
        id=depot.depot_id,
        display_id=depot.depot_display_id,
        client_id=depot.client_id,
    )


def map_depot_position(pos):
    instrument = _get_val(pos, "instrument")
    return DepotPosition(
        depot_id=_get_val(pos, "depot_id", "depotId"),
        position_id=_get_val(pos, "position_id", "positionId"),
        wkn=_get_val(pos, "wkn"),
        quantity=_to_decimal(_get_val(pos, "quantity")),
        quantity_unit=_unit_name(_get_val(pos, "quantity")),
        current_value=_to_decimal(_get_val(pos, "current_value", "currentValue")),
        current_value_currency=_to_unit(_get_val(pos, "current_value", "currentValue")),
        purchase_value=_to_decimal(_get_val(pos, "purchase_value", "purchaseValue")),
        purchase_value_currency=_to_unit(_get_val(pos, "purchase_value", "purchaseValue")),
        profit_loss_purchase_abs=_to_decimal(_get_val(pos, "profit_loss_purchase_abs", "profitLossPurchaseAbs")),
        profit_loss_purchase_rel=_get_val(pos, "profit_loss_purchase_rel", "profitLossPurchaseRel"),
        profit_loss_prev_day_abs=_to_decimal(_get_val(pos, "profit_loss_prev_day_abs", "profitLossPrevDayAbs")),
        profit_loss_prev_day_rel=_get_val(pos, "profit_loss_prev_day_rel", "profitLossPrevDayRel"),
        instrument_name=_get_val(instrument, "name"),
        isin=_get_val(instrument, "isin"),
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
        advertisement=doc.advertisement,
        already_read=doc.document_meta_data.already_read if doc.document_meta_data else None,
    )


def map_card(product: dict) -> Card:
    """Maps a CARD entry of /reports/participants/user/v1/allbalances (plain JSON, see client.list_cards)."""
    balance = product.get("balance") or {}
    card = balance.get("card") or {}
    card_type = card.get("cardType") or {}
    return Card(
        id=balance.get("cardId") or card.get("cardId") or product.get("productId"),
        type=card_type.get("key"),
        type_name=card_type.get("text"),
        number_suffix=card.get("primaryAccountNumberSuffix"),
        status=card.get("status"),
        balance=_to_decimal(balance.get("balance")),
        available=_to_decimal(balance.get("availableCashAmount")),
        limit=_to_decimal(card.get("cardLimit")),
        currency=_to_unit(balance.get("balance")) or None,
    )


def map_depot_transaction(tx: dict, depot_id: str) -> DepotTransaction:
    instrument = tx.get("instrument") or {}
    return DepotTransaction(
        depot_id=depot_id,
        transaction_id=tx.get("transactionId"),
        booking_status=tx.get("bookingStatus"),
        booking_date=_to_date(tx.get("bookingDate")),
        business_date=_to_date(tx.get("businessDate")),
        settlement_date=tx.get("settlementDate"),
        instrument_id=tx.get("instrumentId"),
        instrument_name=instrument.get("name"),
        isin=instrument.get("isin"),
        wkn=instrument.get("wkn"),
        quantity=_to_decimal(tx.get("quantity")),
        quantity_unit=_unit_name(tx.get("quantity")),
        execution_price=_to_decimal(tx.get("executionPrice")),
        execution_price_currency=_to_unit(tx.get("executionPrice")),
        transaction_value=_to_decimal(tx.get("transactionValue")),
        transaction_value_currency=_to_unit(tx.get("transactionValue")),
        direction=tx.get("transactionDirection"),
        type=_get_val(tx.get("transactionType"), "key")
        if isinstance(tx.get("transactionType"), dict)
        else tx.get("transactionType"),
    )


def _decimal_string(value) -> Decimal | None:
    return Decimal(value) if value not in (None, "") else None


def map_instrument(value: dict) -> Instrument:
    static = value.get("staticData") or {}
    fund = value.get("fundsDistribution")
    derivative = value.get("derivativeData")
    fund_details = None
    if fund is not None:
        rating = fund.get("rating") or {}
        fund_details = FundDetails(
            status=fund.get("fundStatus"),
            flags=tuple(fund["fundFlags"]) if fund.get("fundFlags") is not None else None,
            currency=fund.get("currency"),
            investment_category=fund.get("investmentCategory"),
            total_expense_ratio=_decimal_string(fund.get("totalExpenseRatio")),
            regular_issue_surcharge=_decimal_string(fund.get("regularIssueSurcharge")),
            discount_issue_surcharge=_decimal_string(fund.get("discountIssueSurcharge")),
            reduced_issue_surcharge=_decimal_string(fund.get("reducedIssueSurcharge")),
            individual_issue_surcharge=_decimal_string(fund.get("individualIssueSurcharge")),
            individual_issue_surcharge_corrected=fund.get("isIndividualIssueSurchargeCorrected"),
            bonification=_decimal_string(fund.get("bonification")),
            morningstar_rating=rating.get("morningstar"),
            moodys_rating=rating.get("moodys"),
        )
    derivative_details = None
    if derivative is not None:
        underlying = derivative.get("underlyingInstrument") or {}
        rating = derivative.get("rating") or {}
        derivative_details = DerivativeDetails(
            underlying_name=underlying.get("name"),
            underlying_isin=underlying.get("isin"),
            underlying_wkn=underlying.get("wkn"),
            certificate_type=derivative.get("certificateType"),
            warrant_type=derivative.get("warrantType"),
            strike_price=_to_decimal(derivative.get("strikePrice")),
            strike_price_currency=_to_unit(derivative.get("strikePrice")),
            leverage=_decimal_string(derivative.get("leverage")),
            multiplier=_decimal_string(derivative.get("multiplier")),
            expiry_date=_to_date(derivative.get("expiryDate")),
            maturity_date=_to_date(derivative.get("maturityDate")),
            yield_pa=_decimal_string(derivative.get("yieldPA")),
            remaining_term_in_years=_decimal_string(derivative.get("remainingTermInYears")),
            nominal_rate=_decimal_string(derivative.get("nominalRate")),
            interest_payment_date=_to_date(derivative.get("interestPaymentDate")),
            interest_payment_interval=derivative.get("interestPaymentInterval"),
            morningstar_rating=rating.get("morningstar"),
            moodys_rating=rating.get("moodys"),
            underlying_price=map_price(derivative["underlyingPrice"]) if derivative.get("underlyingPrice") else None,
        )
    return Instrument(
        id=value.get("instrumentId"),
        name=value.get("name"),
        short_name=value.get("shortName"),
        isin=value.get("isin"),
        wkn=value.get("wkn"),
        mnemonic=value.get("mnemonic"),
        type=static.get("instrumentType"),
        currency=static.get("currency"),
        notation=_UNITS.get(static.get("notation") or "", static.get("notation")),
        priips_relevant=static.get("priipsRelevant"),
        kid_available=static.get("kidAvailable"),
        shipping_waiver_required=static.get("shippingWaiverRequired"),
        fund_redemption_limited=static.get("fundRedemptionLimited"),
        fund=fund_details,
        derivative=derivative_details,
        order_dimensions=map_dimensions(value["orderDimensions"])
        if value.get("orderDimensions") is not None
        else None,
    )


def map_price(value: dict) -> PriceSnapshot:
    return PriceSnapshot(
        type=value.get("type"),
        price=_to_decimal(value.get("price")),
        currency=_to_unit(value.get("price")),
        quantity=_to_decimal(value.get("quantity")),
        quantity_unit=_unit_name(value.get("quantity")),
        timestamp=value.get("priceDateTime"),
    )


def map_dimensions(value: dict) -> OrderDimensions:
    venues = None
    if value.get("venues") is not None:
        venues = tuple(
            Venue(
                id=v.get("venueId"),
                name=v.get("name"),
                country=v.get("country"),
                type=v.get("type"),
                currencies=tuple(v["currencies"]) if v.get("currencies") is not None else None,
                sides=tuple(v["sides"]) if v.get("sides") is not None else None,
                validity_types=tuple(v["validityTypes"]) if v.get("validityTypes") is not None else None,
                order_types=tuple(
                    (
                        name,
                        OrderTypeDetails(
                            limit_extensions=tuple(details["limitExtensions"])
                            if details.get("limitExtensions") is not None
                            else None,
                            trading_restrictions=tuple(details["tradingRestrictions"])
                            if details.get("tradingRestrictions") is not None
                            else None,
                        ),
                    )
                    for name, details in (v.get("orderTypes") or {}).items()
                )
                if v.get("orderTypes") is not None
                else None,
            )
            for v in value["venues"]
        )
    return OrderDimensions(venues=venues)


def map_order(value: dict, depth: int = 0) -> Order:
    from ..exceptions import DataError

    if depth > 8:
        raise DataError("Order nesting exceeds the supported depth; request individual order details.")
    instrument = value.get("instrument") or {}
    return Order(
        id=value.get("orderId"),
        depot_id=value.get("depotId"),
        instrument_id=value.get("instrumentId"),
        instrument_name=instrument.get("name"),
        isin=instrument.get("isin"),
        wkn=instrument.get("wkn"),
        side=value.get("side"),
        type=value.get("orderType"),
        status=value.get("orderStatus"),
        quantity=_to_decimal(value.get("quantity")),
        quantity_unit=_unit_name(value.get("quantity")),
        open_quantity=_to_decimal(value.get("openQuantity")),
        executed_quantity=_to_decimal(value.get("executedQuantity")),
        cancelled_quantity=_to_decimal(value.get("cancelledQuantity")),
        limit=_to_decimal(value.get("limit")),
        limit_currency=_to_unit(value.get("limit")),
        trigger_limit=_to_decimal(value.get("triggerLimit")),
        trigger_limit_currency=_to_unit(value.get("triggerLimit")),
        trailing_limit_distance=_to_decimal(value.get("trailingLimitDistAbs")),
        trailing_limit_distance_currency=_to_unit(value.get("trailingLimitDistAbs")),
        trailing_limit_percent=_decimal_string(value.get("trailingLimitDistRel")),
        expected_value=_to_decimal(value.get("expectedValue")),
        expected_value_currency=_to_unit(value.get("expectedValue")),
        venue_id=value.get("venueId"),
        created_at=value.get("creationTimestamp"),
        validity_type=value.get("validityType"),
        validity=_to_date(value.get("validity")),
        best_execution=value.get("bestEx"),
        leg_number=value.get("legNumber"),
        settlement_account_id=value.get("settlementAccountId"),
        limit_extension=value.get("limitExtension"),
        trading_restriction=value.get("tradingRestriction"),
        executions=tuple(
            Execution(
                id=e.get("executionId"),
                number=e.get("executionNumber"),
                quantity=_to_decimal(e.get("executedQuantity")),
                quantity_unit=_unit_name(e.get("executedQuantity")),
                price=_to_decimal(e.get("executionPrice")),
                currency=_to_unit(e.get("executionPrice")),
                timestamp=e.get("executionTimestamp"),
            )
            for e in value["executions"]
        )
        if value.get("executions") is not None
        else None,
        sub_orders=tuple(map_order(o, depth + 1) for o in value["subOrders"])
        if value.get("subOrders") is not None
        else None,
    )


def map_product_balance(product: dict) -> ProductBalance:
    balance = product.get("balance") or {}
    kind = product.get("productType")
    fields: dict[str, tuple[str | None, str | None, str | None, str | None]] = {
        "ACCOUNT": ("account", "balance", "accountDisplayId", "accountType"),
        "CARD": ("card", "balance", "primaryAccountNumberSuffix", "cardType"),
        "DEPOT": ("depot", "currentValue", "depotDisplayId", None),
        "LOAN": ("installmentLoan", "balance", "productDisplayId", None),
        "SAVINGS": (None, "savingsAmount", "fixedTermSavingsDisplayName", "fixedTermSavingsType"),
    }
    static_key, amount_key, display_key, type_key = fields.get(kind or "", (None, None, None, None))
    static = balance.get(static_key) or {} if static_key else balance
    product_type = static.get(type_key) or {} if type_key else {}
    amount = balance.get(amount_key) if amount_key else None
    return ProductBalance(
        id=product.get("productId"),
        type=kind,
        type_name=product_type.get("text") if isinstance(product_type, dict) else product_type,
        display_id=static.get(display_key) if display_key and kind != "SAVINGS" else None,
        balance=_to_decimal(amount),
        currency=_to_unit(amount),
        available=_to_decimal(balance.get("availableCashAmount")),
        available_currency=_to_unit(balance.get("availableCashAmount")),
        connection_type=product.get("clientConnectionType"),
        target_client_id=product.get("targetClientId"),
    )


def map_wealth_overview(report: dict) -> WealthOverview:
    aggregated = report.get("aggregated") or {}
    balance = aggregated.get("balanceEUR")
    available = aggregated.get("availableCashAmountEUR")
    return WealthOverview(
        products=tuple(map_product_balance(p) for p in report.get("values") or []),
        total_balance_eur=_to_decimal(balance) if _to_unit(balance) == "EUR" else None,
        total_available_eur=_to_decimal(available) if _to_unit(available) == "EUR" else None,
        reported_count=(report.get("paging") or {}).get("matches"),
    )
