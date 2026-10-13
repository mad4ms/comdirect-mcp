# Troubleshoot

The server logs to stderr. Your MCP client shows these logs: Claude Desktop under *Settings → Developer*, Claude
Code via `/mcp`, VS Code in the *Output* panel (*MCP: List Servers → Show Output*).

## Login

| Message | Cause | Fix |
| --- | --- | --- |
| `Missing credentials: ...` | The listed values are neither in the environment, the keychain nor the file named by `COMDIRECT_ENV_FILE` (a `.env` in the working directory is not read) | `comdirect-mcp configure`, see [Manage credentials](manage-credentials.md) |
| `Primary OAuth failed (HTTP 401)` | Wrong Client ID/Secret, Zugangsnummer or PIN | Check the values; do not retry blindly, repeated failures can lock the access |
| `comdirect offered TAN method M_TAN/P_TAN instead of photoTAN push` | photoTAN Push is not activated, or comdirect ignored the requested method | Activate photoTAN Push and set it as default in the online banking |
| `... TAN challenges were started without a confirmed TAN ...` | Protection against the lock after 5 unconfirmed challenges | Log in once on comdirect.de with a TAN, then restart the MCP server (restart your client) |
| `Login was not approved by the user. ...` | The dialog was declined, cancelled (some clients cancel without showing it) or submitted without ticking *Freigegeben*; the message names which | Call `login` again only when the user is ready to approve; each attempt counts as an unconfirmed challenge |
| `TAN confirmation failed` | The dialog was confirmed before the push was approved in the app, or the push expired | Approve in the app first, then confirm; call `login` again |
| Dialog approved, but the login reports *declined* | The client sent `decline` | Set `COMDIRECT_MCP_LOG_FILE`, log in once and check the `login round` and `login answer` lines: they show the client, its elicitation capability and its raw answer. A `decline` within milliseconds comes from the client, not from you; the server then waits `COMDIRECT_MCP_PUSH_TAN_WAIT` seconds for the approval in the app (log line `Client answered decline after ...`). If the client declines later than one second without a dialog, set `COMDIRECT_MCP_SKIP_ELICITATION=1` |
| Login hangs, then the client reports a timeout | The client waits for the dialog or the fallback window | Approve faster, or raise the client's tool timeout |

## During use

| Message | Cause | Fix |
| --- | --- | --- |
| `Not logged in to comdirect. Call the login tool first.` | No session yet, or after `logout` | Let the assistant call `login` |
| `comdirect session is no longer valid` / `token refresh failed` | comdirect ended the session after inactivity | Call `login` again |
| `comdirect API error: HTTP 4xx/5xx` | comdirect rejected or failed the request | Retry later; check the arguments (e.g. an `account_id` from `list_accounts`) |
| `Document is ... bytes, above the limit` | The document exceeds `COMDIRECT_MCP_MAX_DOCUMENT_BYTES` | Raise the limit or download it in the online banking |

## Setup

| Symptom | Fix |
| --- | --- |
| Client cannot start the server (`uvx: command not found`) | Use the absolute path to `uvx` in the client config |
| `No usable OS keychain` when running `configure` | No keychain backend (e.g. Linux without desktop session); use environment variables |
| macOS asks whether Python may access the Keychain | Choose *Always Allow* for the interpreter that runs the server |
| The assistant does not use the tools | Check the server is enabled in the client and the model supports tool calling |

## Still stuck?

Open an [issue](https://github.com/mad4ms/comdirect-mcp/issues/new/choose) with the version, your client and
anonymized logs. Never post credentials or real banking data.
