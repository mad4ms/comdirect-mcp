# Configure MCP clients

`comdirect-mcp` is a local stdio server: the client starts it with `uvx comdirect-mcp@<version>`. These examples
assume your credentials are in the OS keychain ([Manage credentials](manage-credentials.md)), so the configs
contain no secrets.

> [!TIP]
> Always pin the version (`comdirect-mcp@0.5.1`). Without a pin, `uvx` may start a newer release you have not
> reviewed - for software that holds your banking credentials, update deliberately.

If a client cannot find `uvx`, use its absolute path (`which uvx`, e.g. `/Users/you/.local/bin/uvx`).

## Claude Desktop

*Settings → Developer → Edit Config* opens `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "comdirect": {
      "command": "uvx",
      "args": ["comdirect-mcp@0.5.1"]
    }
  }
}
```

Restart Claude Desktop after saving.

## Claude Code

```bash
claude mcp add --transport stdio --scope user comdirect -- uvx comdirect-mcp@0.5.1
```

`--scope user` makes the server available in all projects. Check it with `claude mcp list` or `/mcp`.

## VS Code (GitHub Copilot)

*MCP: Open User Configuration* (or `.vscode/mcp.json` for one workspace):

```json
{
  "servers": {
    "comdirect": {
      "type": "stdio",
      "command": "uvx",
      "args": ["comdirect-mcp@0.5.1"]
    }
  }
}
```

Without the keychain, use VS Code's secure input variables, see [Manage credentials](manage-credentials.md#vs-code-input-variables).

The server is also listed in the [MCP Registry](https://registry.modelcontextprotocol.io) as
`io.github.mad4ms/comdirect-mcp`; clients with a registry-backed server gallery (e.g. VS Code: *MCP: Browse MCP
Servers*) can install it from there. Check that the installed entry pins a version.

## LM Studio (local model)

LM Studio runs models on your machine and reads MCP servers from `mcp.json` (*Program* tab in the right sidebar
→ *Install* → *Edit mcp.json*), in the same `mcpServers` format as Claude Desktop:

```json
{
  "mcpServers": {
    "comdirect": {
      "command": "uvx",
      "args": ["comdirect-mcp@0.5.1"]
    }
  }
}
```

See [Use a local model](use-a-local-model.md).

## Ollama (local model)

Ollama needs an MCP client in between; [ollmcp](https://github.com/jonigl/mcp-client-for-ollama) works:

```bash
uvx ollmcp mcp add --scope user comdirect -- uvx comdirect-mcp@0.5.1
uvx ollmcp -m <model>
```

ollmcp shows no login dialog, so approve the push within the fallback window (30 s by default). Details:
[Use a local model](use-a-local-model.md#with-ollama).

## Other clients

Any MCP client that can start a stdio server works: command `uvx`, arguments `["comdirect-mcp@0.5.1"]`.
Alternatives: `comdirect-mcp` after `uv tool install comdirect-mcp`, or `python -m comdirect_mcp`.

## Login dialog support

The `login` tool asks you to confirm the push TAN through an MCP *elicitation* dialog. Clients without
elicitation support get a fixed approval window instead (`COMDIRECT_MCP_PUSH_TAN_WAIT`, default 30 s): approve the
push in the app within that time. See [Login and sessions](../explanation/login-and-sessions.md).

## From a source checkout

For development, point the client to the checkout's virtual environment (`uv sync` creates it):

```json
{
  "command": "/path/to/comdirect-mcp/.venv/bin/comdirect-mcp"
}
```

This repository's [.vscode/mcp.json](../../.vscode/mcp.json) does exactly that and loads credentials from `.env`.
