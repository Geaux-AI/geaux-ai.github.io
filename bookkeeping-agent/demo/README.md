# Live pipeline demo

Runs the Bookkeeping Agent's real pipeline logic end to end against a mock
QuickBooks, so it needs no Intuit or Google credentials. It proves the flow
(read, extract, dedupe, ledger, approve, post, reconcile) and the two safety
controls (idempotent posting, duplicate-upload rejection).

Run it:

    python3 run_demo.py        # first upload: extracts, posts, writes the ledger
    python3 run_demo.py        # same file again: duplicate detected, refused

Reset it:

    rm -f .mock_qbo.json .seen_docs.json demo_ledger.csv

This is a sandbox simulation. The only difference from production is the mock
QuickBooks and a CSV ledger instead of a live Google Sheet. To run it for real,
follow ../QUICKSTART.md to connect your QuickBooks and Google Sheet.
