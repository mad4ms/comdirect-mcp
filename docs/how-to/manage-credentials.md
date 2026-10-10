# Manage credentials

The server looks up each credential in this order and uses the first value it finds:

1. **Environment variable** (`COMDIRECT_CLIENT_ID`, `COMDIRECT_CLIENT_SECRET`, `COMDIRECT_USERNAME`,
   `COMDIRECT_PASSWORD`), e.g. set in the MCP client's config
2. **OS keychain** entry with the same name under the service `comdirect-mcp`
3. **Dotenv file** named by `COMDIRECT_ENV_FILE` (opt-in; no `.env` is read implicitly)

Where you get the values: [Get comdirect API access](get-comdirect-api-access.md).

## Recommended: OS keychain

```bash
uvx comdirect-mcp@0.5.1 configure     # or: comdirect-mcp configure
```

- Prompts for the four values; Client Secret and PIN are not echoed.
- Press Enter to keep a value that is already stored.
- Stores them in the macOS Keychain, Windows Credential Manager or the Linux Secret Service (GNOME Keyring,
  KWallet). Your MCP client configs then contain no secrets at all.

Remove them again:

```bash
uvx comdirect-mcp@0.5.1 configure --delete
```

On macOS, the Keychain may ask once whether the Python interpreter may read the entries; choose *Always Allow*.
On a Linux machine without a desktop session there is usually no keychain; use one of the options below.

## VS Code: input variables

VS Code can prompt for secrets and keep them in its secure storage instead of `mcp.json`:

```json
{
  "inputs": [
    {"type": "promptString", "id": "comdirect-client-secret", "description": "comdirect Client Secret", "password": true},
    {"type": "promptString", "id": "comdirect-pin", "description": "comdirect PIN", "password": true}
  ],
  "servers": {
    "comdirect": {
      "type": "stdio",
      "command": "uvx",
      "args": ["comdirect-mcp@0.5.1"],
      "env": {
        "COMDIRECT_CLIENT_ID": "User_...",
        "COMDIRECT_USERNAME": "...",
        "COMDIRECT_CLIENT_SECRET": "${input:comdirect-client-secret}",
        "COMDIRECT_PASSWORD": "${input:comdirect-pin}"
      }
    }
  }
}
```

## Environment variables in the client config

Every client can pass environment variables (`env` in Claude Desktop, `--env` for `claude mcp add`). This is
simple, but the values are stored **in plain text** in the client's config file. Prefer the keychain.

## Dotenv file (opt-in)

The server reads a dotenv file only when `COMDIRECT_ENV_FILE` points to it. It never picks up a `.env` from its
working directory: an MCP client starts the server in an arbitrary directory, and a file with your PIN should not
be used by accident.

```bash
COMDIRECT_ENV_FILE=/path/to/comdirect.env comdirect-mcp
```

For development and the [Python library](use-the-python-library.md): copy `.env.example` to `.env` (git-ignored).
The examples load it themselves; this repository's `.vscode/mcp.json` passes it to the server via `envFile`.
Prefer the keychain wherever possible - a dotenv file keeps the PIN in plain text.

## Rotate or revoke

- Changed PIN: run `comdirect-mcp configure` again and enter the new PIN.
- Suspect a leak of the Client Secret: deactivate and reactivate the developer access in the online banking
  (*Verwaltung → Entwicklerzugang*), then store the new values.
