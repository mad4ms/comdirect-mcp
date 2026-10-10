"""
Live check of the MCP server against the real comdirect API.

Runs every tool once through an in-process MCP client and prints only structure (counts, which
fields are set, format checks) - never amounts, ids, names, IBANs or payment texts. Nothing is
written to disk; a downloaded document is checked for its file signature and discarded.

Uses configured credentials (environment, OS keychain, or explicit COMDIRECT_ENV_FILE).
Triggers ONE push TAN: approve it in the photoTAN app while the
script waits. There is deliberately no retry, repeated failed logins can lock the access.

    uv run python scripts/live_check.py [seconds-to-wait-for-approval]
"""

import asyncio
import base64
import json
import logging
import re
import sys
import uuid
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import requests
from mcp.client import Client
from mcp.types import ElicitResult

from comdirect_mcp import server
from comdirect_mcp.credentials import load_credentials
from comdirect_mcp.utils import request_id

WAIT = int(sys.argv[1]) if len(sys.argv) > 1 else 20
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    failures += not ok
    print(f"  {'OK  ' if ok else 'FAIL'} {label}", flush=True)


def is_decimal(value) -> bool:
    try:
        Decimal(value)
    except (InvalidOperation, TypeError):
        return False
    return True


def set_fields(obj: dict) -> str:
    """Names of the non-empty fields (one level into nested objects), without values."""
    names = []
    for key, value in obj.items():
        if isinstance(value, dict):
            inner = sorted(k for k, v in value.items() if v not in (None, ""))
            if inner:
                names.append(f"{key}{{{','.join(inner)}}}")
        elif value not in (None, "", False):
            names.append(key)
    return ",".join(sorted(names))


def print_mapping_statistics(transactions) -> None:
    """How the API fills purposes and party roles - counts and categories only, no values."""
    numbered = sum(1 for tx in transactions if (tx.purpose_raw or "").startswith("01"))
    references = sum(
        1 for tx in transactions if re.search(r"End-to-End-Ref|Mandatsref|ubiger-ID", tx.purpose_raw or "")
    )
    shortened = sum(
        1 for tx in transactions if tx.purpose and tx.purpose_raw and len(tx.purpose) < len(tx.purpose_raw)
    )
    print(
        f"  INFO purposes: {numbered} numbered, {references} with reference block, {shortened} shortened", flush=True
    )
    roles = Counter()
    for tx in transactions:
        filled = "+".join(
            role for role in ("remitter", "debtor", "creditor") if getattr(tx, role) and getattr(tx, role).holder_name
        )
        chosen = next(
            (role for role in ("remitter", "debtor", "creditor") if getattr(tx, role) is tx.counterparty), "none"
        )
        roles[(tx.type, tx.direction, filled or "-", chosen)] += 1
    for (tx_type, direction, filled, chosen), count in sorted(roles.items(), key=lambda item: -item[1]):
        print(
            f"  INFO {count:3d}x {tx_type} {direction}: roles with names [{filled}] -> counterparty {chosen}",
            flush=True,
        )


def rejected_status(access_token: str) -> int:
    """Calls the accounts endpoint with a token that should be revoked; returns only the HTTP status."""
    response = requests.get(
        "https://api.comdirect.de/api/banking/clients/user/v2/accounts/balances",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "x-http-request-info": json.dumps(
                {"clientRequestId": {"sessionId": uuid.uuid4().hex, "requestId": request_id()}}
            ),
        },
        timeout=30,
    )
    return response.status_code


