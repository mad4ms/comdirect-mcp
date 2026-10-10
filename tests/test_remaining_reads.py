"""Read-only API additions, financial aggregation and bounded document processing."""

import dataclasses
import io
import subprocess
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from mcp.client import Client
from test_http_roundtrip import ORDER, ORDER_DIMENSIONS, synthetic_pdf
from test_read_features import bank as bank_fixture

from comdirect_mcp import server
from comdirect_mcp._openapi.exceptions import ApiException
from comdirect_mcp.document_text import html_text, pdf_text
from comdirect_mcp.domain.mappers import map_dimensions, map_instrument, map_order
from comdirect_mcp.exceptions import DataError
from comdirect_mcp.views import dimensions_view, instrument_view, order_view, summarize_portfolio

bank = bank_fixture


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_single_reads_use_documented_paths_and_transport(bank):
    client, transport = bank
    assert client.get_account_balance("acc_1") == client.list_accounts()[0]
    assert client.get_depot_position("dep_1", "pos_1") == client.get_depot_positions("dep_1")[1][0]
    dimensions = client.get_order_dimensions("DE0001234567", "venue_1", "BUY", "LIMIT")
    assert dimensions == map_dimensions(ORDER_DIMENSIONS)
    url = transport.requests[-1][1]
    assert "isin=DE0001234567" in url and "side=BUY" in url and "venueId=venue_1" in url
    order = client.get_order("order_1")
    assert order == map_order(ORDER)
    assert order.validity == date(2026, 10, 31) and order.best_execution is False
    assert order.executions[0].price == Decimal("10")
    assert b"Synthetic cover" in client.get_document_cover("doc_1")
    assert transport.requests[-1][2]["Accept"] == "text/html"
    assert all(method == "GET" for method, _, _ in transport.requests)


def test_order_bank_pages_and_ignored_filters_are_handled(bank):
    client, transport = bank
    orders = client.list_orders("dep_1", side="SELL", status="SETTLED")
    assert len(orders) == 1 and orders[0].id == "order_2"
    urls = [url for _, url, _ in transport.requests]
    assert len(urls) == 2 and "paging-first=1" in urls[1]
    assert "side=SELL" in urls[0] and "orderStatus=SETTLED" in urls[0]


def test_dimensions_selects_wkn_or_uuid_and_position_supports_envelopes(bank):
    client, transport = bank
    client.get_order_dimensions("123456")
    assert "wkn=123456" in transport.requests[-1][1]
    client.get_order_dimensions("instrument-uuid")
    assert "instrumentId=instrument-uuid" in transport.requests[-1][1]
    with patch.object(client, "_get_json", return_value={"values": [{}]}):
        assert client.get_depot_position("dep_1", "pos_1").current_value is None
    with patch.object(client, "_get_json", return_value={"values": []}), pytest.raises(DataError):
        client.get_depot_position("dep_1", "pos_1")


def test_known_partial_positions_cannot_be_summarized(bank):
    client, _ = bank
    from comdirect_mcp._openapi.models.list_resource_depot_position import ListResourceDepotPosition

    response = ListResourceDepotPosition.from_dict({"paging": {"matches": 2}, "values": [{}]})
    with (
        patch.object(client._brokerage, "brokerage_v3_get_depot_positions", return_value=response),
        pytest.raises(DataError),
    ):
        client.get_depot_positions("dep_1")


@pytest.mark.parametrize(
    "pages",
    [
        [{"paging": {"matches": 2}, "values": [ORDER]}] * 2,
        [{"paging": {"matches": 2}, "values": [ORDER]}, {"paging": {"matches": 2}, "values": []}],
        [{"paging": {"matches": 2}, "values": [ORDER]}, {"paging": {"matches": 3}, "values": []}],
    ],
)
def test_order_incomplete_lists_fail_without_exposing_content(bank, pages):
    client, _ = bank
    with patch.object(client, "_get_json", side_effect=pages), pytest.raises(DataError) as error:
        client.list_orders("dep_1")
    assert "order_1" not in str(error.value)


def test_sparse_orders_dimensions_and_underlying_snapshot():
    assert order_view(map_order({}), True).model_dump(mode="json") == {}
    assert dimensions_view(map_dimensions({})).model_dump(mode="json") == {}
    assert "best_execution" not in order_view(map_order({}), True).model_dump(mode="json")
    order = order_view(map_order(ORDER)).model_dump(mode="json")
    assert "executions" not in order and "best_execution" not in order
    assert order["sub_orders"][0]["id"] == "leg_1"
    data = {
        "derivativeData": {
            "underlyingPrice": {
                "type": "LST",
                "price": {"value": "12.50", "unit": "USD"},
                "priceDateTime": "2026-10-09T10:00:00Z",
            }
        }
    }
    price = instrument_view(map_instrument(data), True).model_dump(mode="json")["derivative"]["underlying_price"]
    assert price == {"type": "LST", "price": "12.50", "currency": "USD", "timestamp": "2026-10-09T10:00:00Z"}


def test_order_excessive_nesting_is_rejected():
    nested = {}
    for _ in range(10):
        nested = {"subOrders": [nested]}
    with pytest.raises(DataError, match="nesting"):
        map_order(nested)


