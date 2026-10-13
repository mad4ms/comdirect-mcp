# Categorize transactions

`summarize_transactions` can group spending by your own categories, such as groceries, rent or insurance. The
rules live in a file on your computer and are applied by the server, so the result is the same every time and the
assistant does not have to guess categories from payment texts.

## Create the rules file

The server reads `~/.config/comdirect-mcp/categories.toml` (or `$XDG_CONFIG_HOME/comdirect-mcp/categories.toml`).
Set `COMDIRECT_MCP_CATEGORIES` to use a different path.

```toml
[[rule]]
category = "Lebensmittel"
counterparty = ["REWE", "EDEKA", "ALDI", "LIDL"]

[[rule]]
category = "Versicherungen"
type = "DIRECT_DEBIT"
counterparty = ["Allianz", "HUK-COBURG"]

[[rule]]
category = "Umbuchung"
purpose = "Übertrag"

[[rule]]
category = "Gehalt"
direction = "in"
counterparty = "Arbeitgeber GmbH"
```

Each `[[rule]]` has a `category` and at least one condition:

| Key | Matches |
| --- | --- |
| `counterparty` | Text or list of texts in the counterparty name |
| `purpose` | Text or list of texts in the payment reference |
| `type` | Text or list of texts in the transaction type, e.g. `DIRECT_DEBIT`, `TRANSFER` |
| `direction` | `"in"` or `"out"` |

- Texts match case-insensitively anywhere in the field (`"rewe"` matches `REWE Markt GmbH`).
- All conditions of a rule must match; for a list, one of its texts is enough.
- The first matching rule wins, so put specific rules before general ones.
- Transactions without a matching rule are grouped as `(uncategorized)`.

The file is read on every call, so changes apply without restarting the server. Unknown keys and empty values
are rejected with an error that names the rule.

## Use it

Ask for spending by category, or start the `monthly_review` prompt, which uses the categories when the file
exists. The assistant calls `summarize_transactions` with `group_by="category"`.

To improve the rules, ask the assistant to look at the `(uncategorized)` group and to suggest new rules. It can
read the current file through the `comdirect://categories` resource, but it cannot change it; you edit the file.

A category named for transfers between your own accounts, as in the example above, keeps them out of your
spending categories.
