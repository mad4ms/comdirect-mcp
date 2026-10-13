"""
Local category rules for `summarize_transactions(group_by="category")`.

The rules live in a TOML file on the user's machine and are applied deterministically on the server, so the
model does not have to guess categories from payment texts. Example:

    [[rule]]
    category = "Lebensmittel"
    counterparty = ["REWE", "EDEKA"]

    [[rule]]
    category = "Umbuchung"
    purpose = "Uebertrag"
    direction = "out"

A rule matches when every condition it sets matches; a condition with several patterns matches if any of them
does. Text patterns match case-insensitively as substrings. The first matching rule wins.
"""

import os
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain.models import Transaction

CATEGORIES_ENV = "COMDIRECT_MCP_CATEGORIES"
UNCATEGORIZED = "(uncategorized)"

_TEXT_FIELDS = ("counterparty", "purpose", "type")
_KEYS = {"category", "direction", *_TEXT_FIELDS}

FORMAT_HELP = """\
Category rules: a TOML file with one [[rule]] table per rule. Keys:
  category      required, the group name in summarize_transactions(group_by="category")
  counterparty  text or list of texts, matched in the counterparty name
  purpose       text or list of texts, matched in the payment reference
  type          text or list of texts, matched in the transaction type (e.g. DIRECT_DEBIT)
  direction     "in" or "out"
Each rule needs at least one condition; all conditions of a rule must match, any pattern of a list may match.
Text matches are case-insensitive substrings. The first matching rule wins; other transactions are grouped as
"(uncategorized)"."""


class CategoryRulesError(ValueError):
    pass


def categories_path() -> Path:
    if path := os.environ.get(CATEGORIES_ENV):
        return Path(path).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(config_home).expanduser() / "comdirect-mcp" / "categories.toml"


@dataclass(frozen=True)
class CategoryRule:
    category: str
    counterparty: tuple[str, ...] = ()
    purpose: tuple[str, ...] = ()
    type: tuple[str, ...] = ()
    direction: str | None = None

    def matches(self, tx: Transaction) -> bool:
        if self.direction and tx.direction != self.direction:
            return False
        holder = tx.counterparty
        texts = {
            "counterparty": holder.holder_name if holder else None,
            "purpose": tx.purpose,
            "type": tx.type,
        }
        for field in _TEXT_FIELDS:
            patterns: tuple[str, ...] = getattr(self, field)
            text = (texts[field] or "").casefold()
            if patterns and not any(pattern in text for pattern in patterns):
                return False
        return True


def _patterns(value: Any, where: str) -> tuple[str, ...]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v.strip() for v in values):
        raise CategoryRulesError(f"{where} must be a non-empty text or a list of non-empty texts.")
    return tuple(v.strip().casefold() for v in values)


def parse_rules(data: dict[str, Any]) -> tuple[CategoryRule, ...]:
    unknown = set(data) - {"rule"}
    if unknown:
        raise CategoryRulesError(f"Unknown top-level keys: {', '.join(sorted(unknown))}. Use [[rule]] tables.")
    tables = data.get("rule", [])
    if not isinstance(tables, list):
        raise CategoryRulesError("Write rules as [[rule]] tables.")
    rules = []
    for number, table in enumerate(tables, start=1):
        where = f"Rule {number}"
        if not isinstance(table, dict):
            raise CategoryRulesError(f"{where} must be a table.")
        if unknown := set(table) - _KEYS:
            raise CategoryRulesError(f"{where} has unknown keys: {', '.join(sorted(unknown))}.")
        category = table.get("category")
        if not isinstance(category, str) or not category.strip():
            raise CategoryRulesError(f"{where} needs a non-empty `category`.")
        direction = table.get("direction")
        if direction is not None and direction not in ("in", "out"):
            raise CategoryRulesError(f'{where}: `direction` must be "in" or "out".')
        conditions = {f: _patterns(table[f], f"{where} `{f}`") for f in _TEXT_FIELDS if f in table}
        if not conditions and direction is None:
            raise CategoryRulesError(f"{where} ({category}) has no condition.")
        rules.append(CategoryRule(category=category.strip(), direction=direction, **conditions))
    return tuple(rules)


def load_rules(path: Path | None = None) -> tuple[CategoryRule, ...] | None:
    """The rules from the categories file, or None if it does not exist. Raises CategoryRulesError."""
    path = path or categories_path()
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError:
        return None
    except tomllib.TOMLDecodeError as e:
        raise CategoryRulesError(f"{path} is not valid TOML: {e}") from e
    except OSError as e:
        raise CategoryRulesError(f"{path} cannot be read: {e.strerror}") from e
    try:
        return parse_rules(data)
    except CategoryRulesError as e:
        raise CategoryRulesError(f"{path}: {e}") from e


def categorize(tx: Transaction, rules: Sequence[CategoryRule]) -> str:
    return next((rule.category for rule in rules if rule.matches(tx)), UNCATEGORIZED)
