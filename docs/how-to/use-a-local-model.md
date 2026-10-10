# Use a local model

With a local model, your balances, transactions and documents never leave your machine: the only network traffic
is between `comdirect-mcp` and comdirect. Why this matters: [Privacy and security](../explanation/privacy-and-security.md).

## With LM Studio

1. Install [LM Studio](https://lmstudio.ai) and download a model with good **tool calling** support. Larger
   instruction-tuned models (e.g. recent Qwen, Llama or Mistral releases with tool use) work noticeably better
   than small ones, which tend to call tools with wrong arguments or invent numbers.
2. Store your credentials in the keychain: `uvx comdirect-mcp@0.4.0 configure`
   ([Manage credentials](manage-credentials.md)).
3. In LM Studio open the *Program* tab in the right sidebar → *Install* → *Edit mcp.json* and add:

   ```json
   {
     "mcpServers": {
       "comdirect": {
         "command": "uvx",
         "args": ["comdirect-mcp@0.4.0"]
       }
     }
   }
   ```

   LM Studio loads the server when you save. If it already has servers, add the `comdirect` entry to the
   existing `mcpServers` object instead of pasting a second one.
4. Start a chat with your model and ask it to log in to comdirect. Approve the push TAN in the photoTAN app.

LM Studio asks for confirmation before each tool call; you can allow the read-only comdirect tools permanently.

## With other local setups

Any MCP client that talks to a local model works the same way: register `uvx comdirect-mcp@0.4.0` as a stdio
server. Check that the client really uses a local model for the chat (no cloud fallback) and that it does not send
telemetry with conversation content.

## Tips

- Ask for aggregates ("Summe der Ausgaben pro Kategorie im September") rather than full transaction lists; local
  models have smaller context windows.
- Use the `limit` and date filters of `list_transactions` in your question ("nur die letzten 30 Tage").
- Double-check numbers that matter. Every model can miscalculate.
