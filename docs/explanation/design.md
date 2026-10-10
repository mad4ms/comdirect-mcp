# Design decisions

## No tool can move money

The comdirect API can place securities orders. `comdirect-mcp` deliberately exposes none of these endpoints: an
assistant that can be manipulated by text in a payment reference must not be able to trade. Contributions that
move money are not accepted.

The tool annotations are kept truthful: data tools are `readOnlyHint: true`, except `download_document`, because
comdirect marks an unread document as read when it is downloaded.

## Layers

```text
server.py      MCP tools: argument validation, structured results, errors for the model
views.py       compact agent-facing views, masking, aggregation
client.py      ComdirectClient: API calls, paging, token refresh
auth.py        OAuth + session + 2FA flow
domain/        own frozen dataclasses + mappers
_openapi/      generated client from comdirect's Swagger spec (vendored)
```

The generated code is never edited and never leaks out of the package: `client.py` maps its models to the
domain dataclasses. When comdirect changes the API, only the generated code and the mappers change.

The generated client is vendored as `comdirect_mcp._openapi` instead of a top-level `openapi_client` package, so it
cannot collide with other generated clients in the same environment. See
[Regenerate the OpenAPI client](../how-to/regenerate-openapi-client.md).

## The spec guarantees nothing

comdirect's Swagger specification marks no field as required, and the live API differs from it in places
(e.g. the depot id inside the depot balance is nested in `aggregated.depot`). The PDF documentation (April 2020)
adds rules the Swagger file does not express: instrument data only comes with `with-attr=instrument`, valuta dates
can be non-existent dates like `2019-02-30`, and five unconfirmed TAN challenges lock the access. Conversely, the
transaction date filters and paging the client uses are not in the PDF but work. Consequences:

- Domain fields are `X | None` instead of invented defaults like `0` or `1970-01-01`, which would silently
  produce wrong numbers. Fields that may hold invalid values (the valuta date) stay raw strings instead of
  failing the whole request.
- MCP output schemas reflect this; a `None` in a non-optional field would make clients reject the whole result.
- Mocked tests can only confirm what we assumed. `scripts/live_check.py` verifies every tool against the real API
  before a release, printing structure only.

## Tools designed for the agent, not mirroring the API

Every tool result lands in the model's context. The API's transaction object has around twenty fields, most of them
empty or irrelevant for a question like "what did I spend last month". The tools therefore return views
(`views.py`) instead of the domain models: null fields are left out, references are only returned with `verbose`,
the SEPA role juggling (`remitter`/`creditor`) is resolved into one `counterparty`, payment texts are cleaned up,
and `summarize_transactions` aggregates on the server. Less data in the context means fewer tokens, fewer
mistakes and less personal data at the model provider.

## Money as decimal strings

Amounts are `Decimal` in Python and decimal strings in tool results, so no value is rounded through binary
floating point on the way to the model.

## stdio and one session per process

The server is a local stdio process started by the client. That keeps credentials on the user's machine, needs no
network listener or authentication layer, and makes the single in-memory session the natural model. A remote
(HTTP) deployment would need its own authorization design and is out of scope.

## Built on the official SDK

The server uses `MCPServer` from the official MCP Python SDK v2. It provides version negotiation (2026-07-28 and
older), structured output from type hints, tool annotations, and resolvers for the elicitation-based login, so
the project contains no protocol code of its own.
