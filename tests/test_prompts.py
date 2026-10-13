from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from mcp.client import Client
from mcp.shared.exceptions import MCPError
from mcp.types import PromptReference

from comdirect_mcp import server as mcp_server
from comdirect_mcp.domain.models import AccountHolder, Transaction

RULES = '[[rule]]\ncategory = "Lebensmittel"\ncounterparty = "REWE"\n'


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def logged_in(monkeypatch):
    client = MagicMock(is_logged_in=True)
    state = mcp_server._ServerState()
    state._client = client
    monkeypatch.setattr(mcp_server, "_state", state)
    return client


def _tx(amount, counterparty):
    return Transaction(
        account_id="acc_1",
        booking_date=date(2026, 3, 5),
        amount=Decimal(amount),
        currency="EUR",
        purpose=None,
        type="TRANSFER",
        counterparty=AccountHolder(holder_name=counterparty, iban=None, bic=None),
        direction="in" if Decimal(amount) > 0 else "out",
    )


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_prompts_are_listed_and_render(mode):
    async with Client(mcp_server.mcp, mode=mode) as client:
        prompts = {p.name: p for p in (await client.list_prompts()).prompts}
        review = await client.get_prompt("monthly_review", {"month": "2026-03"})
        subscriptions = await client.get_prompt("find_subscriptions", {})
        taxes = await client.get_prompt("tax_documents", {"year": "2025"})

    assert set(prompts) == {"monthly_review", "find_subscriptions", "tax_documents"}
    assert prompts["monthly_review"].title == "Monatsrückblick"
    assert [(a.name, a.required) for a in prompts["monthly_review"].arguments or []] == [("month", True)]

    text = review.messages[0].content.text  # type: ignore[union-attr]
    assert "2026-03-01 bis 2026-03-31" in text
    assert 'group_by="month" von 2026-02-01' in text
    assert "keine Kategorie-Regeln" in text
    assert "summarize_transactions" in subscriptions.messages[0].content.text  # type: ignore[union-attr]
    tax_text = taxes.messages[0].content.text  # type: ignore[union-attr]
    assert "Steuerjahr 2025" in tax_text and "bevor ich zustimme" in tax_text


@pytest.mark.anyio
async def test_monthly_review_uses_category_rules_when_configured(categories_file):
    categories_file.write_text(RULES, encoding="utf-8")
    async with Client(mcp_server.mcp) as client:
        review = await client.get_prompt("monthly_review", {"month": "2026-12"})
    text = review.messages[0].content.text  # type: ignore[union-attr]
    assert 'group_by="category"' in text
    assert "2026-12-01 bis 2026-12-31" in text


@pytest.mark.anyio
async def test_invalid_month_is_rejected():
    async with Client(mcp_server.mcp) as client:
        with pytest.raises(MCPError, match="YYYY-MM"):
            await client.get_prompt("monthly_review", {"month": "März"})


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_prompt_argument_completion(mode):
    this_month = f"{date.today():%Y-%m}"
    async with Client(mcp_server.mcp, mode=mode) as client:
        months = await client.complete(PromptReference(name="monthly_review"), {"name": "month", "value": ""})
        years = await client.complete(PromptReference(name="tax_documents"), {"name": "year", "value": "20"})
        none = await client.complete(PromptReference(name="monthly_review"), {"name": "month", "value": "1999"})

    assert months.completion.values[0] == this_month
    assert len(months.completion.values) == 24
    assert years.completion.values[0] == str(date.today().year - 1)
    assert none.completion.values == []


@pytest.mark.anyio
async def test_categories_resource_shows_format_and_file(categories_file):
    async with Client(mcp_server.mcp) as client:
        missing = await client.read_resource("comdirect://categories")
        categories_file.write_text(RULES, encoding="utf-8")
        present = await client.read_resource("comdirect://categories")

    assert "[[rule]]" in missing.contents[0].text  # type: ignore[union-attr]
    assert "does not exist yet" in missing.contents[0].text  # type: ignore[union-attr]
    assert 'category = "Lebensmittel"' in present.contents[0].text  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_summarize_by_category(logged_in, categories_file):
    categories_file.write_text(RULES, encoding="utf-8")
    logged_in.iter_all_transactions.side_effect = lambda **kwargs: iter([_tx("-30", "REWE Markt"), _tx("-5", "Kiosk")])
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool(
            "summarize_transactions",
            {"account_id": "acc_1", "min_booking_date": "2026-03-01", "group_by": "category"},
        )

    assert not result.is_error, result.content
    groups = {g["key"]: g["expenses"] for g in result.structured_content["groups"]}
    assert groups == {"Lebensmittel": "-30", "(uncategorized)": "-5"}


@pytest.mark.anyio
@pytest.mark.parametrize(("content", "message"), [(None, "No category rules"), ("[[rule]\n", "not valid TOML")])
async def test_summarize_by_category_without_valid_rules(logged_in, categories_file, content, message):
    if content is not None:
        categories_file.write_text(content, encoding="utf-8")
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool(
            "summarize_transactions",
            {"account_id": "acc_1", "min_booking_date": "2026-03-01", "group_by": "category"},
        )

    assert result.is_error
    assert message in result.content[0].text  # type: ignore[union-attr]
    logged_in.iter_all_transactions.assert_not_called()
