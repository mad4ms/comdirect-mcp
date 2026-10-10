# Get comdirect API access

comdirect offers its REST API to private customers free of charge. You need four values:

| Value | Where it comes from | Variable / keychain entry |
| --- | --- | --- |
| Client ID | Developer access in the online banking (starts with `User_`) | `COMDIRECT_CLIENT_ID` |
| Client Secret | Developer access in the online banking | `COMDIRECT_CLIENT_SECRET` |
| Zugangsnummer | Your online banking login | `COMDIRECT_USERNAME` |
| PIN | Your online banking PIN | `COMDIRECT_PASSWORD` |

## Activate the developer access

1. Log in to the [comdirect online banking](https://www.comdirect.de) in your browser.
2. Go to **Verwaltung → Entwicklerzugang**.
3. Activate access to the REST API and follow the steps shown there.
4. Copy the **Client ID** and **Client Secret** you receive and store them right away, e.g. with
   `comdirect-mcp configure` (see [Manage credentials](manage-credentials.md)). Treat the Client Secret like a
   password.

comdirect's own documentation of the API (the PDF *comdirect REST API – Schnittstellenspezifikation* and the
Swagger specification) is linked on the developer access page and on the
[comdirect REST API page](https://www.comdirect.de/cms/kontakt-zugaenge-api.html).

## Set up the TAN method

Every API session needs a second factor. `comdirect-mcp` supports **photoTAN Push**: comdirect sends a push
notification to the photoTAN app and you approve it there.

- Install the comdirect photoTAN app and activate photoTAN Push for your account if you have not done so yet.
- The server explicitly requests photoTAN Push for each login. If comdirect still offers a different method,
  set photoTAN Push as your default TAN method in the online banking settings. (The Python library also
  supports SMS-TAN and the photoTAN graphic, see [Use the Python library](use-the-python-library.md).)

> [!WARNING]
> comdirect locks the online banking access after **five TAN challenges without a confirmed TAN** in between,
> and after **three wrong TANs** (after two wrong TANs via the API, one correct TAN on comdirect.de resets the
> counter). Every `login` that is not confirmed counts as a challenge. The MCP server therefore refuses new
> logins after three unconfirmed challenges. If a login fails, find the cause before trying again, see
> [Troubleshoot](troubleshoot.md).

## Limits

- An access token is valid for 10 minutes (`expires_in: 599`) and is refreshed automatically. The session TAN
  stays valid until the last access/refresh token expires; after that the assistant has to call `login` again.
- `logout` and stopping the server revoke the session at comdirect: it cannot be extended anymore, and the last
  access token expires within 10 minutes.
- Besides reading accounts, transactions, depots and the postbox, the API can also place securities orders.
  `comdirect-mcp` uses only the read-only endpoints and has no tool that could place an order.
