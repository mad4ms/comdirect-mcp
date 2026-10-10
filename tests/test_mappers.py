from decimal import Decimal
from types import SimpleNamespace

import pytest

from comdirect_mcp.domain.mappers import map_card, map_transaction, normalize_purpose


def numbered(*lines):
    return "".join(f"{i:02d}{line:<35}"[:37] for i, line in enumerate(lines, start=1))


def test_joins_numbered_lines_and_split_words():
    first = "Rechnung 4711 Beispielhandel XY Gmb"  # a full line: the word continues on the next line
    assert len(first) == 35
    assert (
        normalize_purpose("01" + first + "02" + "H Berlin".ljust(35)) == "Rechnung 4711 Beispielhandel XY GmbH Berlin"
    )


def test_padded_lines_are_joined_with_a_space():
    assert (
        normalize_purpose(numbered("EDEKA SAGT DANKE", "Karte 1 2026-10-01")) == "EDEKA SAGT DANKE Karte 1 2026-10-01"
    )


def test_reference_block_is_dropped():
    raw = numbered("Beitrag Oktober", "End-to-End-Ref.:", "ABC123", "Mandatsref: M-1", "Gläubiger-ID: DE98ZZZ")
    assert normalize_purpose(raw) == "Beitrag Oktober"


def test_text_without_line_numbers_is_only_trimmed():
    assert normalize_purpose("  Lohn   September ") == "Lohn September"
    assert normalize_purpose("01.10. Miete", numbered=False) == "01.10. Miete"
    assert normalize_purpose("01" + "x" * 35 + "03y") == "01" + "x" * 35 + "03y"  # numbers not consecutive
    assert normalize_purpose(None) is None and normalize_purpose("") is None


def _api_tx(amount, booking_status="BOOKED", remittance_info=None, **roles):
    def holder(name):
        return SimpleNamespace(holder_name=name, iban=None, bic=None) if name else None

    return SimpleNamespace(
        booking_date="2026-10-01",
        amount=SimpleNamespace(value=amount, unit="EUR"),
        remittance_info=remittance_info,
        transaction_type=SimpleNamespace(key="TRANSFER"),
        reference=None,
        booking_status=booking_status,
        valuta_date=None,
        direct_debit_creditor_id=None,
        direct_debit_mandate_id=None,
        end_to_end_reference=None,
        new_transaction=False,
        remitter=holder(roles.get("remitter")),
        deptor=holder(roles.get("debtor")),
        creditor=holder(roles.get("creditor")),
    )


@pytest.mark.parametrize(
    "amount, roles, expected",
    [
        ("-20.00", {"creditor": "Recipient", "remitter": "Me"}, "Recipient"),  # outgoing transfer
        ("-20.00", {"remitter": "PayPal Europe"}, "PayPal Europe"),  # direct debit: collector is the remitter
        ("100.00", {"remitter": "Sender", "creditor": "Me"}, "Sender"),  # incoming transfer
        ("100.00", {}, None),
    ],
)
def test_counterparty_and_direction(amount, roles, expected):
    tx = map_transaction(_api_tx(amount, **roles), "acc")
    assert (tx.counterparty.holder_name if tx.counterparty else None) == expected
    assert tx.direction == ("out" if Decimal(amount) < 0 else "in")


def test_pending_purpose_keeps_leading_digits():
    tx = map_transaction(_api_tx("-5.00", booking_status="NOTBOOKED", remittance_info="01.10. Miete"), "acc")
    assert tx.purpose == "01.10. Miete"
    assert tx.purpose_raw == "01.10. Miete"


def test_map_card():
    card = map_card(
        {
            "productType": "CARD",
            "balance": {
                "cardId": "c1",
                "card": {
                    "cardType": {"key": "VISA_PREPAID", "text": "Visa"},
                    "primaryAccountNumberSuffix": "1234",
                    "cardLimit": {"value": "500", "unit": "EUR"},
                    "status": "ACTIVE",
                },
                "balance": {"value": "42.10", "unit": "EUR"},
                "availableCashAmount": {"value": "42.10", "unit": "EUR"},
            },
        }
    )
    assert (card.id, card.type, card.number_suffix, card.balance, card.limit, card.currency) == (
        "c1",
        "VISA_PREPAID",
        "1234",
        Decimal("42.10"),
        Decimal("500"),
        "EUR",
    )


@pytest.mark.parametrize(
    "model, mapper_name",
    [
        ("AccountBalance", "map_account"),
        ("Depot", "map_depot"),
        ("DepotPosition", "map_depot_position"),
        ("Document", "map_document"),
    ],
)
def test_empty_api_models_preserve_missing_values(model, mapper_name):
    import dataclasses

    from comdirect_mcp import _openapi
    from comdirect_mcp.domain import mappers

    mapped = getattr(mappers, mapper_name)(getattr(_openapi, model)())
    assert all(value is None for value in dataclasses.asdict(mapped).values())


def test_transaction_without_amount_preserves_unknown_direction():
    from comdirect_mcp._openapi.models.account_transaction import AccountTransaction

    tx = map_transaction(AccountTransaction(), "acc")
    assert tx.amount is None and tx.currency is None and tx.direction is None
    assert tx.new_transaction is None


def test_booked_purpose_can_begin_with_a_date_or_number():
    assert normalize_purpose(numbered("01.10. Rechnung 123")) == "01.10. Rechnung 123"


@pytest.mark.parametrize("value", [None, False, True])
def test_transaction_flag_preserves_missing_and_explicit_values(value):
    from comdirect_mcp._openapi.models.account_transaction import AccountTransaction

    payload = {} if value is None else {"newTransaction": value}
    assert map_transaction(AccountTransaction.from_dict(payload), "acc").new_transaction is value


def test_unnamed_counterparty_retains_iban_for_verbose_view():
    from comdirect_mcp.views import transaction_view

    raw = _api_tx("-1")
    raw.creditor = SimpleNamespace(holder_name=None, iban="DE89370400440532013000", bic=None)
    tx = map_transaction(raw, "acc")
    view = transaction_view(tx, verbose=True).model_dump(mode="json")
    assert view["counterparty_iban"] == "DE**...3000"
    assert "counterparty" not in view
