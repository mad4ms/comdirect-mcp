from datetime import date
from decimal import Decimal

import pytest

from comdirect_mcp import views
from comdirect_mcp.domain.models import Account, AccountHolder, Transaction


def _tx(amount, counterparty=None, booking=date(2026, 3, 5), tx_type="TRANSFER", currency="EUR"):
    holder = AccountHolder(holder_name=counterparty, iban=None, bic=None) if counterparty else None
    return Transaction(
        account_id="acc",
        booking_date=booking,
        amount=Decimal(amount),
        currency=currency,
        purpose=None,
        type=tx_type,
        counterparty=holder,
        direction="in" if Decimal(amount) > 0 else "out",
    )


def test_transaction_view_omits_null_fields():
    dumped = views.transaction_view(_tx("-1.50")).model_dump(mode="json")
    assert dumped == {
        "booking_date": "2026-03-05",
        "amount": "-1.50",
        "currency": "EUR",
        "direction": "out",
        "type": "TRANSFER",
    }


def test_pending_transactions_are_flagged():
    tx = Transaction("acc", None, Decimal("-1"), "EUR", None, None, booking_status="NOTBOOKED")
    assert views.transaction_view(tx).model_dump(mode="json")["pending"] is True


def test_account_view_masks_number_and_iban():
    account = Account("a", "EUR", Decimal("1"), None, "CA", "Girokonto", "1234567890", "DE89370400440532013000")
    view = views.account_view(account).model_dump(mode="json")
    assert view["number"] == "...7890"
    assert view["iban"] == "DE**...3000"
    assert view["type_name"] == "Girokonto"


def test_name_masking_is_opt_in_and_stable(monkeypatch):
    holder = AccountHolder(holder_name="Erika Mustermann", iban=None, bic=None)
    assert views.counterparty_name(holder) == "Erika Mustermann"

    monkeypatch.setattr(views, "MASK_NAMES", True)
    pseudonym = views.counterparty_name(holder)
    assert pseudonym.startswith("Counterparty ") and "Erika" not in pseudonym
    assert views.counterparty_name(AccountHolder("erika mustermann ", None, None)) == pseudonym
    assert views.counterparty_name(AccountHolder("Max Mustermann", None, None)) != pseudonym


def test_summarize_by_counterparty_sorts_by_volume_and_merges_the_rest():
    txs = [_tx("-10", "A"), _tx("-300", "B"), _tx("100", "C"), _tx("-5", "D"), _tx("-1", None)]

    summary = views.summarize(["acc"], txs, "counterparty", max_groups=3)

    assert [g.key for g in summary.groups] == ["B", "C", "(other)"]
    assert summary.groups[2].count == 3 and summary.groups[2].expenses == Decimal("-16")
    assert summary.groups_truncated is True
    assert (summary.income, summary.expenses, summary.net) == (Decimal("100"), Decimal("-316"), Decimal("-216"))


def test_summarize_by_type():
    summary = views.summarize(
        ["acc"], [_tx("-1", tx_type="DIRECT_DEBIT"), _tx("-2", tx_type="DIRECT_DEBIT")], "type", 10
    )
    assert [(g.key, g.count, g.expenses) for g in summary.groups] == [("DIRECT_DEBIT", 2, Decimal("-3"))]


def test_summarize_rejects_mixed_currencies():
    with pytest.raises(ValueError, match="several currencies"):
        views.summarize(["acc"], [_tx("1"), _tx("1", currency="USD")], "month", 10)


def test_depot_view_masks_display_number():
    from comdirect_mcp.domain.models import Depot

    dumped = views.depot_view(Depot("dep", "1234567890", None)).model_dump(mode="json")
    assert dumped == {"id": "dep", "display_id": "...7890"}


def test_whitespace_counterparty_name_is_omitted():
    assert views.counterparty_name(AccountHolder("  ", None, None)) is None


def test_compact_depot_position_keeps_holding_and_verbose_restores_details():
    from comdirect_mcp.domain.models import DepotPosition

    position = DepotPosition(
        depot_id="dep",
        position_id="pos",
        wkn="123456",
        quantity=Decimal("2"),
        quantity_unit="XXX",
        current_value=Decimal("10"),
        current_value_currency="EUR",
        purchase_value=Decimal("8"),
        purchase_value_currency="EUR",
        profit_loss_purchase_abs=None,
        profit_loss_purchase_rel=None,
        profit_loss_prev_day_abs=None,
        profit_loss_prev_day_rel=None,
        instrument_name="Example",
        isin="DE0001234567",
    )
    compact = views.depot_position_view(position).model_dump(mode="json")
    verbose = views.depot_position_view(position, True).model_dump(mode="json")
    assert compact == {key: value for key, value in verbose.items() if key in compact}
    assert compact["quantity"] == "2"
    assert compact["instrument_name"] == "Example"
    assert "position_id" not in compact and "purchase_value" not in compact
    assert verbose["position_id"] == "pos" and verbose["purchase_value"] == "8"


