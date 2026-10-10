#!/usr/bin/env python3
"""
Patches known schema violations in the comdirect Swagger specification.

comdirect defines several primitive wrapper types (e.g. CurrencyString,
DateString) as objects, but the API returns plain strings.

This script normalizes those schemas so code generation works reliably.
"""

import json
import sys
from pathlib import Path

# Default: the spec downloaded by bootstrap_client.sh, independent of the current directory.
DEFAULT_SPEC_PATH = Path(__file__).resolve().parent.parent / "tmp" / "comdirect_openapi.json"
SPEC_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SPEC_PATH

if not SPEC_PATH.exists():
    raise RuntimeError(f"Spec file not found: {SPEC_PATH}")

data = json.loads(SPEC_PATH.read_text())

definitions = data.get("definitions")
if not definitions:
    raise RuntimeError("No 'definitions' section found in swagger")


def patch_string(name, description, *, example=None, pattern=None):
    schema = {
        "type": "string",
        "description": description,
    }
    if example is not None:
        schema["example"] = example
    if pattern is not None:
        schema["pattern"] = pattern
    definitions[name] = schema


# ------------------------------------------------------------------
# Primitive wrapper fixes (API returns plain strings)
# ------------------------------------------------------------------

patch_string(
    "CurrencyString",
    "ISO-4217 currency code",
    example="EUR",
)

patch_string(
    "DateString",
    "ISO-8601 date (YYYY-MM-DD)",
    example="2024-09-30",
    pattern=r"^\d{4}-\d{2}-\d{2}$",
)

patch_string(
    "TimestampString",
    "ISO-8601 timestamp",
    example="2024-09-30T12:34:56Z",
)

patch_string(
    "PercentageString",
    "Percentage encoded as string",
    example="12.34",
)
# DateTimeString
patch_string(
    "DateTimeString",
    "ISO-8601 date-time (YYYY-MM-DDThh:mm:ssZ)",
    example="2024-09-30T12:34:56Z",
)


# ------------------------------------------------------------------
# Relax validations for fields where API violates spec
# ------------------------------------------------------------------

if "Document" in definitions:
    doc_props = definitions["Document"].get("properties", {})
    if "name" in doc_props:
        # API returns legal names > 50 chars
        doc_props["name"]["maxLength"] = 255
        print("✔ Patched Document.name.maxLength -> 255")

# Missing fields are unknown, not false; the PDF declares no field required.
for name in ("AccountTransaction", "Document", "DocumentMetadata"):
    for prop in definitions.get(name, {}).get("properties", {}).values():
        if prop.get("type") == "boolean":
            prop.pop("default", None)

SPEC_PATH.write_text(json.dumps(data, indent=2))
print("✔ OpenAPI spec patched successfully")
