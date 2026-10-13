"""
Checks whether a model picks the right first tool for typical questions, using the server's real tool catalog
and instructions. No banking login: the tools are listed in-process and never called.

Needs Anthropic API credentials (ANTHROPIC_API_KEY or an `ant auth login` profile) and costs a few cents per run:

    uv run --with anthropic python scripts/tool_choice_eval.py [--model claude-opus-5-5]
"""

import argparse
import asyncio
import sys
from datetime import date

import anthropic
from mcp.client import Client

from comdirect_mcp import server

# (question, acceptable first tools). Tools that need an id from a list tool accept the list tool first.
CASES: list[tuple[str, set[str]]] = [
    ("Wie viel Geld habe ich insgesamt auf meinen Konten?", {"list_accounts", "get_wealth_overview"}),
    ("Was habe ich im September 2026 insgesamt ausgegeben?", {"summarize_transactions"}),
    ("Wofür gebe ich dieses Jahr am meisten Geld aus, nach Kategorien?", {"summarize_transactions"}),
    ("Wie viel habe ich seit Januar bei Amazon bezahlt?", {"summarize_transactions"}),
    ("Wie haben sich Einnahmen und Ausgaben dieses Jahr von Monat zu Monat entwickelt?", {"summarize_transactions"}),
    ("Zeig mir die letzten zehn Buchungen auf meinem Girokonto.", {"list_accounts"}),
    ("Wie viel ist noch auf meiner Visa-Karte verfügbar?", {"list_cards", "get_wealth_overview"}),
    ("Wie ist mein Depot aufgeteilt?", {"list_depots"}),
    ("Welche Wertpapiere habe ich dieses Jahr gekauft?", {"list_depots"}),
    ("Habe ich noch offene Orders?", {"list_depots"}),
    ("Wie hoch ist die laufende Kostenquote des ETFs IE00B4L5Y983?", {"get_instrument"}),
    ("Was steht in meinem letzten Kontoauszug?", {"list_documents"}),
    ("Welche Abos und Verträge bezahle ich jeden Monat?", {"find_recurring_payments"}),
    ("Ist irgendein Abo in letzter Zeit teurer geworden?", {"find_recurring_payments"}),
]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--model", default="claude-opus-5-5")
parser.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
options = parser.parse_args()


async def catalog() -> list[dict]:
    async with Client(server.mcp) as client:
        tools = (await client.list_tools()).tools
    return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in tools]


def first_tool(client: anthropic.Anthropic, tools: list[dict], question: str) -> tuple[str | None, int]:
    system = (
        f"{server.mcp.instructions}\n\nToday is {date.today().isoformat()}. The user is already logged in. "
        "Answer by calling a tool."
    )
    response = client.messages.create(
        model=options.model,
        max_tokens=4000,
        system=system,
        tools=tools,
        tool_choice={"type": "auto"},
        output_config={"effort": options.effort},
        messages=[{"role": "user", "content": question}],
    )
    tokens = response.usage.input_tokens + response.usage.output_tokens
    if response.stop_reason == "refusal":
        return "(refusal)", tokens
    names = [block.name for block in response.content if block.type == "tool_use"]
    return (names[0] if names else None), tokens


def main() -> int:
    tools = asyncio.run(catalog())
    client = anthropic.Anthropic()
    failures = 0
    total_tokens = 0
    print(f"model={options.model} effort={options.effort} tools={len(tools)}", flush=True)
    for question, expected in CASES:
        try:
            chosen, tokens = first_tool(client, tools, question)
        except anthropic.APIStatusError as error:
            print(f"ABORT API error HTTP {error.status_code}", flush=True)
            return 2
        except anthropic.APIConnectionError:
            print("ABORT network error", flush=True)
            return 2
        total_tokens += tokens
        ok = chosen in expected
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {chosen or '(no tool)':<24} {question}", flush=True)
        if not ok:
            print(f"      expected one of {sorted(expected)}", flush=True)
    print(f"RESULT {len(CASES) - failures}/{len(CASES)} correct, {total_tokens} tokens", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
