## What and why

<!-- What does this change, and why is it needed? Link related issues. -->

## Checklist

- [ ] `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` pass
- [ ] Tests added or updated; no test touches the network
- [ ] `CHANGELOG.md` updated (user-facing changes)
- [ ] Docs updated (`README.md`, `docs/`) if behavior or configuration changed
- [ ] No real banking data or credentials in code, tests, logs or screenshots
- [ ] Verified against the real API with `scripts/live_check.py` (optional, say so if you did)
