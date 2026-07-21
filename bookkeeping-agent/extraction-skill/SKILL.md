---
name: bookkeeping-extraction
description: Extract transactions from an uploaded bank statement (PDF/CSV), invoice (PDF/image), or photo of a check into a strict JSON schema, with a reconciliation check and per-field confidence. Use this whenever a document is uploaded to the bookkeeping agent before anything is written to the ledger.
license: MIT
---

# Bookkeeping extraction

Turn one uploaded document into a clean, verified list of transactions. You never write to the ledger or QuickBooks here — you only produce trustworthy transaction candidates. Accuracy over speed: this is money.

## Pick the path by document type

- **Bank statement, CSV** → parse deterministically. Do NOT use vision. Map columns to fields.
- **Bank statement, PDF with a text layer** → extract the text layer and parse. Use vision only as a fallback for scanned/image-only PDFs.
- **Invoice or check photo (image or image-PDF)** → use vision (read the image directly).

## Output schema (return exactly this JSON, nothing else)

```json
{
  "source_file": "<original filename>",
  "source_doc_hash": "<sha256 of the file bytes>",
  "document_type": "bank_statement | invoice | check",
  "statement_total_cents": <integer or null>,
  "transactions": [
    {
      "txn_id": "<uuid4 you generate>",
      "date": "YYYY-MM-DD",
      "payee": "<string>",
      "amount_cents": <positive integer, cents>,
      "type": "Expense | Deposit | Transfer",
      "memo": "<string>",
      "bank_ref": "<check# or bank reference, or ''>",
      "confidence": <0.00-1.00>,
      "low_confidence_fields": ["<field names below threshold>"]
    }
  ],
  "reconciliation": {
    "sum_of_transactions_cents": <integer>,
    "expected_total_cents": <integer or null>,
    "matches": <true|false>,
    "note": "<explain any mismatch>"
  }
}
```

## Hard rules

1. **Money is integer cents.** `128.44` → `12844`. Never use floats for amounts. Never round silently.
2. **Amount is always positive.** Direction lives in `type`. A debit/withdrawal/payment is `Expense`; a credit/deposit/payout is `Deposit`; a move between own accounts is `Transfer`.
3. **Generate a fresh `txn_id` (uuid4) per transaction.** This becomes the permanent idempotency key. Never reuse one.
4. **Compute `source_doc_hash` = SHA-256 of the file bytes.** It lets the ledger reject a re-uploaded document.
5. **Reconcile before returning.** Sum the transactions and compare to the document's stated total (statement ending balance change, invoice total, or check amount). Set `reconciliation.matches` and explain any gap. A mismatch is a flag, not a silent pass.
6. **Confidence gate.** Score each transaction 0–1. Any field you're unsure of goes in `low_confidence_fields`. The downstream ledger will force anything below the org's threshold (suggested 0.90) into `Needs Review`.
7. **Never guess the QuickBooks account/category here.** That mapping happens against the Vendor Map tab during review. Leave categorization out of extraction.

## Then hand off

Return only the JSON. The agent takes it from here: it checks the hash for duplicates, applies the Vendor Map, writes rows to the Google Sheet with `Status = Needs Review`, and waits for human approval before anything reaches QuickBooks.