def test_portfolio_weights_are_rounded_to_two_decimals():
    assert views._percent(Decimal(1), Decimal(3)) == Decimal("33.33")
    assert views._percent(Decimal(1), Decimal(0)) is None


def _monthly(counterparty, amounts, start=date(2026, 1, 3), step=30):
    from datetime import timedelta

    return [
        _tx(amount, counterparty, booking=start + timedelta(days=step * i), tx_type="DIRECT_DEBIT")
        for i, amount in enumerate(amounts)
    ]


def _recurring(txs, until=date(2026, 6, 10)):
    return views.find_recurring(["acc"], txs, date(2026, 1, 1), until, limit=10)


def test_recurring_finds_monthly_payments_with_price_change():
    result = _recurring(_monthly("Streaming", ["-9.99", "-9.99", "-12.99", "-12.99", "-12.99"]))
    (payment,) = result.payments
    assert (payment.counterparty, payment.rhythm, payment.count) == ("Streaming", "monthly", 5)
    assert (payment.last_amount, payment.previous_amount) == (Decimal("-12.99"), Decimal("-9.99"))
    assert payment.yearly_cost == Decimal("-155.88") == result.yearly_cost
    assert payment.next_expected == date(2026, 6, 2) and payment.ended is None


def test_recurring_marks_ended_payments_and_leaves_them_out_of_the_total():
    result = _recurring(_monthly("Gym", ["-30"] * 3), until=date(2026, 6, 10))
    (payment,) = result.payments
    assert payment.ended is True and payment.next_expected is None
    assert result.yearly_cost == 0


def test_recurring_ignores_irregular_shopping_income_and_internal_transfers():
    shop = [_tx("-20", "Shop", booking=date(2026, 1, d)) for d in (2, 3, 11, 25)]
    shop += [_tx("-15", "Shop", booking=date(2026, 2, d)) for d in (1, 2)]
    weekly_groceries = _monthly("Market", ["-12", "-80", "-35", "-60", "-20"], step=7)
    salary = _monthly("Employer", ["3000"] * 4)
    own = AccountHolder(holder_name="Me", iban="DE02120300000000202051", bic=None)
    savings = [
        Transaction("acc", t.booking_date, Decimal("-100"), "EUR", None, "TRANSFER", counterparty=own)
        for t in _monthly("x", ["-1"] * 4)
    ]
    result = views.find_recurring(
        ["acc"],
        shop + weekly_groceries + salary + savings,
        date(2026, 1, 1),
        date(2026, 6, 10),
        limit=10,
        own=frozenset({"DE02120300000000202051"}),
    )
    assert result.payments == []


def test_recurring_finds_yearly_payments_with_two_bookings():
    txs = [_tx("-89", "Insurance", booking=date(2025, 3, 1)), _tx("-95", "Insurance", booking=date(2026, 3, 2))]
    (payment,) = views.find_recurring(["acc"], txs, date(2025, 1, 1), date(2026, 6, 1), limit=10).payments
    assert (payment.rhythm, payment.yearly_cost, payment.previous_amount) == ("yearly", Decimal("-95"), Decimal("-89"))


def test_category_summary_lists_uncategorized_counterparties():
    from comdirect_mcp.categories import parse_rules

    rules = parse_rules({"rule": [{"category": "Groceries", "counterparty": "REWE"}]})
    txs = [_tx("-30", "REWE"), _tx("-50", "Amazon"), _tx("-5", "Kiosk"), _tx("-20", "Amazon")]
    summary = views.summarize(["acc"], txs, "category", 10, categories=rules)
    assert [(g.key, g.expenses, g.count) for g in summary.uncategorized] == [
        ("Amazon", Decimal("-70"), 2),
        ("Kiosk", Decimal("-5"), 1),
    ]
    assert views.summarize(["acc"], txs, "counterparty", 10).uncategorized is None


def test_recurring_ignores_payments_with_strongly_varying_amounts():
    # Live data: fuel payments at a petrol station looked monthly, with strongly varying amounts.
    assert _recurring(_monthly("Petrol", ["-17", "-9", "-2.70"])).payments == []
