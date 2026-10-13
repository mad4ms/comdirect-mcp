# Use a local model

With a local model, your balances, transactions and documents never leave your machine: the only network traffic
is between `comdirect-mcp` and comdirect. Why this matters: [Privacy and security](../explanation/privacy-and-security.md).

## With LM Studio

1. Install [LM Studio](https://lmstudio.ai) and download a model with good **tool calling** support. Larger
   instruction-tuned models (e.g. recent Qwen, Llama or Mistral releases with tool use) work noticeably better
   than small ones, which tend to call tools with wrong arguments or invent numbers.
2. Store your credentials in the keychain: `uvx comdirect-mcp@0.6.1 configure`
   ([Manage credentials](manage-credentials.md)).
3. In LM Studio open the *Program* tab in the right sidebar → *Install* → *Edit mcp.json* and add:

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

   LM Studio loads the server when you save. If it already has servers, add the `comdirect` entry to the
   existing `mcpServers` object instead of pasting a second one.
4. Start a chat with your model and ask it to log in to comdirect. Approve the push TAN in the photoTAN app.

LM Studio asks for confirmation before each tool call; you can allow the read-only comdirect tools permanently.

## With Ollama

Ollama has no built-in MCP client, so you connect the two with
[ollmcp](https://github.com/jonigl/mcp-client-for-ollama) (*MCP Client for Ollama*), a terminal chat client.

1. Install [Ollama](https://ollama.com) and pull a model that supports tools. `ollama show <model>` lists `tools`
   under *Capabilities* if it does. Prefer larger models; very small ones (around 4B parameters) call tools
   unreliably.
2. Store your credentials in the keychain: `uvx comdirect-mcp@0.6.1 configure`.
3. Register the server once for all projects (no secrets in ollmcp's config):

   ```bash
   uvx ollmcp mcp add --scope user comdirect -- uvx comdirect-mcp@0.6.1
   ```

4. Start a chat with your model:

   ```bash
   uvx ollmcp -m <model>
   ```

5. Ask it to log in to comdirect. ollmcp asks you to approve the `login` tool call; then the push arrives on
   your phone.

ollmcp has no elicitation dialog. The server therefore uses its fallback window: approve the push in the app
within 30 seconds; the server waits the full window and then confirms. For more time, register the server with
`-e COMDIRECT_MCP_PUSH_TAN_WAIT=60` before the `comdirect` name.

ollmcp can also use Ollama Cloud models. Use only local models (no `-cloud` suffix) if your data should stay on
your machine. Server logs are written to `~/.config/ollmcp/logs/`.

## With other local setups

Any MCP client that talks to a local model works the same way: register `uvx comdirect-mcp@0.6.1` as a stdio
server. Check that the client really uses a local model for the chat (no cloud fallback) and that it does not send
telemetry with conversation content.

## Tips

- Ask for aggregates ("Summe der Ausgaben pro Kategorie im September") rather than full transaction lists; the
  `summarize_transactions` tool computes them on the server, which suits the smaller context of local models.
- Use the `limit` and date filters of `list_transactions` in your question ("nur die letzten 30 Tage").
- Double-check numbers that matter. Every model can miscalculate.
