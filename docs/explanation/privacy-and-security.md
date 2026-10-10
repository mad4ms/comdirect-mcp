# Privacy and security

`comdirect-mcp` runs on your machine and talks only to comdirect. The privacy question is not the server, but
**where the tool results go next**.

## Where your data goes

```text
comdirect API  <-->  comdirect-mcp (your machine)  <-->  MCP client  <-->  language model
                                                                          local: stays on your machine
                                                                          cloud: goes to the provider
```

An MCP client sends every tool result into the model's context. With a cloud model (Claude, GitHub Copilot,
ChatGPT, ...) your balances, transactions, payment references and document contents are processed by that
provider under its retention and training policy. With a local model they stay on your machine.

| Setup | Your financial data |
| --- | --- |
| Local model (e.g. LM Studio) | stays on your machine |
| Cloud model, training disabled, short retention | processed and stored by the provider for a limited time |
| Cloud model with default consumer settings | may be retained longer and, depending on the provider, used for training |

Recommendation: prefer a [local model](../how-to/use-a-local-model.md). If you use a cloud model, check the
provider's data settings first and ask only what you need.

## Prompt injection

Payment references, counterparty names and documents are written by third parties. Someone who sends you a
transfer controls the text the model reads. Such text can try to make the assistant do something you did not ask
for, e.g. call other tools you have connected or leak data into a link.

Mitigations in `comdirect-mcp`:

- No tool can move money or place orders, even if the model is manipulated. The only state change besides the
  session is that downloading a document marks it as read.
- The server's instructions tell the model to treat transaction texts and documents as untrusted data.
- You decide which other MCP servers run next to it. Be careful combining it with tools that can send data out
  (e-mail, web requests, file uploads).

No model is immune to prompt injection. Keep a human in the loop for anything that matters.

## Data minimization defaults

- Counterparty IBANs and own account numbers are masked (`DE**...3000`, `...7890`) unless
  `COMDIRECT_MCP_UNMASK_IBANS` is set.
- Counterparty names can be replaced with pseudonyms (`COMDIRECT_MCP_MASK_NAMES=true`), e.g. to keep names of
  family members away from a cloud model. Pseudonyms are stable within a server run, so summaries per counterparty
  still work, and cannot be linked across runs. Payment texts may still contain names.
- Results are compact: no null fields, references only on request (`verbose`), and `summarize_transactions`
  answers cash flow questions with totals instead of individual transactions.
- Transaction lists are limited (`limit`, default 250) and can be filtered by date.
- Documents are only downloaded on request and are size-limited.

## Credentials and session

- Credentials come from the OS keychain, the environment or an explicitly named dotenv file; they are never
  logged or returned by a tool.
- Each session needs a 2FA approval on your phone.
- Tokens live in memory only. On logout and when the server stops, the session is revoked at comdirect so it
  cannot be extended; the last access token expires within 10 minutes.
- The server refuses new logins after three unconfirmed TAN challenges, before comdirect locks the access at five.

The threat model and how to report vulnerabilities: [SECURITY.md](../../SECURITY.md).
