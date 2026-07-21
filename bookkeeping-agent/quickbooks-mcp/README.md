# QuickBooks Online MCP Server

An MCP server that lets an AI bookkeeping agent post **human-approved**
transactions from a Google Sheets ledger into **QuickBooks Online (QBO)** —
idempotently, so a transaction is never posted twice.

It exposes six tools:

| Tool | What it does |
| --- | --- |
| `find_or_create_vendor(name)` | Return a Vendor id by DisplayName, creating it if missing. |
| `find_account(name_or_type)` | Resolve an expense/bank/income account to its id (by Name, then AccountType). |
| `find_transaction_by_txn_id(txn_id)` | Look up an already-posted txn by its ledger id (the idempotency read). |
| `create_expense(...)` | Create a Purchase (expense). |
| `create_deposit(...)` | Create a Deposit. |
| `post_transaction(...)` | **Primary entry point.** Idempotent dispatcher: checks `txn_id` first, then routes to expense/deposit. |

---

## How it works

- **Auth**: reads OAuth2 credentials from the environment and exchanges the
  long-lived **refresh token** for short-lived **access tokens** against Intuit's
  token endpoint. On any `401` it refreshes the access token once and retries.
  Intuit rotates the refresh token on every refresh; the newest one is kept in
  memory and (if `QBO_TOKEN_CACHE_FILE` is set) persisted to disk.
- **REST**: talks directly to the QBO Accounting API v3
  (`/v3/company/{realmId}/...`) with async `httpx`. No third-party QBO client is
  required at runtime.
- **Money**: the ledger stores integer **cents**; the QBO API uses decimal
  **dollars**. The agent passes dollars (`cents / 100`); every amount is
  validated as positive and rounded to 2 decimals (`ROUND_HALF_UP`).

### Idempotency design (the important part)

Every transaction is posted with the ledger's `txn_id` written into the QBO
**`DocNumber`** field. `DocNumber` is *filterable* in the QBO query language on
both `Purchase` and `Deposit`, so we can look a transaction up **before**
creating it:

```
SELECT * FROM Purchase WHERE DocNumber = '<txn_id>'
SELECT * FROM Deposit  WHERE DocNumber = '<txn_id>'
```

`post_transaction` **always** runs this lookup first. If a match exists it
returns the existing QBO id (`"status": "exists"`, `"created": false`) and does
**not** create a duplicate. Only if nothing matches does it create the entity.

`DocNumber` is capped at **21 characters**, so `txn_id` is validated against that
limit — use a short, stable ledger key (row hash, sequence number, or a
`YYYYMMDD-NNN` style id). The full `txn_id` is also stamped into `PrivateNote`
for human traceability in the QBO UI.

> Direct `create_expense` / `create_deposit` calls do **not** perform the
> pre-check — they exist for composition and manual use. Prefer
> `post_transaction` for guaranteed idempotency. (Intuit's per-request
> `RequestId` idempotency parameter dedupes only identical requests within a
> short window, so it is not a substitute for the durable `DocNumber` lookup.)

### Approval gate design

This server is a **posting** service, not an approval authority. The intended
flow:

1. A transaction lands in the Google Sheets ledger.
2. A **human approves** it (e.g. sets an `Approved` column / status).
3. The agent reads only approved rows and calls `post_transaction` for each.
4. This server posts to QBO idempotently and returns the QBO id, which the agent
   writes back to the ledger row (so the sheet records what was posted).

The server trusts that it is only called for approved rows — it does not read the
sheet or re-check approval. Keep the approval check in the agent/orchestration
layer, and treat this server's credentials as write-capable to your books.

---

## Setup

### 1. Create an Intuit app

1. Sign in at <https://developer.intuit.com> and open the **Developer Dashboard**.
2. **My Apps → Create an app →** select the **QuickBooks Online Accounting API**
   scope.
3. Open the app → **Keys & credentials**. Note the two credential sets:
   - **Development keys** → use with `QBO_ENVIRONMENT=sandbox`.
   - **Production keys** → use with `QBO_ENVIRONMENT=production`.

### 2. Get a sandbox company

The developer account comes with a **sandbox company**
(<https://developer.intuit.com/app/developer/sandbox>). Its **Realm ID** (company
id) is shown there — that's your `QBO_REALM_ID` for sandbox.

### 3. Get a refresh token

