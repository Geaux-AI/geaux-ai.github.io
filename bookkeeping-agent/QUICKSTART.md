# Quick Start — the 3 things to do

No coding. About 20 minutes, most of it one-time. If you can install an app and click "Authorize," you can do this.

---

## 1. Set up your ledger (5 min)

1. Open [Google Drive](https://drive.google.com) → **New → File upload** → choose `ledger/Bookkeeping-Ledger-Template.xlsx`.
2. Right-click the uploaded file → **Open with → Google Sheets**.
3. Go to the **Vendor Map** tab and type in your real vendors and which QuickBooks category each belongs to. (Replace the example rows.)

That's the only setup the ledger needs. The **Instructions** tab explains the colors.

---

## 2. Connect QuickBooks (10 min, one time)

You need two codes from Intuit first — this is the only slightly technical part, and it's just copy-paste:

1. Go to the [Intuit Developer portal](https://developer.intuit.com) → sign in with your QuickBooks login → **Create an app** → choose **QuickBooks Online Accounting**.
2. Open your app → **Keys & credentials**. You'll see a **Client ID** and **Client Secret**. Keep that tab open.
3. On that same page, find **Redirect URIs**, click **Add URI**, paste `http://localhost:8000/callback`, and **Save**. (This is the one thing the installer can't do for you — it lets your browser hand the connection back.)
4. In the `quickbooks-mcp` folder, **double-click `install.command`** (Mac) or run `./install.sh` (Mac/Linux).
   - It will ask you to paste the Client ID and Client Secret.
   - Then your browser opens — click **Authorize** / **Connect**.
   - It finishes the rest for you: installs everything, gets your secure token, and connects the agent to Claude Desktop.
5. **Restart Claude Desktop** when it says to.

Do this against the QuickBooks **Sandbox** first (a free test company) to watch it work with no risk, then switch to your real company by changing one setting the installer explains.

---

## 3. Turn on the agent (2 min)

1. Open **Claude Desktop** → create a new **Project**.
2. Open `agent/AGENT.md`, copy everything, and paste it into the Project's instructions.
3. Connect your **Google Sheet** to the Project (the Google Drive/Sheets connector).

Done. Now, to use it every day:

> **Drag a bank statement, invoice, or check photo into the chat.**
> The agent reads it, fills your ledger, and shows you what it found.
> You glance at it, set **Status = Approved** on the rows that look right, and tell the agent "post the approved ones."
> It enters them into QuickBooks and marks them Posted.

Once a week, open the **Reconciliation** tab and type in your bank and QuickBooks totals — it tells you in one cell whether everything matches.

---

### If you get stuck
- The installer prints plain-English messages if something's missing (like "install Python from python.org").
- Full detail is in `README.md` and `quickbooks-mcp/README.md`.
- Nothing ever posts to QuickBooks unless you mark it **Approved** — so you can experiment safely.
