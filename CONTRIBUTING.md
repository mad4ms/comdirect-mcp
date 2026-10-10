# Contributing

Thanks for your interest! Issues and pull requests are welcome. Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- **Security issues:** do not open a public issue, see [SECURITY.md](SECURITY.md).
- **Never include real banking data** (account numbers, IBANs, amounts, documents, screenshots) in issues,
  pull requests, tests or logs. Anonymize everything.
- The server is read-only by design. Features that move money (orders, transfers) will not be accepted.

## Workflow

1. Set up the project as described in [Develop](docs/how-to/develop.md) (`uv sync --all-extras`,
   `uv run pre-commit install`).
2. Make your change with tests. Tests must not touch the network.
3. Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy`.
4. Add a line to the `Unreleased` section of [CHANGELOG.md](CHANGELOG.md) for user-facing changes.
5. Open a pull request describing what changed and why. If you verified it against the real API with
   `scripts/live_check.py`, say so.

AI coding agents: follow [AGENTS.md](AGENTS.md).
