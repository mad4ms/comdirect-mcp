"""Exercise both protocol modes over real process pipes, without network or real credentials."""

import base64
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import ElicitResult


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_all_tools_through_stdio_with_fake_bank(mode):
    approvals = 0

    async def approve(context, params):
        nonlocal approvals
        approvals += 1
        return ElicitResult(action="accept", content={"approved": True})

    command = StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).with_name("stdio_fake_server.py"))]
    )
    async with Client(command, mode=mode, elicitation_callback=approve) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert len(tools) == 17
        assert (await client.call_tool("list_accounts")).is_error
        assert not (await client.call_tool("login")).is_error
        assert approvals == 1
        assert (await client.call_tool("login")).is_error
        assert approvals == 1
        accounts = await client.call_tool("list_accounts")
        assert not accounts.is_error
        account_id = accounts.structured_content["accounts"][0]["id"]
        for direction, amount in (("INCOMING", "100.00"), ("OUTGOING", "-12.34")):
            result = await client.call_tool(
                "list_transactions", {"account_id": account_id, "transaction_direction": direction, "verbose": True}
            )
            assert not result.is_error
            assert [tx["amount"] for tx in result.structured_content["transactions"]] == [amount]
        result = await client.call_tool(
            "list_transactions",
            {"account_id": account_id, "min_booking_date": "2026-10-08", "max_booking_date": "2026-10-08"},
        )
        assert not result.is_error
        assert result.structured_content["count"] == 1
        page = await client.call_tool("list_transactions", {"account_id": account_id, "limit": 1})
        assert page.structured_content["next_offset"] == 1
        tail = await client.call_tool("list_transactions", {"account_id": account_id, "limit": 1, "offset": 1})
        assert tail.structured_content["transactions"][0]["amount"] == "100.00"
        assert "next_offset" not in tail.structured_content
        filtered_tail = await client.call_tool(
            "list_transactions", {"account_id": account_id, "min_booking_date": "2026-10-08", "offset": 1}
        )
        assert filtered_tail.structured_content["count"] == 1
        for group_by in ("month", "counterparty", "type"):
            result = await client.call_tool(
                "summarize_transactions",
                {
                    "account_id": account_id,
                    "min_booking_date": "2026-10-08",
                    "max_booking_date": "2026-10-08",
                    "group_by": group_by,
                },
            )
            assert not result.is_error
            assert result.structured_content["net"] == "100.00"
        wealth = await client.call_tool("get_wealth_overview")
        assert not wealth.is_error
        assert wealth.structured_content["total_balance_eur"] == "758.00"
        assert wealth.structured_content["products_complete"] is True
        security = await client.call_tool("get_instrument", {"identifier": "DE0001234567", "verbose": True})
        assert not security.is_error
        assert security.structured_content["fund"]["total_expense_ratio"] == "0.20"
        movements = await client.call_tool("list_depot_transactions", {"depot_id": "dep_1", "limit": 1})
        assert not movements.is_error
        assert movements.structured_content["next_offset"] == 1
        movement_tail = await client.call_tool("list_depot_transactions", {"depot_id": "dep_1", "offset": 1})
        assert movement_tail.structured_content["transactions"][0]["type"] == "SELL"
        assert not (await client.call_tool("list_cards")).is_error
        assert not (await client.call_tool("list_depots")).is_error
        assert not (await client.call_tool("get_depot_positions", {"depot_id": "dep_1"})).is_error
        for name, args in (
            ("get_depot_positions", {"depot_id": "dep_1", "isin": "DE0001234567", "verbose": True}),
            ("summarize_portfolio", {"depot_id": "dep_1"}),
            ("list_orders", {"depot_id": "dep_1", "limit": 1}),
            ("get_order", {"order_id": "order_1", "verbose": True}),
            ("read_document", {"document_id": "doc_1", "format": "cover"}),
            ("read_document", {"document_id": "doc_1", "max_pages": 1}),
        ):
            result = await client.call_tool(name, args)
            assert not result.is_error, name
            assert result.structured_content is not None
        security = await client.call_tool(
            "get_instrument", {"identifier": "DE0001234567", "verbose": True, "include_order_dimensions": True}
        )
        assert not security.is_error and security.structured_content["order_dimensions"]["count"] == 1
        docs = await client.call_tool("list_documents", {"limit": 1})
        assert not docs.is_error
        assert docs.structured_content["truncated"] is False
        assert "next_offset" not in docs.structured_content
        result = await client.call_tool("read_document", {"document_id": "doc_1", "format": "file"})
        assert not result.is_error
        contents = (await client.read_resource(result.structured_content["resource_uri"])).contents
        assert base64.b64decode(contents[0].blob).startswith(b"%PDF")
        assert (await client.call_tool("list_transactions", {"account_id": account_id, "limit": 0})).is_error
        assert (
            await client.call_tool(
                "list_transactions",
                {"account_id": account_id, "min_booking_date": "2026-10-09", "max_booking_date": "2026-10-08"},
            )
        ).is_error
        assert not (await client.call_tool("logout")).is_error
        assert (await client.call_tool("list_accounts")).is_error
        assert not (await client.call_tool("logout")).is_error
