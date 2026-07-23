# Start here

Your bookkeeping agent. Setup is about 20 minutes, one time. No coding. You can't break anything, and nothing ever goes into QuickBooks unless you approve it.

## 1. Your ledger (5 min)
1. Go to **drive.google.com** and sign in.
2. Open the **ledger** folder, drag the spreadsheet into Google Drive, then right-click it and **Open with Google Sheets**.
3. On the **Vendor Map** tab, type your regular vendors and the category each one belongs to. (Copy the example rows.) This is what makes it auto-code every invoice from a vendor to the same category.

## 2. Connect QuickBooks (10 min, one time)
1. Go to **developer.intuit.com**, sign in with your QuickBooks login.
2. **Create an app**, pick **QuickBooks Online Accounting**.
3. Open **Keys & credentials**. Copy the **Client ID** and **Client Secret**.
4. On that same page, under **Redirect URIs**, add exactly this and Save: `http://localhost:8000/callback`
5. In the **quickbooks-mcp** folder, double-click **install.command**. Paste the two codes when asked, then click **Authorize** in your browser.
6. Restart Claude Desktop when it tells you to.

## 3. Turn it on (2 min)
1. Open **Claude Desktop**, make a new **Project**.
2. Open **AGENT.md**, copy everything, paste it into the Project's instructions.
3. Connect your **Google Sheet** to the Project.

## Done. Every day after that:
**Drag** a bank statement, invoice, or photo of a check into the chat.
It fills your ledger. You glance at it, set the good rows to **Approved**, and say **"post the approved ones."**
It enters them into QuickBooks. That's it.

*Stuck on anything? Take a screenshot and send it. First-time setups sometimes need one small tweak.*
