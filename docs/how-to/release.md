# Release a new version

1. Update the version in `pyproject.toml`, `server.json` (both `version` fields) and the pinned
   `comdirect-mcp@<version>` examples in `README.md`, `SECURITY.md` and `docs/`, then run `uv lock`.
   `tests/test_packaging.py` fails if any of them disagree.
2. Move the `Unreleased` notes in [CHANGELOG.md](../../CHANGELOG.md) to the new version.
3. Run the checks and the live check ([Develop](develop.md)).
4. Merge to `main`, then create a GitHub release with the tag `v<version>` (e.g. `v0.4.0`).

The [publish workflow](../../.github/workflows/publish.yml) then:

1. checks that the tag matches the package version, runs the tests (including `test_packaging.py`), builds
2. publishes to PyPI with trusted publishing (environment `pypi`)
3. waits until the version is visible on PyPI and publishes `server.json` to the
   [MCP Registry](https://registry.modelcontextprotocol.io) via GitHub OIDC (namespace `io.github.mad4ms`)

### One-time setup

- **PyPI**: add a trusted publisher (for a new project: a *pending publisher*) for `comdirect-mcp` with owner
  `mad4ms`, repository `comdirect-mcp`, workflow `publish.yml`, environment `pypi`.
- **GitHub**: the `pypi` environment is created on first use; optionally restrict it to protected tags or
  require a reviewer.
- **MCP Registry**: nothing to configure; GitHub OIDC proves ownership of `io.github.mad4ms/*`, the README
  marker `mcp-name: io.github.mad4ms/comdirect-mcp` proves ownership of the PyPI package.