def refresh_status_of(refresh_token: str) -> int:
    """Tries a refresh with a token that should be revoked; returns only the HTTP status."""
    credentials = load_credentials()
    response = requests.post(
        "https://api.comdirect.de/oauth/token",
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    return response.status_code


async def approve(context, params):
    print("  [dialog] comdirect push TAN requested", flush=True)
    print(f"  [dialog] confirming automatically in {WAIT}s - approve the push in the app now", flush=True)
    await asyncio.sleep(WAIT)
    return ElicitResult(action="accept", content={"approved": True})


async def call(client: Client, name: str, args: dict | None = None):
    try:
        result = await client.call_tool(name, args or {})
    except Exception as e:  # e.g. the client rejecting output that violates the tool's output schema
        check(f"{name}: {type(e).__name__} (details suppressed)", False)
        return None
    if result.is_error:
        check(f"{name}: tool error (details suppressed)", False)
        return None
    return result.structured_content if result.structured_content is not None else result


async def main() -> None:
    async with Client(server.mcp, elicitation_callback=approve) as client:
        print("== login", flush=True)
        if not await call(client, "login"):
            sys.exit(1)

        print("== list_accounts", flush=True)
        data = await call(client, "list_accounts")
        accounts = data["accounts"] if data else []
        print(f"  {len(accounts)} account(s), types: {sorted(a.get('type') or '?' for a in accounts)}", flush=True)
        for i, account in enumerate(accounts):
            check(f"account {i}: balance is a decimal", "balance" not in account or is_decimal(account["balance"]))
            check(f"account {i}: has type name", bool(account.get("type_name")))
            check(f"account {i}: number masked", "number" not in account or account["number"].startswith("..."))
            print(f"       fields: {set_fields(account)}", flush=True)

        if accounts:
            account_id = next((a.get("id") for a in accounts if a.get("id")), None)
            if account_id is None:
                check("account id available for further checks", False)
                sys.exit(1)
            since = (date.today() - timedelta(days=30)).isoformat()
            print("== list_transactions (BOOKED, last 30 days, limit 20, compact)", flush=True)
            args = {"account_id": account_id, "min_booking_date": since, "limit": 20}
            data = await call(client, "list_transactions", args)
            if data:
                txs = data["transactions"]
                print(f"  {data['count']} transaction(s), truncated={data['truncated']}", flush=True)
                check("amounts are decimals", all("amount" not in t or is_decimal(t["amount"]) for t in txs))
                check(
                    "booking dates are ISO dates",
                    all(ISO_DATE.match(t["booking_date"]) for t in txs if "booking_date" in t),
                )
                check(
                    "booking dates within the filter",
                    all(t["booking_date"] >= since for t in txs if "booking_date" in t),
                )
                check("no null fields in compact view", all(None not in t.values() for t in txs))
                check(
                    "direction matches the sign",
                    all(
                        t.get("direction")
                        == ("in" if Decimal(t["amount"]) > 0 else "out" if Decimal(t["amount"]) < 0 else None)
                        for t in txs
                        if "amount" in t
                    ),
                )
                with_counterparty = sum(1 for t in txs if t.get("counterparty"))
                print(f"  INFO counterparty set for {with_counterparty}/{len(txs)}", flush=True)
                purposes = [t["purpose"] for t in txs if t.get("purpose")]
                check(
                    "no complete numbered SEPA line sequence left in purposes",
                    not any(re.match(r"^01.{35}02", p) for p in purposes),
                )
                size = sum(len(json.dumps(t)) for t in txs) // max(len(txs), 1)
                print(f"  INFO average size per transaction: {size} characters", flush=True)

            print("== list_transactions (verbose)", flush=True)
            data = await call(client, "list_transactions", {**args, "verbose": True})
            if data:
                ibans = [t["counterparty_iban"] for t in data["transactions"] if t.get("counterparty_iban")]
                check(f"{len(ibans)} counterparty IBAN(s) masked", all("**..." in i for i in ibans))
                size = sum(len(json.dumps(t)) for t in data["transactions"]) // max(len(data["transactions"]), 1)
                print(f"  INFO average size per transaction: {size} characters", flush=True)

            print("== mapping statistics (counts only)", flush=True)
            raw = list(server._state.logged_in_client().iter_all_transactions(account_id, min_booking_date=since))
            print_mapping_statistics(raw)

            print("== summarize_transactions (last 90 days)", flush=True)
            since_90 = (date.today() - timedelta(days=90)).isoformat()
            for group_by in ("month", "counterparty", "type"):
                summary = await call(
                    client,
                    "summarize_transactions",
                    {"account_id": account_id, "min_booking_date": since_90, "group_by": group_by},
                )
                if summary:
                    consistent = Decimal(summary["income"]) + Decimal(summary["expenses"]) == Decimal(summary["net"])
                    group_count = sum(g["count"] for g in summary["groups"])
                    check(
                        f"{group_by}: {len(summary['groups'])} group(s), totals consistent",
                        consistent and group_count == summary["count"],
                    )

            print("== list_transactions (NOTBOOKED)", flush=True)
            data = await call(
                client, "list_transactions", {"account_id": account_id, "transaction_state": "NOTBOOKED"}
            )
            if data:
                print(f"  {data['count']} pending transaction(s)", flush=True)

        print("== list_cards", flush=True)
        data = await call(client, "list_cards")
        if data is not None:
            cards = data["cards"]
            print(f"  {len(cards)} card(s)", flush=True)
            check("card balances are decimals", all(is_decimal(c["balance"]) for c in cards if "balance" in c))
            for card in cards:
                print(f"       fields: {set_fields(card)}", flush=True)

        print("== list_depots / get_depot_positions", flush=True)
        data = await call(client, "list_depots")
        depots = data["depots"] if data else []
        print(f"  {len(depots)} depot(s)", flush=True)
        if depots and depots[0].get("id"):
            data = await call(client, "get_depot_positions", {"depot_id": depots[0]["id"]})
            if data:
                positions = data["positions"]
                print(f"  {len(positions)} position(s)", flush=True)
                check(
                    "depot value is a decimal",
                    "current_value" not in data["balance"] or is_decimal(data["balance"]["current_value"]),
                )
                check(
                    "position values are decimals",
                    all(is_decimal(p["current_value"]) for p in positions if "current_value" in p),
                )
                check("positions have instrument names", all(p.get("instrument_name") for p in positions))
                check("positions have ISINs", all(p.get("isin") for p in positions))

        print("== list_documents / download_document (already-read PDF only)", flush=True)
        data = await call(client, "list_documents", {"paging_count": 5})
        documents = data["documents"] if data else []
        print(
            f"  {len(documents)} document(s), types: {sorted({d.get('mime_type', '?') for d in documents})}",
            flush=True,
        )
        check("documents report already_read", all(d.get("already_read") is not None for d in documents))
        pdf = next(
            (
                d
                for d in documents
                if d.get("mime_type") == "application/pdf" and d.get("already_read") is True and d.get("document_id")
            ),
            None,
        )
        if pdf:
            result = await call(
                client, "download_document", {"document_id": pdf["document_id"], "mime_type": "application/pdf"}
            )
            if result:
                content = base64.b64decode(result.content[0].resource.blob)
                check(f"PDF signature ({len(content) // 1024} KB, discarded)", content.startswith(b"%PDF"))
                del content
        else:
            print("  SKIP download: no already-read PDF in this page", flush=True)

        print("== token refresh", flush=True)
        session = server._state.logged_in_client()
        old_token = session._api_client.configuration.access_token
        session.refresh_token()
        check("new access token", session._api_client.configuration.access_token != old_token)
        check("API call with refreshed token", await call(client, "list_depots") is not None)

        print("== logout", flush=True)
        old_token = session._api_client.configuration.access_token
        old_refresh_token = session._refresh_token
        await call(client, "logout")
        check("session ended locally", not session.is_logged_in)
        refresh_status = await asyncio.to_thread(refresh_status_of, old_refresh_token)
        check(f"old refresh token rejected after revoke (HTTP {refresh_status})", refresh_status >= 400)
        # Informational: whether comdirect also invalidates the access token right away.
        for delay in (0, 15):
            await asyncio.sleep(delay)
            status = await asyncio.to_thread(rejected_status, old_token)
            print(f"  INFO old access token after revoke + {delay}s: HTTP {status}", flush=True)

    print(f"\n{'all checks passed' if not failures else f'{failures} check(s) failed'}", flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Live check aborted: {type(error).__name__} (details suppressed)", flush=True)
        sys.exit(1)
