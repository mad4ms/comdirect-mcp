#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SPEC_URL="https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json"
SPEC_FILE="$ROOT/tmp/comdirect_openapi.json"

GEN_DIR="$ROOT/tmp/generated_client"
DEST_DIR="$ROOT/src/comdirect_mcp/_openapi"

# ------------------------------------------------------------------------------
# Prerequisites
# ------------------------------------------------------------------------------
command -v curl >/dev/null || { echo "curl missing"; exit 1; }
command -v openapi-generator-cli >/dev/null || { echo "openapi-generator-cli missing"; exit 1; }
command -v ruff >/dev/null || { echo "ruff missing"; exit 1; }
command -v python >/dev/null || { echo "python missing"; exit 1; }

mkdir -p "$ROOT/tmp"

# ------------------------------------------------------------------------------
# Download OpenAPI spec
# ------------------------------------------------------------------------------
echo "Downloading OpenAPI spec ..."
curl -fsSL -o "$SPEC_FILE" "$SPEC_URL"

# ------------------------------------------------------------------------------
# Patch broken schemas
# ------------------------------------------------------------------------------
echo "Patching OpenAPI spec ..."
python "$ROOT/scripts/patch_openapi.py" "$SPEC_FILE"

# ------------------------------------------------------------------------------
# Generate Python client
# ------------------------------------------------------------------------------
echo "Generating Python client ..."
rm -rf "$GEN_DIR"

openapi-generator-cli generate \
  -i "$SPEC_FILE" \
  -g python \
  -o "$GEN_DIR" \
  --package-name openapi_client \
  --global-property modelTests=false,apiTests=false \
  --skip-validate-spec

# ------------------------------------------------------------------------------
# Integrate into source tree
# ------------------------------------------------------------------------------
echo "Integrating generated client ..."
rm -rf "$DEST_DIR"
mkdir -p "$(dirname "$DEST_DIR")"
cp -r "$GEN_DIR/openapi_client" "$DEST_DIR"

# The generator emits absolute imports of a top-level `openapi_client` package. Vendor it as
# `comdirect_mcp._openapi` instead, so it cannot clash with other generated clients.
python - "$DEST_DIR" <<'PY'
import pathlib
import re
import sys

for path in pathlib.Path(sys.argv[1]).rglob("*.py"):
    text = path.read_text()
    path.write_text(re.sub(r"\bopenapi_client\b", "comdirect_mcp._openapi", text))
PY

# ------------------------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------------------------
ruff format --isolated --line-length 119 --target-version py312 "$DEST_DIR"

# Generator output and the downloaded spec stay in tmp/ (git-ignored) for inspection.

echo "✔ Client successfully updated at:"
echo "  $DEST_DIR"
