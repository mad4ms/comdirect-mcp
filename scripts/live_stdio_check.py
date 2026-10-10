"""One-login stdio review; only structure/check outcomes leave the process."""

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import ElicitResult

from comdirect_mcp._diagnostics import tool_error_diagnostic

logging.disable(logging.CRITICAL)

ROOT = str(Path(__file__).resolve().parent.parent)
COMMAND = ROOT + "/.venv/bin/comdirect-mcp"
EXPECTED = {
    "login",
    "logout",
    "list_accounts",
    "list_transactions",
    "summarize_transactions",
    "list_cards",
    "list_depots",
    "get_depot_positions",
    "list_documents",
    "list_depot_transactions",
    "get_wealth_overview",
    "get_instrument",
    "download_document",
    "get_account_balance",
    "get_depot_position",
    "summarize_portfolio",
    "get_order_dimensions",
    "list_orders",
    "get_order",
    "get_document_cover",
    "extract_document_text",
}
READS = EXPECTED - {"login", "logout", "download_document", "get_document_cover", "extract_document_text"}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--server-command", default=COMMAND, help="Installed comdirect-mcp executable to test")
parser.add_argument(
    "--offline", action="store_true", help="Check only startup, schemas and login guards; no banking login"
)
parser.add_argument(
    "--wait", type=int, default=20, help="Seconds for timed approval when --no-manual-approval is used"
)
parser.add_argument(
    "--manual-approval",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Wait for an explicit approved/cancel input after photoTAN approval (default)",
)
parser.add_argument(
    "--refresh-wait", type=int, default=620, help="Seconds to keep the session open before another data call"
)
parser.add_argument(
    "--depot-only", action="store_true", help="One login; check only depot movements and their filters"
)
parser.add_argument("--remaining-only", action="store_true", help="One login; targeted new read and document tools")
options = parser.parse_args()
if options.wait < 1 or options.refresh_wait < 0:
    parser.error("wait must be positive and refresh-wait nonnegative")
failures = 0
calls = set()
elicitations = 0


def check(label, ok):
    global failures
    failures += not ok
    print(("OK   " if ok else "FAIL ") + label, flush=True)
    return ok


def compact(value):
    if isinstance(value, dict):
        return all(v is not None and compact(v) for v in value.values())
    if isinstance(value, list):
        return all(compact(v) for v in value)
    return True


