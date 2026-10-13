# Getting started

In this tutorial you connect your comdirect account to an AI assistant and ask it your first question. It takes
about 15 minutes, most of it at comdirect.

You will:

1. get API access at comdirect,
2. store your credentials in the OS keychain,
3. add the server to your MCP client,
4. log in with your photoTAN app and ask a question.

> [!NOTE]
> Before you start, read the [privacy explanation](../explanation/privacy-and-security.md): the assistant's model
> receives the data you ask about. A client with a local model keeps it on your machine.

## What you need

- a comdirect account with online banking and the **photoTAN app**
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (it provides the `uvx` command)
- an MCP client, for example Claude Desktop, VS Code with GitHub Copilot, LM Studio, or Ollama with ollmcp

## 1. Get API access at comdirect

1. Log in to the comdirect online banking in your browser.
2. Open **Verwaltung → Entwicklerzugang** and activate access to the comdirect REST API (free for private
   customers). Follow the steps shown there.
3. Note the **Client ID** (starts with `User_`) and the **Client Secret** you receive.
4. Make sure **photoTAN Push** (approval in the app) is activated, ideally as your default TAN method. The MCP
   server supports only this method.

Your login for the API is the same as for the online banking: **Zugangsnummer** and **PIN**.

More details: [Get comdirect API access](../how-to/get-comdirect-api-access.md).

## 2. Store your credentials in the keychain

```bash
uvx comdirect-mcp@0.6.1 configure
```

Enter the Client ID, Client Secret, Zugangsnummer and PIN. Secret values are not shown while you type. They are
stored in your operating system's keychain (macOS Keychain, Windows Credential Manager, Secret Service on Linux),
not in a file.

## 3. Add the server to your MCP client

The client only needs to know how to start the server; no credentials go into its configuration.

**Claude Desktop**: open *Settings → Developer → Edit Config* and add:

```json
{
  "mcpServers": {
    "comdirect": {
      "command": "uvx",
      "args": ["comdirect-mcp@0.6.1"]
    }
  }
}
```

Restart Claude Desktop. For other clients see [Configure MCP clients](../how-to/configure-mcp-clients.md).

## 4. Log in and ask

Ask your assistant:

> Melde dich bei comdirect an und zeig mir meine Konten.

1. The assistant calls the `login` tool. Your phone receives a photoTAN push notification.
2. Approve the login in the photoTAN app.
3. Your client shows a dialog *"comdirect: Bitte die Anmeldung in der photoTAN-App freigeben ..."*. Confirm it.
   Some clients, e.g. Claude Code, show no dialog; the server then waits 30 seconds for your approval in the app.
4. The assistant lists your accounts.

Now try:

> Wie haben sich meine Ausgaben im letzten Monat entwickelt?

> Welche Depotposition läuft seit Kauf am schlechtesten?

When you are done, ask the assistant to log out, or just close the client.

## Next steps

- [Use a local model](../how-to/use-a-local-model.md) to keep your data on your machine
- [Tools reference](../reference/tools.md): what the assistant can do
- [Login and sessions](../explanation/login-and-sessions.md): what happens during login
- [Troubleshoot](../how-to/troubleshoot.md) if something does not work