def test_portfolio_currency_groups_weights_and_remainder(bank):
    client, _ = bank
    position = client.get_depot_positions("dep_1")[1][0]
    positions = [
        dataclasses.replace(position, current_value=Decimal("75")),
        dataclasses.replace(position, current_value=Decimal("25")),
        dataclasses.replace(position, current_value=Decimal("200"), current_value_currency="USD"),
    ]
    summary = summarize_portfolio("dep_1", positions, 1)
    eur, usd = summary.currencies
    assert eur.total_value == Decimal("100") and eur.positions[0].weight_percent == Decimal("75")
    assert (
        eur.omitted_count == 1 and eur.omitted_value == Decimal("25") and eur.omitted_weight_percent == Decimal("25")
    )
    assert usd.total_value == Decimal("200") and usd.positions[0].weight_percent == Decimal("100")
    zero = summarize_portfolio("dep_1", [dataclasses.replace(position, current_value=Decimal("0"))], 1)
    assert zero.currencies[0].positions[0].weight_percent is None
    assert summarize_portfolio("dep_1", [], 1).currencies == []


@pytest.mark.parametrize(
    "value,currency", [(None, "EUR"), (Decimal("1"), None), (Decimal("-1"), "EUR"), (Decimal("NaN"), "EUR")]
)
def test_portfolio_unknown_or_invalid_values_fail(bank, value, currency):
    client, _ = bank
    position = client.get_depot_positions("dep_1")[1][0]
    with pytest.raises(ValueError):
        summarize_portfolio(
            "dep_1", [dataclasses.replace(position, current_value=value, current_value_currency=currency)], 1
        )


def test_pdf_worker_paging_truncation_invalid_input_and_timeout():
    content = synthetic_pdf()
    first = pdf_text(content, 0, 1, 1000)
    assert first["page_count"] == 2 and first["next_page"] == 1 and first["pages_processed"] == 1
    assert "page one" in first["text"] and "page two" not in first["text"]
    last = pdf_text(content, 1, 1, 10)
    assert len(last["text"]) == 10 and last["text_truncated"] is True and last["has_more_pages"] is False
    with pytest.raises(DataError):
        pdf_text(b"not a PDF", 0, 1, 100)
    with pytest.raises(DataError):
        pdf_text(content, 2, 1, 100)
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("synthetic", 15)), pytest.raises(DataError):
        pdf_text(content, 0, 1, 100)


def test_pdf_scans_encryption_and_decompression_limits():
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    blank = PdfWriter()
    blank.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    blank.write(buffer)
    assert pdf_text(buffer.getvalue(), 0, 1, 100)["text"] == ""

    encrypted = PdfWriter()
    encrypted.append(PdfReader(io.BytesIO(synthetic_pdf())))
    encrypted.encrypt("synthetic-test-password")
    buffer = io.BytesIO()
    encrypted.write(buffer)
    with pytest.raises(DataError):
        pdf_text(buffer.getvalue(), 0, 1, 100)

    large = PdfWriter()
    page = large.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b" " * (21 * 1024 * 1024))
    page[NameObject("/Contents")] = large._add_object(stream.flate_encode())
    buffer = io.BytesIO()
    large.write(buffer)
    with pytest.raises(DataError):
        pdf_text(buffer.getvalue(), 0, 1, 100)


def test_html_never_returns_active_content_or_follows_links():
    text, truncated = html_text(
        b'<script>secret()</script><style>x</style><p>Hello &amp; world</p><a href="https://example.com">Link</a>', 100
    )
    assert "secret" not in text and "https" not in text and "Hello & world" in text and "Link" in text
    assert not truncated
    assert html_text(b"123456", 5) == ("12345", True)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_new_tools_schemas_guards_annotations_continuation_and_limits(bank, mode, monkeypatch):
    client, _ = bank
    state = server._ServerState()
    monkeypatch.setattr(server, "_state", state)
    args = {
        "get_account_balance": {"account_id": "acc_1"},
        "get_depot_position": {"depot_id": "dep_1", "position_id": "pos_1"},
        "summarize_portfolio": {"depot_id": "dep_1", "limit": 1},
        "list_orders": {"depot_id": "dep_1", "limit": 1},
        "get_order": {"order_id": "order_1", "verbose": True},
        "get_order_dimensions": {"identifier": "DE0001234567"},
        "get_document_cover": {"document_id": "doc_1"},
        "extract_document_text": {"document_id": "doc_1", "max_pages": 1},
    }
    async with Client(server.mcp, mode=mode) as mcp_client:
        tools = {t.name: t for t in (await mcp_client.list_tools()).tools}
        for name, arguments in args.items():
            assert (await mcp_client.call_tool(name, arguments)).is_error
            assert tools[name].output_schema
            assert tools[name].annotations.read_only_hint is (
                name not in {"get_document_cover", "extract_document_text"}
            )
        state._client = client
        for name, arguments in args.items():
            result = await mcp_client.call_tool(name, arguments)
            assert not result.is_error, name
            assert result.structured_content is not None
            if name == "list_orders":
                assert result.structured_content["next_offset"] == 1
                tail = await mcp_client.call_tool(name, {**arguments, "offset": 1})
                assert tail.structured_content["orders"][0]["id"] == "order_2"
                assert "next_offset" not in tail.structured_content
        assert (
            await mcp_client.call_tool("extract_document_text", {"document_id": "doc_1", "max_pages": 21})
        ).is_error
        assert (await mcp_client.call_tool("summarize_portfolio", {"depot_id": "dep_1", "limit": 0})).is_error
        with patch.object(
            client, "get_document_cover", side_effect=ApiException(status=500, reason="Internal Server Error")
        ):
            failure = await mcp_client.call_tool("get_document_cover", {"document_id": "doc_1"})
            assert failure.is_error
            message = " ".join(getattr(block, "text", "") for block in failure.content)
            assert "HTTP 500" in message and "extract_document_text" in message
        monkeypatch.setattr(server, "MAX_DOCUMENT_BYTES", 1)
        assert (await mcp_client.call_tool("extract_document_text", {"document_id": "doc_1"})).is_error
        assert (await mcp_client.call_tool("get_document_cover", {"document_id": "doc_1"})).is_error