def decimal_fields(value):
    money = {
        "amount",
        "balance",
        "available",
        "credit_limit",
        "limit",
        "quantity",
        "current_value",
        "purchase_value",
        "prev_day_value",
        "profit_loss_purchase_abs",
        "profit_loss_prev_day_abs",
        "income",
        "expenses",
        "net",
        "transaction_value",
        "execution_price",
        "total_balance_eur",
        "total_available_eur",
        "strike_price",
        "leverage",
        "multiplier",
        "total_expense_ratio",
        "regular_issue_surcharge",
        "discount_issue_surcharge",
        "reduced_issue_surcharge",
        "individual_issue_surcharge",
        "bonification",
        "yield_pa",
        "remaining_term_in_years",
        "nominal_rate",
        "price",
        "value",
        "open_quantity",
        "executed_quantity",
        "cancelled_quantity",
        "trigger_limit",
        "trailing_limit_distance",
        "trailing_limit_percent",
        "expected_value",
        "weight_percent",
        "total_value",
        "omitted_value",
        "omitted_weight_percent",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if key in money and not isinstance(item, dict):
                if not isinstance(item, str) or not Decimal(item).is_finite():
                    return False
            if not decimal_fields(item):
                return False
    elif isinstance(value, list):
        return all(decimal_fields(item) for item in value)
    return True


async def approve(context, params):
    global elicitations
    elicitations += 1
    if options.manual_approval:
        print("PUSH TAN: approve in photoTAN; enter approved only after approval, or cancel", flush=True)
        answer = await asyncio.to_thread(sys.stdin.readline)
        if answer.strip().lower() != "approved":
            return ElicitResult(action="decline")
    else:
        print(f"PUSH TAN: approve in photoTAN now; one confirmation in {options.wait} seconds", flush=True)
        await asyncio.sleep(options.wait)
    return ElicitResult(action="accept", content={"approved": True})


def params():
    return StdioServerParameters(
        command=options.server_command,
        cwd=ROOT,
        env={
            "COMDIRECT_ENV_FILE": "",
            "COMDIRECT_MCP_UNMASK_IBANS": "false",
            "COMDIRECT_MCP_MASK_NAMES": "true",
        },
    )


async def invoke(client, name, args=None, error=False, allow_missing=False):
    calls.add(name)
    try:
        result = await client.call_tool(name, args or {})
    except Exception as exc:
        check(name + ": expected protocol error" if error else name + ": unexpected " + type(exc).__name__, error)
        return None
    if error:
        check(name + ": expected tool error", result.is_error)
        return result
    if allow_missing and result.is_error:
        category = tool_error_diagnostic(getattr(c, "text", "") for c in result.content)
        if category == "api_http_404":
            print("SKIP " + name + ": bank returned HTTP 404 for available document", flush=True)
            return None
    if not check(name + ": success and output schema accepted", not result.is_error):
        category = tool_error_diagnostic(getattr(c, "text", "") for c in result.content)
        print("DIAG " + name + ": " + category, flush=True)
        return None
    data = result.structured_content
    if data is not None:
        check(name + ": no null fields", compact(data))
        check(name + ": finite decimal strings", decimal_fields(data))
    return data if data is not None else result


async def catalog(client, label):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    check(label + ": expected tool catalog", set(tools) == EXPECTED)
    check(label + ": input schemas for all tools", all(t.input_schema for t in tools.values()))
    check(
        label + ": output schemas on all structured tools",
        all(t.output_schema for n, t in tools.items() if n != "download_document"),
    )
    check(
        label + ": truthful read-only annotations",
        all(tools[n].annotations.read_only_hint is (n in READS) for n in EXPECTED),
    )
    check(label + ": annotations on every tool", all(t.annotations is not None for t in tools.values()))
    return tools


async def offline():
    for mode in ("auto", "legacy"):
        with open(os.devnull, "w") as errlog:
            async with Client(stdio_client(params(), errlog=errlog), mode=mode) as client:
                await catalog(client, "stdio " + mode)
                for name, args in (
                    ("list_accounts", {}),
                    ("list_transactions", {"account_id": "synthetic"}),
                    ("summarize_transactions", {"account_id": "synthetic", "min_booking_date": "2026-01-01"}),
                    ("list_cards", {}),
                    ("list_depots", {}),
                    ("get_depot_positions", {"depot_id": "synthetic"}),
                    ("list_documents", {}),
                    ("list_depot_transactions", {"depot_id": "synthetic"}),
                    ("get_wealth_overview", {}),
                    ("get_instrument", {"identifier": "synthetic"}),
                    ("download_document", {"document_id": "synthetic", "mime_type": "application/pdf"}),
                    ("get_account_balance", {"account_id": "synthetic"}),
                    ("get_depot_position", {"depot_id": "synthetic", "position_id": "synthetic"}),
                    ("summarize_portfolio", {"depot_id": "synthetic"}),
                    ("get_order_dimensions", {"identifier": "synthetic"}),
                    ("list_orders", {"depot_id": "synthetic"}),
                    ("get_order", {"order_id": "synthetic"}),
                    ("get_document_cover", {"document_id": "synthetic"}),
                    ("extract_document_text", {"document_id": "synthetic"}),
                ):
                    await invoke(client, name, args, error=True)
                await invoke(client, "logout")


async def live():
    calls.clear()
    today = date.today()
    since = (today - timedelta(days=30)).isoformat()
    end = today.isoformat()
    with open(os.devnull, "w") as errlog:
        async with Client(
            stdio_client(params(), errlog=errlog),
            mode="auto",
            elicitation_callback=approve,
            read_timeout_seconds=300 if options.manual_approval else 120,
        ) as client:
            await catalog(client, "LIVE stdio")
            logged_in = False
            try:
                login = await invoke(client, "login")
                if not login or login.get("status") != "logged_in":
                    print("STOP: login failed; no retry", flush=True)
                    return
                logged_in = True
                check("login: exactly one elicitation approval", elicitations == 1)
                started = asyncio.get_running_loop().time()
                accounts = await invoke(client, "list_accounts")
                cards = await invoke(client, "list_cards")
                if cards:
                    check(
                        "cards: suffix never exceeds four digits",
                        all(len(c.get("number_suffix", "")) <= 4 for c in cards["cards"]),
                    )
                for index, account in enumerate((accounts or {}).get("accounts", [])):
                    print("REVIEW account index " + str(index), flush=True)
                    check(
                        "accounts: display number and IBAN masked",
                        ("number" not in account or account["number"].startswith("..."))
                        and ("iban" not in account or "**..." in account["iban"]),
                    )
                    account_id = account.get("id")
                    if not account_id:
                        check("accounts: actionable identifier available", False)
                        continue
                    single = await invoke(client, "get_account_balance", {"account_id": account_id})
                    if single:
                        check(
                            "single account: identity and currency agree",
                            single.get("id") == account_id and single.get("currency") == account.get("currency"),
                        )
                    args = {"account_id": account_id, "min_booking_date": since, "max_booking_date": end, "limit": 250}
                    txdata = await invoke(client, "list_transactions", args)
                    verbose = await invoke(client, "list_transactions", {**args, "verbose": True})
                    if txdata and verbose:
                        txs, detail = txdata["transactions"], verbose["transactions"]
                        check("transactions: count matches array", txdata["count"] == len(txs))
                        check(
                            "transactions: date range respected",
                            all(since <= t["booking_date"] <= end for t in txs if "booking_date" in t),
                        )
                        check(
                            "transactions: direction matches sign",
                            all(
                                t.get("direction")
                                == ("in" if Decimal(t["amount"]) > 0 else "out" if Decimal(t["amount"]) < 0 else None)
                                for t in txs
                                if "amount" in t
                            ),
                        )
                        check(
                            "transactions: compact equals subset of verbose",
                            len(txs) == len(detail)
                            and all(
                                all(d.get(k) == v for k, v in t.items()) for t, d in zip(txs, detail, strict=True)
                            ),
                        )
                        check(
                            "transactions: verbose IBAN masking",
                            all("**..." in t["counterparty_iban"] for t in detail if "counterparty_iban" in t),
                        )
                        check(
                            "transactions: pseudonym masking",
                            all(t["counterparty"].startswith("Counterparty ") for t in txs if "counterparty" in t),
                        )
                        check(
                            "transactions: no complete numbered SEPA sequence",
                            not any(re.match(r"^01.{35}02", t.get("purpose", "")) for t in txs),
                        )
                        print(
                            "INFO transaction count="
                            + str(len(txs))
                            + ", missing counterparty="
                            + str(sum("counterparty" not in t for t in txs))
                            + ", missing purpose="
                            + str(sum("purpose" not in t for t in txs)),
                            flush=True,
                        )
                        print(
                            "INFO compact/verbose response characters="
                            + str(len(json.dumps(txdata)))
                            + "/"
                            + str(len(json.dumps(verbose))),
                            flush=True,
                        )
                        tiny = await invoke(client, "list_transactions", {**args, "limit": 1})
                        if tiny and txs:
                            check(
                                "transactions: limit and truncation",
                                tiny["count"] == 1 and tiny["truncated"] == (len(txs) > 1 or txdata["truncated"]),
                            )
                            if tiny.get("next_offset") is not None:
                                tail = await invoke(
                                    client, "list_transactions", {**args, "offset": tiny["next_offset"]}
                                )
                                if tail:
                                    check(
                                        "transactions: continuation matches filtered sequence",
                                        tail["transactions"][: len(txs) - 1] == txs[1:],
                                    )
                        summaries = []
                        for group_by in ("month", "counterparty", "type"):
                            summary = await invoke(
                                client,
                                "summarize_transactions",
                                {
                                    "account_id": account_id,
                                    "min_booking_date": since,
                                    "max_booking_date": end,
                                    "group_by": group_by,
                                    "max_groups": 2,
                                },
                            )
                            if summary:
                                summaries.append(summary)
                                groups = summary["groups"]
                                check(
                                    "summary " + group_by + ": bounded groups and consistent group totals",
                                    len(groups) <= 2
                                    and sum(g["count"] for g in groups) == summary["count"]
                                    and all(
                                        sum((Decimal(g[k]) for g in groups), Decimal(0)) == Decimal(summary[k])
                                        for k in ("income", "expenses", "net")
                                    )
                                    and Decimal(summary["income"]) + Decimal(summary["expenses"])
                                    == Decimal(summary["net"]),
                                )
                                check(
                                    "summary " + group_by + ": other group when truncated",
                                    not summary["groups_truncated"] or groups[-1]["key"] == "(other)",
                                )
                                if not txdata["truncated"] and not summary["transactions_truncated"]:
                                    check(
                                        "summary " + group_by + ": matches independent transaction totals",
                                        summary["count"] == len(txs)
                                        and sum((Decimal(t["amount"]) for t in txs), Decimal(0))
                                        == Decimal(summary["net"]),
                                    )
                        check(
                            "summary: grouping preserves totals",
                            len(summaries) == 3
                            and all(
                                tuple(s[k] for k in ("count", "income", "expenses", "net"))
                                == tuple(summaries[0][k] for k in ("count", "income", "expenses", "net"))
                                for s in summaries
                            ),
                        )
                    for direction, expected in (("INCOMING", "in"), ("OUTGOING", "out")):
                        filtered = await invoke(
                            client, "list_transactions", {**args, "transaction_direction": direction}
                        )
                        if filtered:
                            check(
                                "transactions: " + direction + " filter",
                                all(t.get("direction") in (expected, None) for t in filtered["transactions"]),
                            )
                    pending = await invoke(
                        client, "list_transactions", {"account_id": account_id, "transaction_state": "NOTBOOKED"}
                    )
                    if pending:
                        check(
                            "transactions: pending flag",
                            all(t.get("pending") is True for t in pending["transactions"]),
                        )
                wealth = await invoke(client, "get_wealth_overview")
                detailed_wealth = await invoke(client, "get_wealth_overview", {"verbose": True})
                if wealth and detailed_wealth:
                    check("wealth: count matches product array", wealth["count"] == len(wealth["products"]))
                    check("wealth: all reported products returned", wealth.get("products_complete", True))
                    check(
                        "wealth: compact agrees with verbose",
                        len(wealth["products"]) == len(detailed_wealth["products"])
                        and all(
                            p == {k: v for k, v in d.items() if k in p}
                            for p, d in zip(wealth["products"], detailed_wealth["products"], strict=True)
                        ),
                    )
                    check(
                        "wealth: display numbers masked",
                        all(
                            "display_id" not in p or p["display_id"].startswith("...") or len(p["display_id"]) <= 4
                            for p in wealth["products"]
                        ),
                    )
                    print(
                        "INFO wealth products="
                        + str(wealth["count"])
                        + ", missing values="
                        + str(wealth["missing_value_count"]),
                        flush=True,
                    )
                    if (
                        wealth.get("total_balance_eur") is not None
                        and wealth.get("products_complete") is True
                        and all(p.get("currency") == "EUR" and "balance" in p for p in wealth["products"])
                    ):
                        check(
                            "wealth: EUR aggregate agrees with product balances",
                            sum((Decimal(p["balance"]) for p in wealth["products"]), Decimal(0))
                            == Decimal(wealth["total_balance_eur"]),
                        )
                instruments_seen = set()
                depots = await invoke(client, "list_depots")
                for index, depot in enumerate((depots or {}).get("depots", [])):
                    print("REVIEW depot index " + str(index), flush=True)
                    check(
                        "depots: display number masked",
                        "display_id" not in depot or depot["display_id"].startswith("..."),
                    )
                    if depot.get("id"):
                        orders = await invoke(client, "list_orders", {"depot_id": depot["id"], "limit": 1})
                        all_orders = await invoke(
                            client, "list_orders", {"depot_id": depot["id"], "limit": 1000, "verbose": True}
                        )
                        if orders and all_orders:
                            check(
                                "orders: count and first page agree",
                                orders["count"] == len(orders["orders"])
                                and orders["orders"]
                                == [
                                    {k: v for k, v in row.items() if k in orders["orders"][i]}
                                    for i, row in enumerate(all_orders["orders"][:1])
                                ],
                            )
                            if orders.get("next_offset") is not None:
                                tail = await invoke(
                                    client,
                                    "list_orders",
                                    {"depot_id": depot["id"], "offset": 1, "limit": 1, "verbose": True},
                                )
                                if tail:
                                    check(
                                        "orders: continuation matches sequence",
                                        tail["orders"] == all_orders["orders"][1:2],
                                    )
                            order_id = next((o.get("id") for o in all_orders["orders"] if o.get("id")), None)
                            if order_id:
                                await invoke(client, "get_order", {"order_id": order_id, "verbose": True})
                                side = next(
                                    (o.get("side") for o in all_orders["orders"] if o.get("side") in {"BUY", "SELL"}),
                                    None,
                                )
                                if side:
                                    filtered = await invoke(
                                        client, "list_orders", {"depot_id": depot["id"], "side": side}
                                    )
                                    if filtered:
                                        check(
                                            "orders: side filter respected",
                                            all(o.get("side") == side for o in filtered["orders"]),
                                        )
                            else:
                                print(
                                    "SKIP successful get_order: no existing order id; checking missing-id error",
                                    flush=True,
                                )
                                await invoke(
                                    client, "get_order", {"order_id": "__mcp_live_missing_order__"}, error=True
                                )
                        movements = await invoke(
                            client, "list_depot_transactions", {"depot_id": depot["id"], "limit": 1}
                        )
                        if movements:
                            check(
                                "depot transactions: page count",
                                movements["count"] == len(movements["transactions"]) <= 1,
                            )
                            if movements.get("next_offset") is not None:
                                movement_tail = await invoke(
                                    client,
                                    "list_depot_transactions",
                                    {"depot_id": depot["id"], "offset": movements["next_offset"], "verbose": True},
                                )
                                if movement_tail:
                                    check("depot transactions: continuation offset", movement_tail["offset"] == 1)
                            dated = await invoke(
                                client,
                                "list_depot_transactions",
                                {"depot_id": depot["id"], "min_booking_date": since, "max_booking_date": end},
                            )
                            if dated:
                                check(
                                    "depot transactions: date bounds",
                                    all(since <= tx.get("booking_date", "") <= end for tx in dated["transactions"]),
                                )
                        positions = await invoke(client, "get_depot_positions", {"depot_id": depot["id"]})
                        if positions:
                            detailed = await invoke(
                                client, "get_depot_positions", {"depot_id": depot["id"], "verbose": True}
                            )
                            if detailed:
                                for holding in detailed["positions"]:
                                    if holding.get("position_id"):
                                        one = await invoke(
                                            client,
                                            "get_depot_position",
                                            {
                                                "depot_id": depot["id"],
                                                "position_id": holding["position_id"],
                                                "verbose": True,
                                            },
                                        )
                                        if one:
                                            check(
                                                "single position: identity and quantity agree",
                                                one.get("position_id") == holding["position_id"]
                                                and one.get("quantity") == holding.get("quantity"),
                                            )
                                check(
                                    "positions: compact equals subset of verbose",
                                    len(positions["positions"]) == len(detailed["positions"])
                                    and all(
                                        p == {k: v for k, v in d.items() if k in p}
                                        for p, d in zip(positions["positions"], detailed["positions"], strict=True)
                                    ),
                                )
                                print(
                                    "INFO positions compact/verbose response characters="
                                    + str(len(json.dumps(positions)))
                                    + "/"
                                    + str(len(json.dumps(detailed))),
                                    flush=True,
                                )
                            for holding in positions["positions"]:
                                identifier = holding.get("isin") or holding.get("wkn")
                                if not identifier or identifier in instruments_seen:
                                    continue
                                instruments_seen.add(identifier)
                                security = await invoke(client, "get_instrument", {"identifier": identifier})
                                security_details = await invoke(
                                    client, "get_instrument", {"identifier": identifier, "verbose": True}
                                )
                                await invoke(client, "get_order_dimensions", {"identifier": identifier})
                                await invoke(
                                    client,
                                    "get_instrument",
                                    {"identifier": identifier, "include_order_dimensions": True},
                                )
                                if security is not None and security_details is not None:
                                    check(
                                        "instrument: compact equals subset of verbose",
                                        security == {k: v for k, v in security_details.items() if k in security},
                                    )
                                    check(
                                        "instrument: requested security resolved",
                                        security.get("isin") == identifier or security.get("wkn") == identifier,
                                    )
                            check("positions: requested depot identifier", positions["depot_id"] == depot["id"])
                            portfolio = await invoke(
                                client, "summarize_portfolio", {"depot_id": depot["id"], "limit": 1}
                            )
                            if portfolio:
                                check(
                                    "portfolio: all positions counted",
                                    portfolio["count"] == len(positions["positions"]),
                                )
                                for group in portfolio["currencies"]:
                                    source = [
                                        p
                                        for p in positions["positions"]
                                        if p.get("current_value_currency") == group["currency"]
                                    ]
                                    total = sum((Decimal(p["current_value"]) for p in source), Decimal(0))
                                    check("portfolio: independent value total", Decimal(group["total_value"]) == total)
                                    check(
                                        "portfolio: remainder conserves value",
                                        sum((Decimal(p["value"]) for p in group["positions"]), Decimal(0))
                                        + Decimal(group["omitted_value"])
                                        == total,
                                    )
                                    if total:
                                        check(
                                            "portfolio: weights sum to 100",
                                            abs(
                                                sum(
                                                    (Decimal(p["weight_percent"]) for p in group["positions"]),
                                                    Decimal(0),
                                                )
                                                + Decimal(group["omitted_weight_percent"])
                                                - 100
                                            )
                                            < Decimal("0.00000001"),
                                        )
                            check(
                                "positions: no unresolved special units",
                                all(
                                    p.get("quantity_unit") not in ("XXX", "XXC", "XXM", "XXP", "XXU")
                                    for p in positions["positions"]
                                ),
                            )
                            print(
                                "INFO positions="
                                + str(len(positions["positions"]))
                                + ", missing instrument names="
                                + str(sum("instrument_name" not in p for p in positions["positions"])),
                                flush=True,
                            )
                docs = await invoke(client, "list_documents", {"paging_count": 10})
                next_docs = await invoke(client, "list_documents", {"paging_first": 10, "paging_count": 1})
                if docs and next_docs:
                    check(
                        "documents: continuation agrees with next page",
                        docs["has_more"] == bool(next_docs["documents"]),
                    )
                    check(
                        "documents: next index matches page",
                        docs.get("next_index") == (10 if docs["has_more"] else None),
                    )
                if docs:
                    check("documents: page bound and count", docs["count"] == len(docs["documents"]) <= 10)
                    pdf = next(
                        (
                            d
                            for d in docs["documents"]
                            if d.get("already_read") is True
                            and d.get("mime_type") == "application/pdf"
                            and d.get("document_id")
                        ),
                        None,
                    )
                    if pdf:
                        await invoke(
                            client,
                            "get_document_cover",
                            {"document_id": pdf["document_id"], "max_chars": 500},
                            allow_missing=True,
                        )
                        text = await invoke(
                            client,
                            "extract_document_text",
                            {"document_id": pdf["document_id"], "max_pages": 1, "max_chars": 500},
                        )
                        if text:
                            check(
                                "document text: bounded output and untrusted notice",
                                len(text["text"]) <= 500
                                and "untrusted" in text["notice"]
                                and text["pages_processed"] == 1,
                            )
                            if text.get("next_page") is not None:
                                await invoke(
                                    client,
                                    "extract_document_text",
                                    {
                                        "document_id": pdf["document_id"],
                                        "first_page": text["next_page"],
                                        "max_pages": 1,
                                        "max_chars": 500,
                                    },
                                )
                        result = await invoke(
                            client,
                            "download_document",
                            {"document_id": pdf["document_id"], "mime_type": "application/pdf"},
                        )
                        if result:
                            resource = result.content[0].resource
                            blob = base64.b64decode(resource.blob, validate=True)
                            check(
                                "download: PDF resource, URI and size",
                                resource.mime_type == "application/pdf"
                                and resource.uri == "comdirect://documents/" + pdf["document_id"]
                                and blob.startswith(b"%PDF")
                                and len(blob) <= 10 * 1024 * 1024,
                            )
                            del blob, result
                    else:
                        print("SKIP download: no already-read PDF in page", flush=True)
                for name, args in (
                    ("list_transactions", {"account_id": "synthetic"}),
                    ("list_transactions", {"account_id": "synthetic", "limit": 0}),
                    ("list_transactions", {"account_id": "synthetic", "min_booking_date": "invalid"}),
                    ("list_transactions", {"account_id": "synthetic", "transaction_state": "invalid"}),
                    (
                        "summarize_transactions",
                        {"account_id": "synthetic", "min_booking_date": end, "max_booking_date": since},
                    ),
                    (
                        "summarize_transactions",
                        {"account_id": "synthetic", "min_booking_date": since, "max_groups": 1},
                    ),
                    ("list_documents", {"paging_first": -1}),
                    ("list_documents", {"paging_count": 1001}),
                    ("get_depot_positions", {}),
                    ("download_document", {}),
                ):
                    await invoke(client, name, args, error=True)
                if options.refresh_wait:
                    print("WAIT token expiry: keep same subprocess and session; no new login", flush=True)
                while asyncio.get_running_loop().time() - started < options.refresh_wait:
                    await asyncio.sleep(
                        min(30, max(0, options.refresh_wait - (asyncio.get_running_loop().time() - started)))
                    )
                    print(
                        "INFO same session elapsed seconds=" + str(int(asyncio.get_running_loop().time() - started)),
                        flush=True,
                    )
                await invoke(client, "list_accounts")
                check("all data tools before logout exercised", calls == EXPECTED - {"logout"})
            finally:
                await invoke(client, "logout")
                result = await invoke(client, "list_accounts", error=True)
                check(
                    "logout: following data call requires login",
                    result is not None
                    and result.is_error
                    and any("login" in getattr(c, "text", "") for c in result.content),
                )
                await invoke(client, "logout")
                if logged_in:
                    check("logout: all tools exercised", calls == EXPECTED)
                else:
                    print("SKIP data-tool coverage: login did not complete", flush=True)
    print("RESULT failures=" + str(failures), flush=True)


async def depot_live():
    calls.clear()
    with open(os.devnull, "w") as errlog:
        async with Client(
            stdio_client(params(), errlog=errlog),
            mode="auto",
            elicitation_callback=approve,
            read_timeout_seconds=300 if options.manual_approval else 120,
        ) as client:
            try:
                login = await invoke(client, "login")
                if not login or login.get("status") != "logged_in":
                    print("STOP: login failed; no retry", flush=True)
                    return
                check("login: exactly one elicitation approval", elicitations == 1)
                depots = await invoke(client, "list_depots")
                today = date.today()
                for depot in (depots or {}).get("depots", []):
                    depot_id = depot.get("id")
                    if not depot_id:
                        continue
                    args = {"depot_id": depot_id, "limit": 1}
                    first = await invoke(client, "list_depot_transactions", args)
                    since = (today - timedelta(days=30)).isoformat()
                    dated = await invoke(
                        client,
                        "list_depot_transactions",
                        {
                            **args,
                            "min_booking_date": since,
                            "max_booking_date": today.isoformat(),
                            "verbose": True,
                        },
                    )
                    if dated:
                        check(
                            "depot transactions: date range respected",
                            all(
                                since <= tx.get("booking_date", "") <= today.isoformat()
                                for tx in dated["transactions"]
                            ),
                        )
                    whole = await invoke(client, "list_depot_transactions", {"depot_id": depot_id, "limit": 2000})
                    if first and whole:
                        check(
                            "depot transactions: first page and truncation agree",
                            first["transactions"] == whole["transactions"][:1]
                            and first["truncated"] == (len(whole["transactions"]) > 1 or whole["truncated"]),
                        )
                        print("INFO depot movement count=" + str(whole["count"]), flush=True)
                    positions = await invoke(client, "get_depot_positions", {"depot_id": depot_id})
                    isin = next((p["isin"] for p in (positions or {}).get("positions", []) if p.get("isin")), None)
                    if isin:
                        filtered = await invoke(
                            client, "list_depot_transactions", {**args, "isin": isin, "verbose": True}
                        )
                        if filtered:
                            check(
                                "depot transactions: reported ISIN matches filter",
                                all(tx.get("isin", isin) == isin for tx in filtered["transactions"]),
                            )
                    if first and first.get("next_offset") is not None:
                        tail = await invoke(
                            client, "list_depot_transactions", {**args, "offset": first["next_offset"]}
                        )
                        if tail and whole:
                            check(
                                "depot transactions: continuation agrees with complete sequence",
                                tail["transactions"] == whole["transactions"][1:2],
                            )
            finally:
                await invoke(client, "logout")
                await invoke(client, "list_accounts", error=True)
                await invoke(client, "logout")
    print("RESULT failures=" + str(failures), flush=True)


async def remaining_live():
    calls.clear()
    with open(os.devnull, "w") as errlog:
        async with Client(
            stdio_client(params(), errlog=errlog), mode="auto", elicitation_callback=approve, read_timeout_seconds=300
        ) as client:
            try:
                result = await invoke(client, "login")
                if not result or result.get("status") != "logged_in":
                    print("STOP: login failed; no retry", flush=True)
                    return
                check("login: exactly one approval", elicitations == 1)
                accounts = await invoke(client, "list_accounts")
                for account in (accounts or {}).get("accounts", []):
                    if account.get("id"):
                        await invoke(client, "get_account_balance", {"account_id": account["id"]})
                depots = await invoke(client, "list_depots")
                seen = set()
                for depot in (depots or {}).get("depots", []):
                    depot_id = depot.get("id")
                    if not depot_id:
                        continue
                    data = await invoke(client, "get_depot_positions", {"depot_id": depot_id, "verbose": True})
                    for position in (data or {}).get("positions", []):
                        if position.get("position_id"):
                            one = await invoke(
                                client,
                                "get_depot_position",
                                {"depot_id": depot_id, "position_id": position["position_id"], "verbose": True},
                            )
                            if one:
                                check(
                                    "single position: identity and quantity agree",
                                    one.get("position_id") == position["position_id"]
                                    and one.get("quantity") == position.get("quantity"),
                                )
                        identifier = position.get("isin") or position.get("wkn")
                        if identifier and identifier not in seen:
                            seen.add(identifier)
                            dimensions = await invoke(client, "get_order_dimensions", {"identifier": identifier})
                            embedded = await invoke(
                                client, "get_instrument", {"identifier": identifier, "include_order_dimensions": True}
                            )
                            if dimensions:
                                check(
                                    "dimensions: count matches venue list",
                                    dimensions.get("count") == len(dimensions.get("venues", [])),
                                )
                            if dimensions and embedded and embedded.get("order_dimensions"):
                                check(
                                    "dimensions: venue identities agree with instrument projection",
                                    {v.get("id") for v in dimensions.get("venues", [])}
                                    == {v.get("id") for v in embedded["order_dimensions"].get("venues", [])},
                                )
                    portfolio = await invoke(client, "summarize_portfolio", {"depot_id": depot_id, "limit": 1})
                    if portfolio and data:
                        check("portfolio: all positions counted", portfolio["count"] == len(data["positions"]))
                        for group in portfolio["currencies"]:
                            total = sum(
                                (
                                    Decimal(p["current_value"])
                                    for p in data["positions"]
                                    if p.get("current_value_currency") == group["currency"]
                                ),
                                Decimal(0),
                            )
                            check(
                                "portfolio: independent total and remainder",
                                Decimal(group["total_value"]) == total
                                and sum((Decimal(p["value"]) for p in group["positions"]), Decimal(0))
                                + Decimal(group["omitted_value"])
                                == total,
                            )
                    orders = await invoke(client, "list_orders", {"depot_id": depot_id, "verbose": True})
                    order_id = next((o.get("id") for o in (orders or {}).get("orders", []) if o.get("id")), None)
                    if order_id:
                        await invoke(client, "get_order", {"order_id": order_id, "verbose": True})
                    else:
                        print("SKIP successful get_order: no existing order id; missing-id error checked", flush=True)
                        await invoke(client, "get_order", {"order_id": "__mcp_live_missing_order__"}, error=True)
                docs = await invoke(client, "list_documents", {"paging_count": 50})
                read_docs = [
                    d
                    for d in (docs or {}).get("documents", [])
                    if d.get("already_read") is True and d.get("document_id")
                ]
                read_docs.sort(key=lambda d: d.get("advertisement") is not True)
                for document in read_docs[:2]:
                    await invoke(
                        client,
                        "get_document_cover",
                        {"document_id": document["document_id"], "max_chars": 500},
                        allow_missing=True,
                    )
                pdf = next((d for d in read_docs if d.get("mime_type") == "application/pdf"), None)
                if pdf:
                    text = await invoke(
                        client,
                        "extract_document_text",
                        {"document_id": pdf["document_id"], "max_pages": 1, "max_chars": 500},
                    )
                    if text:
                        check(
                            "PDF: bounded text and untrusted notice",
                            len(text["text"]) <= 500 and "untrusted" in text["notice"],
                        )
                else:
                    print("SKIP PDF extraction: no already-read PDF", flush=True)
            finally:
                await invoke(client, "logout")
                await invoke(client, "list_accounts", error=True)
                await invoke(client, "logout")
    print("RESULT failures=" + str(failures), flush=True)


async def main():
    await offline()
    if not options.offline:
        if options.remaining_only:
            await remaining_live()
        elif options.depot_only:
            await depot_live()
        else:
            await live()
    print("FINAL failures=" + str(failures), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as error:
        print("ABORT " + type(error).__name__ + " (details suppressed)", flush=True)
        sys.exit(1)
