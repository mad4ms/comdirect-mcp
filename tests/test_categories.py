from datetime import date
from decimal import Decimal

import pytest

from comdirect_mcp import views
from comdirect_mcp.categories import (
    UNCATEGORIZED,
    CategoryRulesError,
    categories_path,
    categorize,
    load_rules,
    parse_rules,
)
from comdirect_mcp.domain.models import AccountHolder, Transaction

RULES = """
[[rule]]
category = "Lebensmittel"
counterparty = ["rewe", "EDEKA"]

[[rule]]
category = "Abos"
type = "DIRECT_DEBIT"
purpose = "Monatsbeitrag"

[[rule]]
category = "Sonstige Einnahmen"
direction = "in"
"""


def _tx(amount, counterparty=None, purpose=None, tx_type="TRANSFER"):
    holder = AccountHolder(holder_name=counterparty, iban=None, bic=None) if counterparty else None
    return Transaction(
        account_id="acc",
        booking_date=date(2026, 3, 5),
        amount=Decimal(amount),
        currency="EUR",
        purpose=purpose,
        type=tx_type,
        counterparty=holder,
        direction="in" if Decimal(amount) > 0 else "out",
    )


@pytest.fixture
def rules(categories_file):
    categories_file.write_text(RULES, encoding="utf-8")
    loaded = load_rules()
    assert loaded is not None
    return loaded


def test_path_comes_from_environment(categories_file):
    assert categories_path() == categories_file


def test_missing_file_means_no_rules():
    assert load_rules() is None


def test_first_matching_rule_wins_and_matching_ignores_case(rules):
    assert categorize(_tx("-30", "REWE Markt GmbH"), rules) == "Lebensmittel"
    assert categorize(_tx("-30", "Edeka Center"), rules) == "Lebensmittel"
    assert categorize(_tx("5", "Rewe Markt GmbH"), rules) == "Lebensmittel"
    assert categorize(_tx("12", "Employer"), rules) == "Sonstige Einnahmen"


def test_all_conditions_of_a_rule_must_match(rules):
    debit = _tx("-9.99", "Streaming AG", purpose="MONATSBEITRAG 03/2026", tx_type="DIRECT_DEBIT")
    assert categorize(debit, rules) == "Abos"
    transfer = _tx("-9.99", "Streaming AG", purpose="Monatsbeitrag 03/2026")
    assert categorize(transfer, rules) == UNCATEGORIZED
    assert categorize(_tx("-1"), rules) == UNCATEGORIZED


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"rules": []}, "Unknown top-level keys"),
        ({"rule": [{"counterparty": "x"}]}, "needs a non-empty `category`"),
        ({"rule": [{"category": "A"}]}, "has no condition"),
        ({"rule": [{"category": "A", "counterparty": []}]}, "non-empty text"),
        ({"rule": [{"category": "A", "purpose": [" "]}]}, "non-empty text"),
        ({"rule": [{"category": "A", "direction": "both"}]}, "direction"),
        ({"rule": [{"category": "A", "payee": "x"}]}, "unknown keys: payee"),
    ],
)
def test_invalid_rules_are_rejected(data, message):
    with pytest.raises(CategoryRulesError, match=message):
        parse_rules(data)


def test_invalid_toml_names_the_file(categories_file):
    categories_file.write_text("[[rule]\n", encoding="utf-8")
    with pytest.raises(CategoryRulesError, match="not valid TOML") as error:
        load_rules()
    assert str(categories_file) in str(error.value)


def test_summarize_by_category(rules):
    txs = [_tx("-30", "REWE"), _tx("-20", "EDEKA"), _tx("-5", "Kiosk"), _tx("100", "Employer")]
    summary = views.summarize(["acc"], txs, "category", max_groups=10, categories=rules)
    groups = {g.key: (g.net, g.count) for g in summary.groups}
    assert groups == {
        "Sonstige Einnahmen": (Decimal("100"), 1),
        "Lebensmittel": (Decimal("-50"), 2),
        UNCATEGORIZED: (Decimal("-5"), 1),
    }
    assert summary.group_by == "category"


def test_categories_see_real_names_when_names_are_masked(rules, monkeypatch):
    monkeypatch.setattr(views, "MASK_NAMES", True)
    summary = views.summarize(["acc"], [_tx("-30", "REWE")], "category", max_groups=10, categories=rules)
    assert [g.key for g in summary.groups] == ["Lebensmittel"]