Easiest path — the **OAuth 2.0 Playground**
(<https://developer.intuit.com/app/developer/playground>):

1. Select your app and the `com.intuit.quickbooks.accounting` scope.
2. Click through **Get authorization code → Get tokens**.
3. Copy the **Refresh Token** → `QBO_REFRESH_TOKEN`, and the **Realm ID** →
   `QBO_REALM_ID`.

Or programmatically with the `intuit-oauth` library (installed as `intuitlib`):

```python
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes

ac = AuthClient(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, "sandbox")
print(ac.get_authorization_url([Scopes.ACCOUNTING]))  # open, approve, get ?code=&realmId=
ac.get_bearer_token(auth_code, realm_id=realm_id)
print("REFRESH_TOKEN:", ac.refresh_token)
print("REALM_ID:", ac.realm_id)
```

### 4. Configure environment

```bash
cp .env.example .env
# edit .env and fill in the four required values
```

### 5. Install and run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# stdio MCP server (what MCP clients launch):
python server.py

# sanity check (no credentials needed):
python server.py --help
```

The refresh token rotates on use. In production, set `QBO_TOKEN_CACHE_FILE` to a
writable path so the server persists the rotated token across restarts instead of
falling back to the (eventually stale) `QBO_REFRESH_TOKEN` env value.

---

## Register with an MCP client

### Claude Desktop

Add to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "quickbooks": {
      "command": "python",
      "args": ["/absolute/path/to/quickbooks-mcp/server.py"],
      "env": {
        "QBO_CLIENT_ID": "...",
        "QBO_CLIENT_SECRET": "...",
        "QBO_REFRESH_TOKEN": "...",
        "QBO_REALM_ID": "...",
        "QBO_ENVIRONMENT": "sandbox",
        "QBO_TOKEN_CACHE_FILE": "/absolute/path/to/token-cache.json"
      }
    }
  }
}
```

Use the venv's Python (`.venv/bin/python`) as `command` if you installed into a
virtualenv. Restart the client and the six tools appear.

### Claude Code (CLI)

```bash
claude mcp add quickbooks -- /absolute/path/to/.venv/bin/python \
  /absolute/path/to/quickbooks-mcp/server.py
```

(Set the `QBO_*` variables in the environment where the client launches the
server, or via your MCP client's env config.)

---

## Tool call examples

Post an approved expense (idempotent):

```json
{
  "name": "post_transaction",
  "arguments": {
    "txn_id": "20260721-014",
    "type": "expense",
    "date": "2026-07-21",
    "payee": "Acme Supplies",
    "amount": 42.50,
    "account_name": "Office Supplies",
    "bank_account_name": "Checking",
    "memo": "Printer paper"
  }
}
```

Calling it again with the same `txn_id` returns the existing id and
`"created": false`.

Post an approved deposit:

```json
{
  "name": "post_transaction",
  "arguments": {
    "txn_id": "20260721-015",
    "type": "deposit",
    "date": "2026-07-21",
    "payee": "Client Co",
    "amount": 1500.00,
    "account_name": "Sales",
    "bank_account_name": "Checking",
    "memo": "Invoice 5"
  }
}
```

---

## Behavior notes & v1 scope

- **PaymentType** on a Purchase is derived from the paying account: `CreditCard`
  when paying from a credit-card account, otherwise `Cash`. There is no separate
  payment-type parameter; adjust `_derive_payment_type` in `server.py` if the
  ledger later distinguishes checks.
- **Deposits** record the `payer` in the line description and `PrivateNote`. v1
  does **not** create QBO `Customer` records or set `DepositLineDetail.Entity`.
- **Account lookup** matches Name exactly first, then falls back to `AccountType`
  (`Bank`, `Expense`, `Income`, `CreditCard`, …). Use `find_account` to confirm
  exact names before posting.
- **Amounts** are single-line only in v1 (one expense/income account per
  transaction). Split transactions would need a multi-line extension.
- Verified against the public Intuit QuickBooks Online Accounting API v3 docs and
  the `python-quickbooks` / `intuit-oauth` libraries (July 2026). Where a detail
  could not be confirmed from public docs, it is flagged in a `NOTE:` comment in
  `server.py`.

## Security

- Treat `.env` and `QBO_TOKEN_CACHE_FILE` as secrets — never commit them; restrict
  file permissions to the service user.
- These credentials can write to your live books when
  `QBO_ENVIRONMENT=production`. Develop and test against **sandbox** first.
