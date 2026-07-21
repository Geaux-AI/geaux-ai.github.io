# Bookkeeping Agent — starter kit

Upload a bank statement, invoice, or photo of a check → the agent extracts the transactions, stages them in a Google Sheets ledger, you approve them, and it posts them to QuickBooks Online. Kills the tedious double data entry.

Built by the GEAUX AI team:
- **finance** seat — the ledger schema, the controls, the reconciliation.
- **developers** seat — the QuickBooks MCP server and the extraction skill.

## The one rule that makes it safe

**Nothing posts to QuickBooks until a human sets `Status = Approved` in the ledger.** Every transaction carries a permanent `Txn_ID` that doubles as the QuickBooks idempotency key, so nothing is ever posted twice — even on a retry. That single gate is what lets an agent touch the books at 25–50 documents/week without creating a mess.

## What's in the box

| Folder | What it is | Runs where |
|---|---|---|
| `ledger/Bookkeeping-Ledger-Template.xlsx` | The QuickBooks-ready ledger: Transactions, Vendor Map, Reconciliation, Instructions tabs, with dedup + tie-out formulas | Import into **Google Sheets** |
| `extraction-skill/SKILL.md` | Reads statements/invoices/checks into a strict JSON schema (integer cents, per-field confidence, reconciliation check) | A **skill** the agent invokes |
| `quickbooks-mcp/` | MCP server that posts transactions to QuickBooks Online, idempotently | A **local MCP server** |
| `agent/AGENT.md` | The agent persona that wires the three together | A **Claude Project / agent** |
| `agent/dedup.gs` | Google Apps Script that flags duplicate documents and locks posted rows | **Apps Script** on the sheet |

## The five solution shapes, applied

This use case resolves to a **combination** — which is exactly what the orchestrator recommended:
- **Agent** — the orchestrating persona (`agent/AGENT.md`).
- **Skill** (workflow) — document extraction (`extraction-skill/`).
- **Connector** — Google Sheets (off-the-shelf; you connect it, no build).
- **MCP server** — QuickBooks Online (`quickbooks-mcp/`; the one real build, because QBO has no reliable off-the-shelf connector).

## Setup (about an hour, plus QuickBooks app approval)

1. **Ledger.** Upload `ledger/Bookkeeping-Ledger-Template.xlsx` to Google Drive → open with Google Sheets. Fill in the **Vendor Map** tab with your real vendors → QuickBooks categories.
2. **Guard (optional but recommended).** Extensions → Apps Script → paste `agent/dedup.gs` → run `setup()` once.
3. **QuickBooks MCP server.** Follow `quickbooks-mcp/README.md`: create an Intuit developer app, get sandbox credentials and a refresh token, fill `.env`, and run the server. Test against the QuickBooks **sandbox** before going live.
4. **Agent.** Create a Claude Project (or agent) using `agent/AGENT.md` as its instructions. Connect the Google Sheets connector (pointed at your ledger) and register the QuickBooks MCP server.
5. **Go.** Upload a document. Review the staged rows. Approve. Watch them post.

## How a transaction flows

```
upload ─▶ extraction skill ─▶ dedup (hash) ─▶ Vendor Map categorize
       ─▶ write row: Status = Needs Review
       ─▶ [HUMAN reviews + approves] ─▶ Status = Approved
       ─▶ QuickBooks MCP post_transaction() (idempotent by Txn_ID)
       ─▶ write back QBO_Txn_ID, Status = Posted-QBO
       ─▶ weekly three-way reconciliation (Sheets ↔ Bank ↔ QuickBooks)
```

## Controls (finance seat)

- **Approval gate** — the one rule above.
- **Idempotency** — `Txn_ID` is the QuickBooks idempotency key; the MCP server looks it up before creating anything.
- **Dedup** — `Source_Doc_Hash` rejects re-uploaded documents; `Dup_Check` flags same date+amount+payee.
- **Confidence gate** — extraction confidence below 0.90 stays in Needs Review.
- **Three-way tie-out** — weekly, Sheets total vs. bank statement vs. QuickBooks; monthly close.

## Notes & limits

- Amounts are **integer cents** end to end; the sheet displays dollars.
- The QuickBooks MCP server targets **QuickBooks Online** (not Desktop) and needs real Intuit credentials — build and test on the sandbox first.
- The ledger's formulas were verified by inspection; automated LibreOffice recalc wasn't available in the build environment, but the workbook uses only Google-Sheets-safe functions and recalculates on import.
