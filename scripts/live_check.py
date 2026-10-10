"""
Live check of the MCP server against the real comdirect API.

Runs every tool once through an in-process MCP client and prints only structure (counts, which
fields are set, format checks) - never amounts, ids, names, IBANs or payment texts. Nothing is
written to disk; a downloaded document is checked for its file signature and discarded.

Needs credentials in .env and triggers ONE push TAN: approve it in the photoTAN app while the
script waits. There is deliberately no retry, repeated failed logins can lock the access.

    uv run python scripts/live_check.py [seconds-to-wait-for-approval]
"""

import asyncio
import base64
import json
import re
import sys
import uuid
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
    print(f"  [dialog] {params.message}", flush=True)
    print(f"  [dialog] confirming automatically in {WAIT}s - approve the push in the app now", flush=True)
    await asyncio.sleep(WAIT)
    return ElicitResult(action="accept", content={"approved": True})


async def call(client: Client, name: str, args: dict | None = None):
    try:
        result = await client.call_tool(name, args or {})
    except Exception as e:  # e.g. the client rejecting output that violates the tool's output schema
        check(f"{name}: {type(e).__name__}: {str(e).splitlines()[0]}", False)
        return None
    if result.is_error:
        check(f"{name}: {result.content[0].text}", False)
        return None
    return result.structured_content if result.structured_content is not None else result


async def main() -> None:
    async with Client(server.mcp, elicitation_callback=approve) as client:
        print("== login", flush=True)
        if not await call(client, "login"):
            return

        print("== list_accounts", flush=True)
        data = await call(client, "list_accounts")
        accounts = data["accounts"] if data else []
        print(f"  {len(accounts)} account(s)", flush=True)
        for i, account in enumerate(accounts):
            check(f"account {i}: balance is a decimal", is_decimal(account["balance"]))
            print(f"       fields: {set_fields(account)}", flush=True)

        if accounts:
            since = (date.today() - timedelta(days=30)).isoformat()
            print("== list_transactions (BOOKED, last 30 days, limit 20)", flush=True)
            args = {"account_id": accounts[0]["id"], "min_booking_date": since, "limit": 20}
            data = await call(client, "list_transactions", args)
            if data:
                txs = data["transactions"]
                print(f"  {data['count']} transaction(s), truncated={data['truncated']}", flush=True)
                check("amounts are decimals", all(is_decimal(t["amount"]) for t in txs))
                check(
                    "booking dates are ISO dates",
                    all(t["booking_date"] and ISO_DATE.match(t["booking_date"]) for t in txs),
                )
                check("booking dates within the filter", all(t["booking_date"] >= since for t in txs))
                holders = [h for t in txs for h in (t["remitter"], t["debtor"], t["creditor"]) if h and h.get("iban")]
                check(f"{len(holders)} counterparty IBAN(s) masked", all("**..." in h["iban"] for h in holders))
                if txs:
                    print(f"       fields: {set_fields(txs[0])}", flush=True)

            print("== list_transactions (NOTBOOKED)", flush=True)
            data = await call(
                client, "list_transactions", {"account_id": accounts[0]["id"], "transaction_state": "NOTBOOKED"}
            )
            if data:
                print(f"  {data['count']} pending transaction(s)", flush=True)

        print("== list_depots / get_depot_positions", flush=True)
        data = await call(client, "list_depots")
        depots = data["depots"] if data else []
        print(f"  {len(depots)} depot(s)", flush=True)
        if depots:
            data = await call(client, "get_depot_positions", {"depot_id": depots[0]["id"]})
            if data:
                positions = data["positions"]
                print(f"  {len(positions)} position(s)", flush=True)
                check("depot value is a decimal", is_decimal(data["balance"]["current_value"]))
                check("position values are decimals", all(is_decimal(p["current_value"]) for p in positions))
                check("positions have instrument names", all(p["instrument_name"] for p in positions))
                check("positions have ISINs", all(p["isin"] for p in positions))

        print("== list_documents / download_document", flush=True)
        data = await call(client, "list_documents", {"paging_count": 5})
        documents = data["documents"] if data else []
        print(f"  {len(documents)} document(s), types: {sorted({d['mime_type'] for d in documents})}", flush=True)
        check("documents report already_read", all(d["already_read"] is not None for d in documents))
        pdf = next((d for d in documents if d["mime_type"] == "application/pdf"), None)
        if pdf:
            result = await call(
                client, "download_document", {"document_id": pdf["document_id"], "mime_type": "application/pdf"}
            )
            if result:
                content = base64.b64decode(result.content[0].resource.blob)
                check(f"PDF signature ({len(content) // 1024} KB, discarded)", content.startswith(b"%PDF"))
                del content

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
    asyncio.run(main())
