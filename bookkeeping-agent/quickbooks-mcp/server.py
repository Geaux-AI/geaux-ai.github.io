#!/usr/bin/env python3
"""QuickBooks Online (QBO) MCP server for small-business bookkeeping automation.

Purpose
-------
This server is called by an AI agent *after a human has approved a transaction*
in a Google Sheets ledger. Its single job is to post that transaction to
QuickBooks Online **idempotently** so a duplicate is never created, no matter how
many times the agent retries.

Design at a glance
------------------
* Auth: OAuth2 refresh-token -> access-token exchange against Intuit's token
  endpoint, with automatic refresh-and-retry on a 401. Intuit rotates the
  refresh token on each refresh; the newest one is kept in memory and, if
  ``QBO_TOKEN_CACHE_FILE`` is set, persisted to disk so restarts survive.
* Idempotency: every posted transaction carries the ledger's ``txn_id`` in the
  QBO ``DocNumber`` field. ``DocNumber`` is filterable in the QBO query language
  on both Purchase and Deposit, so we can look a transaction up *before*
  creating it. ``post_transaction`` ALWAYS does this lookup first and returns the
  existing QBO id instead of creating a duplicate.
* Money: the ledger stores integer **cents**. The QBO API works in decimal
  **dollars**. The agent passes dollars (cents / 100); every amount is validated
  as positive and quantized to 2 decimal places before it is sent.

Verification notes (checked against the public Intuit QuickBooks Online
Accounting API v3 docs and the python-quickbooks / intuit-oauth libraries):
  * Token endpoint: POST https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer
    (Basic auth = client_id:client_secret, form body grant_type=refresh_token).
  * API base: sandbox  -> https://sandbox-quickbooks.api.intuit.com
              production-> https://quickbooks.api.intuit.com
  * Entity create:  POST /v3/company/{realmId}/{entity}
  * Query:          GET  /v3/company/{realmId}/query?query=<SQL-like>
  * Purchase requires: PaymentType, AccountRef (the bank/CC/cash account paid
    FROM) and a Line[] whose DetailType is "AccountBasedExpenseLineDetail"
    carrying the expense-category AccountRef and Amount.
  * Deposit requires: DepositToAccountRef (bank account funds land in) and a
    Line[] whose DetailType is "DepositLineDetail" carrying the source/income
    AccountRef and Amount.
  * DocNumber exists and is filterable on both Purchase and Deposit; its max
    length is 21 characters, so txn_id is validated against that limit.

This module deliberately talks to the REST API directly with async httpx rather
than wrapping the (synchronous) python-quickbooks client, so the OAuth refresh,
401 retry, and idempotency query logic are explicit and fully under our control.
The equivalent library calls are noted in comments where relevant.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP("quickbooks_mcp")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Intuit's OAuth2 token endpoint is the same for sandbox and production.
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

API_BASE_BY_ENV = {
    "sandbox": "https://sandbox-quickbooks.api.intuit.com",
    "production": "https://quickbooks.api.intuit.com",
}

# QBO "minor version" pins the API response/field schema. It is configurable via
# QBO_MINOR_VERSION; 70 is a widely-available stable value. Check Intuit's minor
# version changelog for the current maximum if you need newer fields.
DEFAULT_MINOR_VERSION = "70"

# DocNumber (the idempotency carrier) is capped at 21 characters by QBO.
DOCNUMBER_MAX_LEN = 21

# Refresh the access token this many seconds before it actually expires, so an
# in-flight request never races the expiry.
TOKEN_EXPIRY_SKEW_SECONDS = 60

HTTP_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Configuration (loaded lazily so `python server.py --help` works without creds)
# ---------------------------------------------------------------------------

class QBOConfig(BaseModel):
    """Immutable runtime configuration pulled from environment variables."""

    client_id: str
    client_secret: str
    refresh_token: str
    realm_id: str
    environment: str
    minor_version: str
    token_cache_file: Optional[str]

    @property
    def api_base(self) -> str:
        return API_BASE_BY_ENV[self.environment]


def _load_config() -> QBOConfig:
    """Read and validate configuration from the environment.

    Raises a clear RuntimeError (surfaced to the agent as a tool error) if any
    required variable is missing, rather than failing deep inside an HTTP call.
    """
    required = ["QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REFRESH_TOKEN", "QBO_REALM_ID"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". See .env.example for how to obtain each value."
        )

    environment = os.environ.get("QBO_ENVIRONMENT", "sandbox").strip().lower()
    if environment not in API_BASE_BY_ENV:
        raise RuntimeError(
            f"QBO_ENVIRONMENT must be 'sandbox' or 'production', got {environment!r}."
        )

    return QBOConfig(
        client_id=os.environ["QBO_CLIENT_ID"].strip(),
        client_secret=os.environ["QBO_CLIENT_SECRET"].strip(),
        refresh_token=os.environ["QBO_REFRESH_TOKEN"].strip(),
        realm_id=os.environ["QBO_REALM_ID"].strip(),
        environment=environment,
        minor_version=os.environ.get("QBO_MINOR_VERSION", DEFAULT_MINOR_VERSION).strip(),
        token_cache_file=(os.environ.get("QBO_TOKEN_CACHE_FILE") or None),
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class QBOError(Exception):
    """Raised for QBO API and configuration failures with an agent-friendly message."""


# ---------------------------------------------------------------------------
# OAuth2 + REST client
# ---------------------------------------------------------------------------

class QBOClient:
    """Thin async QBO REST client with OAuth2 refresh and 401 retry.

    Token lifecycle
    ---------------
    We are given a long-lived *refresh token*. We exchange it for a short-lived
    *access token* and cache that in memory. When the access token is near
    expiry, or when the API returns 401, we refresh again. Intuit ROTATES the
    refresh token on every refresh, so we always adopt the refresh token from the
    refresh response and (optionally) persist it to ``QBO_TOKEN_CACHE_FILE`` so a
    process restart does not fall back to a now-invalidated env value.
    """

    def __init__(self, config: QBOConfig):
        self.config = config
        self._access_token: Optional[str] = None
        self._access_token_expiry: float = 0.0  # epoch seconds
        # Start from the cached rotating refresh token if we have one, else env.
        self._refresh_token: str = self._load_cached_refresh_token() or config.refresh_token
        # Serialize refreshes so concurrent tool calls don't stampede the token
        # endpoint. A plain threading.Lock is fine because refreshes are brief and
        # infrequent relative to request volume.
        self._refresh_lock = threading.Lock()

    # -- refresh-token persistence (optional) -------------------------------

    def _load_cached_refresh_token(self) -> Optional[str]:
        path = self.config.token_cache_file
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            token = data.get("refresh_token")
            return token if isinstance(token, str) and token else None
        except (OSError, json.JSONDecodeError):
            # A corrupt cache should never be fatal; fall back to the env token.
            return None

    def _persist_refresh_token(self) -> None:
        path = self.config.token_cache_file
        if not path:
            return
        try:
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"refresh_token": self._refresh_token, "updated_at": time.time()}, fh)
            os.replace(tmp, path)  # atomic on POSIX
        except OSError:
            # Persistence is best-effort; the in-memory token still works for
            # this process's lifetime.
            pass

    # -- token acquisition --------------------------------------------------

    def _refresh_access_token(self) -> None:
        """Exchange the refresh token for a fresh access token (blocking HTTP).

        Uses a synchronous httpx call inside the refresh lock. Equivalent library
        call: intuitlib.client.AuthClient(...).refresh(refresh_token=...), which
        hits the same TOKEN_URL under the hood.
        """
        basic = base64.b64encode(
            f"{self.config.client_id}:{self.config.client_secret}".encode()
        ).decode()
        try:
            resp = httpx.post(
                TOKEN_URL,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
                timeout=HTTP_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise QBOError(f"Network error contacting Intuit token endpoint: {exc}") from exc

        if resp.status_code != 200:
            raise QBOError(
                "Failed to refresh QBO access token "
                f"(HTTP {resp.status_code}): {resp.text[:300]}. "
                "The refresh token may be expired or revoked - re-run the OAuth "
                "flow (see README) to obtain a new QBO_REFRESH_TOKEN."
            )

        payload = resp.json()
        self._access_token = payload["access_token"]
        self._access_token_expiry = time.time() + int(payload.get("expires_in", 3600))
        # Adopt the (possibly rotated) refresh token and persist it.
        new_refresh = payload.get("refresh_token")
        if new_refresh and new_refresh != self._refresh_token:
            self._refresh_token = new_refresh
            self._persist_refresh_token()

    def _ensure_access_token(self, force: bool = False) -> str:
        """Return a valid access token, refreshing if missing/expired/forced."""
        with self._refresh_lock:
            expired = time.time() >= (self._access_token_expiry - TOKEN_EXPIRY_SKEW_SECONDS)
            if force or self._access_token is None or expired:
                self._refresh_access_token()
            assert self._access_token is not None
            return self._access_token

    # -- request plumbing ---------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.config.api_base}/v3/company/{self.config.realm_id}/{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Perform an authenticated QBO API request with one automatic 401 retry.

        The QBO minorversion is always attached. On a 401 (expired/invalid access
        token) we force a token refresh and retry exactly once.
        """
        params = dict(params or {})
        params.setdefault("minorversion", self.config.minor_version)

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            for attempt in (1, 2):
                token = self._ensure_access_token(force=(attempt == 2))
                resp = await client.request(
                    method,
                    self._url(path),
                    params=params,
                    json=json_body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code == 401 and attempt == 1:
                    # Access token rejected: refresh once and retry.
                    continue
                return self._parse_response(resp)
        # Unreachable, but keeps type checkers happy.
        raise QBOError("QBO request failed after token refresh retry.")

    @staticmethod
    def _parse_response(resp: httpx.Response) -> Dict[str, Any]:
        if resp.status_code in (200, 201):
            return resp.json()
        # Surface QBO's structured Fault message when present.
        detail = resp.text[:500]
        try:
            body = resp.json()
            fault = body.get("Fault", {})
            errors = fault.get("Error", [])
            if errors:
                detail = "; ".join(
                    f"{e.get('Message', '')} {e.get('Detail', '')}".strip() for e in errors
                )
        except (json.JSONDecodeError, ValueError):
            pass
        raise QBOError(f"QBO API error (HTTP {resp.status_code}): {detail}")

    # -- high-level helpers -------------------------------------------------

    async def query(self, statement: str) -> Dict[str, Any]:
        """Run a QBO SQL-like query and return the QueryResponse dict."""
        data = await self._request("GET", "query", params={"query": statement})
        return data.get("QueryResponse", {})

    async def create(self, entity: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """POST an entity create and return the created object dict."""
        data = await self._request("POST", entity.lower(), json_body=body)
        # QBO echoes the created object under a capitalized entity key.
        for key, value in data.items():
            if key.lower() == entity.lower():
                return value
        return data


# Module-level lazy singleton so tests / --help do not require credentials.
_client: Optional[QBOClient] = None


def _get_client() -> QBOClient:
    global _client
    if _client is None:
        _client = QBOClient(_load_config())
    return _client


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def _escape_qb(value: str) -> str:
    """Escape a value for safe inclusion in a QBO query WHERE clause.

    The QBO query language uses single-quoted string literals; a literal single
    quote is escaped by doubling it.
    """
    return value.replace("'", "''")


def _normalize_amount(amount: float) -> str:
    """Validate a dollar amount and return it as a 2dp decimal string.

    The ledger stores integer cents; the agent passes dollars (cents / 100). We
    quantize with ROUND_HALF_UP so, e.g., 12.005 -> "12.01". Non-positive or
    non-numeric amounts are rejected.
    """
    try:
        # str() avoids binary float artifacts (Decimal(0.1) != Decimal("0.1")).
        dec = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise QBOError(f"Amount {amount!r} is not a valid number.") from exc
    if dec <= 0:
        raise QBOError(f"Amount must be greater than zero, got {dec}.")
    return str(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _validate_txn_id(txn_id: str) -> str:
    """Validate the ledger idempotency key against QBO DocNumber constraints."""
    txn_id = txn_id.strip()
    if not txn_id:
        raise QBOError("txn_id must be a non-empty string.")
    if len(txn_id) > DOCNUMBER_MAX_LEN:
        raise QBOError(
            f"txn_id {txn_id!r} is {len(txn_id)} chars; QBO DocNumber allows at "
            f"most {DOCNUMBER_MAX_LEN}. Use a shorter, stable ledger id (e.g. a "
            "row hash or sequence number)."
        )
    return txn_id


def _private_note(memo: str, txn_id: str, extra: str = "") -> str:
    """Compose a PrivateNote that keeps a human-readable copy of the txn_id.

    DocNumber is the queryable idempotency key, but we also stamp the full
    context into PrivateNote for auditability inside the QBO UI.
    """
    parts = []
    if memo:
        parts.append(memo.strip())
    if extra:
        parts.append(extra.strip())
    parts.append(f"[ledger txn_id: {txn_id}]")
    return " ".join(p for p in parts if p)


def _ok(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2)


def _err(message: str) -> str:
    return json.dumps({"status": "error", "error": message}, indent=2)


# ---------------------------------------------------------------------------
# Enums / input models
# ---------------------------------------------------------------------------

class TxnType(str, Enum):
    """Supported ledger transaction types for the dispatcher."""
    EXPENSE = "expense"
    DEPOSIT = "deposit"


_STR = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")


class VendorInput(BaseModel):
    model_config = _STR
    name: str = Field(..., description="Vendor DisplayName to find or create (e.g. 'Acme Supplies').", min_length=1, max_length=100)


class AccountInput(BaseModel):
    model_config = _STR
    name_or_type: str = Field(
        ...,
        description=(
            "Chart-of-accounts lookup key. First matched exactly against Account "
            "Name (e.g. 'Office Supplies', 'Checking'); if no name matches, matched "
            "against AccountType (e.g. 'Bank', 'Expense', 'Income', 'CreditCard')."
        ),
        min_length=1,
        max_length=100,
    )


class TxnIdInput(BaseModel):
    model_config = _STR
    txn_id: str = Field(..., description="Ledger idempotency key stored in QBO DocNumber (<=21 chars).", min_length=1, max_length=64)


class ExpenseInput(BaseModel):
    model_config = _STR
    txn_id: str = Field(..., description="Ledger idempotency key -> QBO DocNumber (<=21 chars).", min_length=1, max_length=64)
    date: str = Field(..., description="Transaction date in YYYY-MM-DD format.", pattern=r"^\d{4}-\d{2}-\d{2}$")
    payee: str = Field(..., description="Vendor/payee DisplayName; created if it does not exist.", min_length=1, max_length=100)
    amount: float = Field(..., description="Amount in dollars (ledger cents / 100). Rounded to 2dp.", gt=0)
    account_name: str = Field(..., description="Expense-category account name from the chart of accounts (e.g. 'Office Supplies').", min_length=1, max_length=100)
    bank_account_name: str = Field(..., description="Bank / credit-card / cash account the money is paid FROM (e.g. 'Checking').", min_length=1, max_length=100)
    memo: str = Field(default="", description="Optional memo/description stored on the line and PrivateNote.", max_length=1000)


class DepositInput(BaseModel):
    model_config = _STR
    txn_id: str = Field(..., description="Ledger idempotency key -> QBO DocNumber (<=21 chars).", min_length=1, max_length=64)
    date: str = Field(..., description="Transaction date in YYYY-MM-DD format.", pattern=r"^\d{4}-\d{2}-\d{2}$")
    payer: str = Field(..., description="Who the money came from; stored on the line description and PrivateNote.", min_length=1, max_length=100)
    amount: float = Field(..., description="Amount in dollars (ledger cents / 100). Rounded to 2dp.", gt=0)
    account_name: str = Field(..., description="Income/source account name the deposit is credited to (e.g. 'Sales', 'Owner Contributions').", min_length=1, max_length=100)
    bank_account_name: str = Field(..., description="Bank account the funds are deposited INTO (e.g. 'Checking').", min_length=1, max_length=100)
    memo: str = Field(default="", description="Optional memo/description stored on the line and PrivateNote.", max_length=1000)


class PostTransactionInput(BaseModel):
    model_config = _STR
    txn_id: str = Field(..., description="Ledger idempotency key -> QBO DocNumber (<=21 chars).", min_length=1, max_length=64)
    type: TxnType = Field(..., description="Transaction type: 'expense' or 'deposit'.")
    date: str = Field(..., description="Transaction date in YYYY-MM-DD format.", pattern=r"^\d{4}-\d{2}-\d{2}$")
    payee: str = Field(..., description="Vendor (expense) or payer (deposit) name.", min_length=1, max_length=100)
    amount: float = Field(..., description="Amount in dollars (ledger cents / 100). Rounded to 2dp.", gt=0)
    account_name: str = Field(..., description="Expense-category (expense) or income/source (deposit) account name.", min_length=1, max_length=100)
    bank_account_name: str = Field(..., description="Bank/credit-card/cash account (paid FROM for expense, INTO for deposit).", min_length=1, max_length=100)
    memo: str = Field(default="", description="Optional memo/description.", max_length=1000)

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        return v


# ---------------------------------------------------------------------------
# Core implementations (shared by tools and the dispatcher; kept DRY)
# ---------------------------------------------------------------------------

async def _find_vendor(name: str) -> Optional[Dict[str, Any]]:
    client = _get_client()
    # Equivalent library call: Vendor.filter(DisplayName=name, qb=client)
    qr = await client.query(
        f"SELECT * FROM Vendor WHERE DisplayName = '{_escape_qb(name)}'"
    )
    vendors = qr.get("Vendor", [])
    return vendors[0] if vendors else None


async def _find_or_create_vendor(name: str) -> Dict[str, Any]:
    existing = await _find_vendor(name)
    if existing:
        return {"id": existing["Id"], "display_name": existing["DisplayName"], "created": False}
    created = await _get_client().create("vendor", {"DisplayName": name})
    return {"id": created["Id"], "display_name": created["DisplayName"], "created": True}


async def _find_account(name_or_type: str) -> Optional[Dict[str, Any]]:
    """Look up an account by exact Name, then fall back to AccountType."""
    client = _get_client()
    by_name = await client.query(
        f"SELECT * FROM Account WHERE Name = '{_escape_qb(name_or_type)}'"
    )
    accounts = by_name.get("Account", [])
    if not accounts:
        # Fall back to AccountType (e.g. 'Bank', 'Expense', 'Income', 'CreditCard').
        by_type = await client.query(
            f"SELECT * FROM Account WHERE AccountType = '{_escape_qb(name_or_type)}' "
            "AND Active = true"
        )
        accounts = by_type.get("Account", [])
    if not accounts:
        return None
    acct = accounts[0]
    return {
        "id": acct["Id"],
        "name": acct.get("Name"),
        "account_type": acct.get("AccountType"),
        "account_sub_type": acct.get("AccountSubType"),
    }


async def _require_account(name_or_type: str, role: str) -> Dict[str, Any]:
    acct = await _find_account(name_or_type)
    if not acct:
        raise QBOError(
            f"No account found for {role} matching name or type {name_or_type!r}. "
            "Use find_account to confirm the exact Name/AccountType in the chart "
            "of accounts."
        )
    return acct


async def _find_transaction_by_txn_id(txn_id: str) -> Optional[Dict[str, Any]]:
    """Return the existing QBO txn carrying this txn_id in DocNumber, if any.

    Queries Purchase and Deposit (the two entity types this server creates). This
    is the guarantee behind idempotency: it MUST be called before any create.
    """
    txn_id = _validate_txn_id(txn_id)
    client = _get_client()
    escaped = _escape_qb(txn_id)
    for entity, txn_type in (("Purchase", "expense"), ("Deposit", "deposit")):
        qr = await client.query(
            f"SELECT * FROM {entity} WHERE DocNumber = '{escaped}'"
        )
        rows = qr.get(entity, [])
        if rows:
            row = rows[0]
            return {
                "found": True,
                "type": txn_type,
                "entity": entity,
                "id": row["Id"],
                "doc_number": row.get("DocNumber"),
                "total_amt": row.get("TotalAmt"),
                "txn_date": row.get("TxnDate"),
            }
    return None


def _derive_payment_type(bank_account_type: Optional[str]) -> str:
    """Map the paying account's type to a QBO Purchase PaymentType.

    Valid PaymentType values are Cash, Check, CreditCard. We choose CreditCard
    when paying from a credit-card account, otherwise Cash. (There is no separate
    payment_type parameter in the tool signature; adjust here if the ledger later
    distinguishes checks.)
    """
    if (bank_account_type or "").lower() == "creditcard":
        return "CreditCard"
    return "Cash"


async def _create_expense(inp: ExpenseInput) -> Dict[str, Any]:
    txn_id = _validate_txn_id(inp.txn_id)
    amount = _normalize_amount(inp.amount)

    vendor = await _find_or_create_vendor(inp.payee)
    expense_acct = await _require_account(inp.account_name, "expense category")
    bank_acct = await _require_account(inp.bank_account_name, "paying (bank/credit-card) account")

    body = {
        "PaymentType": _derive_payment_type(bank_acct.get("account_type")),
        "AccountRef": {"value": bank_acct["id"]},        # account paid FROM
        "EntityRef": {"value": vendor["id"], "type": "Vendor"},
        "TxnDate": inp.date,
        "DocNumber": txn_id,                              # idempotency key
        "PrivateNote": _private_note(inp.memo, txn_id),
        "Line": [
            {
                "Amount": float(amount),
                "DetailType": "AccountBasedExpenseLineDetail",
                "Description": inp.memo or None,
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": expense_acct["id"]}  # expense category
                },
            }
        ],
    }
    created = await _get_client().create("purchase", body)
    return {
        "status": "created",
        "type": "expense",
        "entity": "Purchase",
        "id": created["Id"],
        "doc_number": created.get("DocNumber"),
        "total_amt": created.get("TotalAmt"),
        "vendor_id": vendor["id"],
        "expense_account_id": expense_acct["id"],
        "bank_account_id": bank_acct["id"],
    }


async def _create_deposit(inp: DepositInput) -> Dict[str, Any]:
    txn_id = _validate_txn_id(inp.txn_id)
    amount = _normalize_amount(inp.amount)

    # NOTE: DepositLineDetail.Entity can reference a Customer/Vendor, but this v1
    # does not create Customer records. The payer is recorded in the line
    # description and PrivateNote for traceability instead.
    source_acct = await _require_account(inp.account_name, "income/source account")
    bank_acct = await _require_account(inp.bank_account_name, "deposit-to bank account")

    line_desc = f"{inp.payer}: {inp.memo}".strip(": ").strip()
    body = {
        "DepositToAccountRef": {"value": bank_acct["id"]},   # funds land here
        "TxnDate": inp.date,
        "DocNumber": txn_id,                                 # idempotency key
        "PrivateNote": _private_note(inp.memo, txn_id, extra=f"payer={inp.payer}"),
        "Line": [
            {
                "Amount": float(amount),
                "DetailType": "DepositLineDetail",
                "Description": line_desc or None,
                "DepositLineDetail": {
                    "AccountRef": {"value": source_acct["id"]}  # source/income account
                },
            }
        ],
    }
    created = await _get_client().create("deposit", body)
    return {
        "status": "created",
        "type": "deposit",
        "entity": "Deposit",
        "id": created["Id"],
        "doc_number": created.get("DocNumber"),
        "total_amt": created.get("TotalAmt"),
        "source_account_id": source_acct["id"],
        "bank_account_id": bank_acct["id"],
    }


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="find_or_create_vendor",
    annotations={
        "title": "Find or Create Vendor",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def find_or_create_vendor(params: VendorInput) -> str:
    """Return the QBO Vendor id for a DisplayName, creating the vendor if absent.

    Looks the vendor up by exact DisplayName. If found, returns the existing id;
    otherwise creates a minimal Vendor (DisplayName only) and returns the new id.
    Safe to call repeatedly - it will not create duplicate vendors.

    Args:
        params (VendorInput):
            - name (str): Vendor DisplayName to find or create.

    Returns:
        str: JSON object:
            {"status": "ok", "id": str, "display_name": str, "created": bool}
        or {"status": "error", "error": str}.
    """
    try:
        result = await _find_or_create_vendor(params.name)
        return _ok({"status": "ok", **result})
    except QBOError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001 - surface unexpected errors to the agent
        return _err(f"Unexpected error: {type(exc).__name__}: {exc}")


@mcp.tool(
    name="find_account",
    annotations={
        "title": "Find Chart-of-Accounts Account",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def find_account(params: AccountInput) -> str:
    """Resolve an expense category or bank account to its QBO Account id.

    Matches the input first against Account Name (exact), then against
    AccountType (e.g. 'Bank', 'Expense', 'Income', 'CreditCard') for the first
    active account of that type. Read-only.

    Args:
        params (AccountInput):
            - name_or_type (str): Account Name or AccountType to resolve.

    Returns:
        str: JSON object:
            {"status": "ok", "id": str, "name": str, "account_type": str,
             "account_sub_type": str}
        or {"status": "not_found", ...} or {"status": "error", "error": str}.
    """
    try:
        acct = await _find_account(params.name_or_type)
        if not acct:
            return _ok({
                "status": "not_found",
                "query": params.name_or_type,
                "hint": "No matching Account Name or AccountType. Check the exact chart-of-accounts spelling.",
            })
        return _ok({"status": "ok", **acct})
    except QBOError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(f"Unexpected error: {type(exc).__name__}: {exc}")


@mcp.tool(
    name="find_transaction_by_txn_id",
    annotations={
        "title": "Find Transaction by Ledger txn_id",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def find_transaction_by_txn_id(params: TxnIdInput) -> str:
    """Look up an already-posted QBO transaction by its ledger txn_id.

    Queries Purchase and Deposit for DocNumber == txn_id. This is the read that
    guarantees idempotency and should be called BEFORE creating anything.

    Args:
        params (TxnIdInput):
            - txn_id (str): Ledger idempotency key (stored in QBO DocNumber).

    Returns:
        str: JSON object. When found:
            {"status": "ok", "found": true, "type": "expense"|"deposit",
             "entity": "Purchase"|"Deposit", "id": str, "doc_number": str,
             "total_amt": number, "txn_date": str}
        When not found: {"status": "ok", "found": false, "txn_id": str}.
        On error: {"status": "error", "error": str}.
    """
    try:
        found = await _find_transaction_by_txn_id(params.txn_id)
        if found:
            return _ok({"status": "ok", **found})
        return _ok({"status": "ok", "found": False, "txn_id": params.txn_id.strip()})
    except QBOError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(f"Unexpected error: {type(exc).__name__}: {exc}")


@mcp.tool(
    name="create_expense",
    annotations={
        "title": "Create Expense (Purchase)",
        "readOnlyHint": False,
        "destructiveHint": False,
        # Not idempotent on its own - call post_transaction (or check
        # find_transaction_by_txn_id first) to avoid duplicates.
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def create_expense(params: ExpenseInput) -> str:
    """Create a QBO Purchase (expense) with txn_id stamped into DocNumber.

    Resolves the payee (find-or-create Vendor), the expense-category account, and
    the paying bank/credit-card/cash account, then posts a Purchase. PaymentType
    is CreditCard when paying from a credit-card account, else Cash.

    WARNING: This does not check for an existing transaction first. For
    guaranteed idempotency, use post_transaction, which looks up txn_id before
    creating.

    Args:
        params (ExpenseInput): txn_id, date (YYYY-MM-DD), payee, amount (dollars),
            account_name (expense category), bank_account_name (paid from), memo.

    Returns:
        str: JSON object:
            {"status": "created", "type": "expense", "entity": "Purchase",
             "id": str, "doc_number": str, "total_amt": number,
             "vendor_id": str, "expense_account_id": str, "bank_account_id": str}
        or {"status": "error", "error": str}.
    """
    try:
        return _ok(await _create_expense(params))
    except QBOError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(f"Unexpected error: {type(exc).__name__}: {exc}")


@mcp.tool(
    name="create_deposit",
    annotations={
        "title": "Create Deposit",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def create_deposit(params: DepositInput) -> str:
    """Create a QBO Deposit with txn_id stamped into DocNumber.

    Resolves the income/source account and the deposit-to bank account, then
    posts a Deposit. The payer is recorded in the line description and
    PrivateNote (v1 does not create Customer records).

    WARNING: This does not check for an existing transaction first. For
    guaranteed idempotency, use post_transaction.

    Args:
        params (DepositInput): txn_id, date (YYYY-MM-DD), payer, amount (dollars),
            account_name (income/source), bank_account_name (deposited into), memo.

    Returns:
        str: JSON object:
            {"status": "created", "type": "deposit", "entity": "Deposit",
             "id": str, "doc_number": str, "total_amt": number,
             "source_account_id": str, "bank_account_id": str}
        or {"status": "error", "error": str}.
    """
    try:
        return _ok(await _create_deposit(params))
    except QBOError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(f"Unexpected error: {type(exc).__name__}: {exc}")


@mcp.tool(
    name="post_transaction",
    annotations={
        "title": "Post Transaction (idempotent dispatcher)",
        "readOnlyHint": False,
        "destructiveHint": False,
        # Idempotent: repeated calls with the same txn_id return the existing
        # QBO id instead of creating a duplicate.
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def post_transaction(params: PostTransactionInput) -> str:
    """Idempotently post an approved ledger transaction to QuickBooks Online.

    This is the primary entry point for the bookkeeping agent. It ALWAYS looks up
    txn_id first (find_transaction_by_txn_id). If a matching QBO transaction
    already exists it returns that id WITHOUT creating a duplicate; otherwise it
    routes to create_expense or create_deposit based on `type`.

    Only call this AFTER a human has approved the transaction in the ledger - this
    server does not itself gate on approval (see README approval-gate notes).

    Args:
        params (PostTransactionInput): txn_id, type ('expense'|'deposit'),
            date (YYYY-MM-DD), payee (vendor or payer), amount (dollars),
            account_name (expense category or income/source), bank_account_name,
            memo.

    Returns:
        str: JSON object. If it already existed:
            {"status": "exists", "created": false, "type": ..., "entity": ...,
             "id": str, "doc_number": str, ...}
        If newly created:
            {"status": "created", "created": true, ...} (see create_expense /
            create_deposit schemas).
        On error: {"status": "error", "error": str}.
    """
    try:
        txn_id = _validate_txn_id(params.txn_id)

        # 1) Idempotency guard: never create if this txn_id already exists.
        existing = await _find_transaction_by_txn_id(txn_id)
        if existing:
            return _ok({
                "status": "exists",
                "created": False,
                "type": existing["type"],
                "entity": existing["entity"],
                "id": existing["id"],
                "doc_number": existing["doc_number"],
                "total_amt": existing["total_amt"],
                "message": "Transaction with this txn_id already exists in QBO; not creating a duplicate.",
            })

        # 2) Route to the correct creator.
        if params.type == TxnType.EXPENSE:
            result = await _create_expense(ExpenseInput(
                txn_id=txn_id, date=params.date, payee=params.payee,
                amount=params.amount, account_name=params.account_name,
                bank_account_name=params.bank_account_name, memo=params.memo,
            ))
        else:  # TxnType.DEPOSIT
            result = await _create_deposit(DepositInput(
                txn_id=txn_id, date=params.date, payer=params.payee,
                amount=params.amount, account_name=params.account_name,
                bank_account_name=params.bank_account_name, memo=params.memo,
            ))

        return _ok({"created": True, **result})
    except QBOError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(f"Unexpected error: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _print_help() -> None:
    print(__doc__)
    print(
        "\nRequired environment variables:\n"
        "  QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REFRESH_TOKEN, QBO_REALM_ID\n"
        "Optional:\n"
        "  QBO_ENVIRONMENT (sandbox|production, default sandbox)\n"
        "  QBO_MINOR_VERSION (default 70)\n"
        "  QBO_TOKEN_CACHE_FILE (path to persist the rotating refresh token)\n"
        "\nRun as an MCP stdio server:  python server.py\n"
    )


if __name__ == "__main__":
    import sys

    if "--help" in sys.argv or "-h" in sys.argv:
        _print_help()
        sys.exit(0)
    # Default MCP transport is stdio (what Claude Desktop / most MCP clients use).
    mcp.run()
