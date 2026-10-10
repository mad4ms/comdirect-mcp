"""New read endpoints through real HTTP serialization and MCP schema validation, using synthetic data."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
import urllib3
from mcp.client import Client
from test_http_roundtrip import DEPOT_TRANSACTIONS, INSTRUMENT, WEALTH_REPORT, FakeComdirect

from comdirect_mcp import server
from comdirect_mcp.client import ComdirectClient
from comdirect_mcp.domain.mappers import map_depot_transaction, map_instrument, map_wealth_overview
from comdirect_mcp.exceptions import DataError, TransactionFilterError
from comdirect_mcp.views import instrument_view, wealth_overview_view


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def bank():
    transport = FakeComdirect()
    auth = patch("comdirect_mcp.client.Authenticator")
    auth.start()
    client = ComdirectClient({"client_id": "cid", "client_secret": "csec", "username": "user", "password": "pwd"})
    client._set_session("synthetic", {"access_token": "synthetic"})
    with patch.object(urllib3.PoolManager, "request", side_effect=transport):
        yield client, transport
    client._api_client.rest_client.pool_manager.clear()
    auth.stop()


def test_wealth_preserves_all_product_types_bank_totals_and_signs(bank):
    client, transport = bank
    overview = client.get_wealth_overview()
    assert {p.type for p in overview.products} == {"ACCOUNT", "CARD", "DEPOT", "LOAN", "SAVINGS"}
    assert overview.total_balance_eur == Decimal("758.00")
    assert next(p for p in overview.products if p.type == "LOAN").balance == Decimal("-500")
    assert next(p for p in overview.products if p.type == "SAVINGS").balance == Decimal("200")
    assert "productType" not in transport.requests[-1][1]
    view = wealth_overview_view(overview).model_dump(mode="json")
    assert view["missing_value_count"] == 0 and view["products_complete"] is True
    assert all(
        p.get("display_id", "...unknown").startswith("...") or len(p.get("display_id", "")) <= 4
        for p in view["products"]
    )


def test_wealth_does_not_invent_totals_or_discard_unknown_product_types():
    report = {
        "paging": {"matches": 3},
        "values": [
            {"productType": "FUTURE", "productId": "future"},
            {"productType": "ACCOUNT", "balance": {"balance": {"value": "12", "unit": "USD"}}},
        ],
    }
    view = wealth_overview_view(map_wealth_overview(report)).model_dump(mode="json")
    assert "total_balance_eur" not in view
    assert view["count"] == 2 and view["products_complete"] is False
    assert view["missing_value_count"] == 1
    assert view["products"][0] == {"id": "future", "type": "FUTURE"}
    assert view["products"][1]["currency"] == "USD"
    empty = wealth_overview_view(map_wealth_overview({})).model_dump(mode="json")
    assert "products_complete" not in empty and "total_balance_eur" not in empty
    assert empty["products"] == []


def test_non_eur_aggregate_is_not_mislabeled_as_eur():
    assert map_wealth_overview({"aggregated": {"balanceEUR": {"value": "1", "unit": "USD"}}}).total_balance_eur is None


def test_instrument_requests_comma_separated_projection_and_preserves_optional_flags(bank):
    client, transport = bank
    instrument = client.get_instrument("DE0001234567", verbose=True)
    assert "fundDistribution%2CderivativeData" in transport.requests[-1][1]
    assert instrument.fund.total_expense_ratio == Decimal("0.20")
    assert instrument.derivative.strike_price_currency == "USD"
    assert instrument.derivative.expiry_date == date(2027, 6, 30)
    assert instrument.notation == "pieces"
    view = instrument_view(instrument, True).model_dump(mode="json")
    assert view["kid_available"] is False and "priips_relevant" not in view
    assert instrument_view(map_instrument({}), True).model_dump(mode="json") == {}
    assert instrument_view(map_instrument({"fundsDistribution": {}}), True).model_dump(mode="json") == {"fund": {}}
    compact = instrument_view(instrument).model_dump(mode="json")
    assert "fund" not in compact and "derivative" not in compact


@pytest.mark.parametrize("values", [[], [{}, {}]])
def test_instrument_ambiguous_or_empty_results_fail(bank, values):
    client, _ = bank
    with patch.object(client, "_get_json", return_value={"values": values}):
        with pytest.raises(DataError, match="exactly one"):
            client.get_instrument("EXAMPLE")


def test_depot_dates_are_enforced_when_bank_ignores_them(bank):
    client, _ = bank
    rows = client.list_depot_transactions(
        "dep_1", min_booking_date=date(2026, 10, 8), max_booking_date=date(2026, 10, 8)
    )
    assert len(rows) == 1 and rows[0].type == "BUY"
    assert rows[0].quantity_unit == "pieces"
    assert rows[0].transaction_value == Decimal("20")
    assert map_depot_transaction({}, "dep_1").booking_date is None
    assert client.list_depot_transactions("dep_1", isin="DE0000000000") == []
    with pytest.raises(TransactionFilterError, match="on or before"):
        client.list_depot_transactions("dep_1", min_booking_date=date(2026, 10, 9), max_booking_date=date(2026, 10, 8))


def test_depot_missing_date_and_incomplete_bank_list_fail(bank):
    client, _ = bank
    with patch.object(client, "_get_json", return_value={"values": [{}]}):
        with pytest.raises(TransactionFilterError, match="no booking date"):
            client.list_depot_transactions("dep_1", min_booking_date=date(2026, 1, 1))
    with patch.object(client, "_get_json", return_value={"paging": {"matches": 2}, "values": [{}]}):
        with pytest.raises(DataError, match="incomplete"):
            client.list_depot_transactions("dep_1")


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_new_tools_validate_full_and_sparse_outputs_without_implicit_login(bank, monkeypatch, mode):
    client, _ = bank
    state = server._ServerState()
    monkeypatch.setattr(server, "_state", state)
    async with Client(server.mcp, mode=mode) as mcp:
        calls = [
            ("get_wealth_overview", {}),
            ("get_instrument", {"identifier": "DE0001234567"}),
            ("list_depot_transactions", {"depot_id": "dep_1"}),
        ]
        for name, args in calls:
            result = await mcp.call_tool(name, args)
            assert result.is_error and "login" in result.content[0].text
        state._client = client
        tools = {tool.name: tool for tool in (await mcp.list_tools()).tools}
        for name, args in calls:
            assert tools[name].annotations.read_only_hint is True
            result = await mcp.call_tool(name, args)
            assert not result.is_error, result.content
        page = await mcp.call_tool("list_depot_transactions", {"depot_id": "dep_1", "limit": 1, "verbose": True})
        data = page.structured_content
        assert data["next_offset"] == 1 and data["transactions"][0]["transaction_id"] == "movement_1"
        tail = await mcp.call_tool("list_depot_transactions", {"depot_id": "dep_1", "offset": 1})
        assert tail.structured_content["transactions"][0]["type"] == "SELL"
        assert "transaction_id" not in tail.structured_content["transactions"][0]
        assert "next_offset" not in tail.structured_content
        with (
            patch.dict(INSTRUMENT, {}, clear=True),
            patch.dict(WEALTH_REPORT, {"values": [{}]}, clear=True),
            patch.dict(DEPOT_TRANSACTIONS, {"values": [{}]}, clear=True),
        ):
            for name, args in calls:
                result = await mcp.call_tool(name, args)
                assert not result.is_error, result.content
                if name == "get_instrument":
                    assert result.structured_content == {}
                else:
                    key = "products" if name == "get_wealth_overview" else "transactions"
                    assert result.structured_content[key] == [{}]
        for name, args in [
            ("get_instrument", {"identifier": ""}),
            ("list_depot_transactions", {"depot_id": "dep_1", "limit": 0}),
            ("list_depot_transactions", {"depot_id": "dep_1", "offset": -1}),
        ]:
            assert (await mcp.call_tool(name, args)).is_error


def test_depot_paging_counts_raw_rows_and_filters_after_all_pages(bank):
    client, transport = bank
    rows = [
        {**DEPOT_TRANSACTIONS["values"][0], "transactionId": f"movement_{i}", "bookingDate": f"2026-10-0{i}"}
        for i in range(1, 6)
    ]
    with patch.dict(DEPOT_TRANSACTIONS, {"values": rows}):
        selected = client.list_depot_transactions("dep_1", min_booking_date=date(2026, 10, 4))
    assert [tx.transaction_id for tx in selected] == ["movement_4", "movement_5"]
    assert [parse_qs(urlparse(url).query)["paging-first"] for _, url, _ in transport.requests] == [["0"], ["2"], ["4"]]


@pytest.mark.parametrize(
    "pages",
    [
        [
            {"paging": {"matches": 3, "index": 0}, "values": [{"transactionId": "x"}]},
            {"paging": {"matches": 3, "index": 0}, "values": [{"transactionId": "y"}]},
        ],
        [
            {"paging": {"matches": 3}, "values": [{"transactionId": "x"}]},
            {"paging": {"matches": 3}, "values": [{"transactionId": "x"}]},
        ],
        [{"paging": {"matches": 3}, "values": [{"transactionId": "x"}]}, {"paging": {"matches": 3}, "values": []}],
    ],
)
def test_depot_pagination_rejects_stalled_or_empty_pages(bank, pages):
    client, _ = bank
    with patch.object(client, "_get_json", side_effect=pages):
        with pytest.raises(DataError, match="incomplete"):
            client.list_depot_transactions("dep_1")


def test_depot_paging_refuses_changed_match_count(bank):
    client, _ = bank
    with patch.object(
        client,
        "_get_json",
        side_effect=[
            {"paging": {"matches": 2}, "values": [{"transactionId": "x"}]},
            {"paging": {"matches": 3}, "values": [{"transactionId": "y"}]},
        ],
    ):
        with pytest.raises(DataError, match="count changed"):
            client.list_depot_transactions("dep_1")
