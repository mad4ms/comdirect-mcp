# Regenerate the OpenAPI client

Low-level communication with the comdirect API goes through a Python client generated from comdirect's official
Swagger specification. It is vendored as

`src/comdirect_mcp/_openapi`

and treated as **vendor code: never edit it by hand**. All business logic lives outside this directory; the rest
of the package maps the generated models to its own domain models (`src/comdirect_mcp/domain/`).

## When to regenerate

Only when one of the following applies:

1. comdirect publishes an updated specification (the current one is version `20.04`, matching the PDF
   documentation of April 2020).
2. A newer OpenAPI generator changes the output or runtime behavior in a way we need.
3. A schema defect is fixed or added in the spec patch step (see below).

## Requirements

- `curl`
- a **Java runtime** (11+): `openapi-generator-cli` is a Python wrapper around the Java generator
- the dev dependencies (`uv sync --all-extras`), which include `openapi-generator-cli`

## How to regenerate

```bash
uv run ./scripts/bootstrap_client.sh
```

The script

1. downloads the specification from `https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json`,
2. patches known schema defects (`scripts/patch_openapi.py`, mandatory, see below),
3. generates a client with the `python` generator (Pydantic v2),
4. replaces `src/comdirect_mcp/_openapi` with the result,
5. rewrites the generator's absolute `openapi_client` imports to `comdirect_mcp._openapi`, so the client cannot
   clash with other generated clients installed in the same environment.

The downloaded spec and the raw generator output stay in `tmp/` (git-ignored) for inspection.

## Spec patching (not optional)

The comdirect specification declares several primitive values as objects (e.g. `CurrencyString`, `DateString`
are plain strings like `"EUR"` and `"2024-01-31"` in real responses) and has constraints the API does not keep
(e.g. document names longer than 50 characters). These are fixed in the spec **before** generation; runtime
monkey-patching is intentionally avoided.

If a Pydantic `ValidationError` from a generated model shows up at runtime:

1. Identify the failing field (e.g. `Document.name`).
2. Relax or correct the schema in `scripts/patch_openapi.py`:
   ```python
   if "Document" in definitions:
       definitions["Document"]["properties"]["name"]["maxLength"] = 255
   ```
3. Regenerate.

Note that the specification marks no field as required. Mappers in `domain/mappers.py` must therefore cope with
any field being absent. Rules that only the PDF documentation states (e.g. invalid valuta dates, the
`with-attr=instrument` projection) are handled in the mappers and the client, not in the spec patch.

The PDF (*comdirect REST API – Schnittstellenspezifikation*) is comdirect's copyrighted document. Download it from
the developer access page; keep a local copy in `docs/reference/` if you like - `*.pdf` there is git-ignored so it
is not redistributed.

## After regeneration

1. Review the diff: `git diff src/comdirect_mcp/_openapi`
2. Check that no object wrappers reappeared: `rg "__root__" src/comdirect_mcp/_openapi || echo OK`
3. Update the domain mappers if comdirect added or removed fields.
4. Run `uv run pytest`. `tests/test_http_roundtrip.py` exercises the generated client end to end (serialization,
   deserialization, mappers) with only the HTTP transport mocked.
5. Run the live check (`uv run python scripts/live_check.py`, see [Develop](develop.md)).

## Rules

- Never edit files inside `src/comdirect_mcp/_openapi` manually.
- Never monkey-patch generated models at runtime.
- Never regenerate without the spec patch.
- Never mix Pydantic v1 and v2 generators.
