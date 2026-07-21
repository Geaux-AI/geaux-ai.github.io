#!/usr/bin/env python3
"""Interactive OAuth 2.0 helper that mints a QuickBooks Online refresh token.

Run this ONCE to authorize the MCP server against your QuickBooks company. It:

  1. Reads QBO_CLIENT_ID / QBO_CLIENT_SECRET / QBO_ENVIRONMENT from `.env`
     (prompting for anything missing, with a hint on where to find it).
  2. Starts a tiny local web server on http://localhost:8000/callback.
  3. Opens your browser to Intuit's sign-in / consent page.
  4. Catches Intuit's redirect, exchanges the one-time code for tokens, and
     reads the refresh_token + realmId (your Company ID) from the response.
  5. Writes QBO_REFRESH_TOKEN and QBO_REALM_ID back into `.env` for you, so you
     never have to copy a token by hand.

No tokens are ever printed to the screen. Only stdlib + httpx (already a
dependency of the server) are used.

Endpoints/scope match server.py and .env.example exactly:
  * Authorization: https://appcenter.intuit.com/connect/oauth2   (Intuit's
    canonical OAuth2 authorize URL)
  * Token exchange: https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer
    (identical to TOKEN_URL in server.py)
  * Scope: com.intuit.quickbooks.accounting
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

# --- Constants (kept identical to server.py / .env.example) ------------------

# Intuit's canonical OAuth2 authorization endpoint.
AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
# Token endpoint - byte-for-byte the same as TOKEN_URL in server.py.
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
# The accounting scope the server needs.
SCOPE = "com.intuit.quickbooks.accounting"

# Fixed local redirect. This EXACT URI must also be listed under your app's
# "Redirect URIs" in the Intuit developer portal.
REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8000
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
ENV_EXAMPLE_PATH = os.path.join(HERE, ".env.example")

HTTP_TIMEOUT = 30.0


# --- Tiny .env reader / writer (no python-dotenv dependency) ------------------

def read_env_file(path: str) -> "dict[str, str]":
    """Parse a simple KEY=VALUE .env file into a dict (ignores comments/blanks)."""
    values: "dict[str, str]" = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip()
    return values


def upsert_env_values(path: str, updates: "dict[str, str]") -> None:
    """Insert or update KEY=VALUE lines in `path`, preserving everything else.

    Existing keys are updated in place (comments and ordering are kept); new keys
    are appended at the end. Creates the file if it does not exist.
    """
    remaining = dict(updates)
    lines: "list[str]" = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

    out: "list[str]" = []
    for line in lines:
        stripped = line.strip()
        replaced = False
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}\n")
                replaced = True
        if not replaced:
            out.append(line if line.endswith("\n") else line + "\n")

    if remaining:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        for key, value in remaining.items():
            out.append(f"{key}={value}\n")

    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.writelines(out)
    os.replace(tmp, path)


# --- Credential gathering -----------------------------------------------------

PLACEHOLDERS = {
    "your_client_id_here",
    "your_client_secret_here",
    "your_refresh_token_here",
    "your_realm_id_here",
    "",
}


def _clean(value: str) -> str:
    return (value or "").strip()


def _is_placeholder(value: str) -> bool:
    return _clean(value) in PLACEHOLDERS


def gather_credentials() -> "tuple[str, str, str]":
    """Return (client_id, client_secret, environment), prompting for any missing."""
    env = read_env_file(ENV_PATH)

    client_id = _clean(env.get("QBO_CLIENT_ID", ""))
    client_secret = _clean(env.get("QBO_CLIENT_SECRET", ""))
    environment = _clean(env.get("QBO_ENVIRONMENT", "")) or "sandbox"

    to_write: "dict[str, str]" = {}

    if _is_placeholder(client_id):
        print(
            "\nI need your QuickBooks app's Client ID.\n"
            "  Find it at https://developer.intuit.com -> your app -> "
            "'Keys & credentials'.\n"
            "  (Use the Development keys for sandbox, Production keys for real books.)"
        )
        client_id = _clean(input("  Paste your Client ID: "))
        if not client_id:
            fail("No Client ID entered. Re-run when you have it in hand.")
        to_write["QBO_CLIENT_ID"] = client_id

    if _is_placeholder(client_secret):
        print(
            "\nNow your Client Secret (same 'Keys & credentials' page, right "
            "under the Client ID)."
        )
        client_secret = _clean(input("  Paste your Client Secret: "))
        if not client_secret:
            fail("No Client Secret entered. Re-run when you have it in hand.")
        to_write["QBO_CLIENT_SECRET"] = client_secret

    if environment not in ("sandbox", "production"):
        environment = "sandbox"
    to_write.setdefault("QBO_ENVIRONMENT", environment)

    # Persist anything the user typed so a re-run won't ask again.
    if to_write:
        if not os.path.exists(ENV_PATH) and os.path.exists(ENV_EXAMPLE_PATH):
            # Seed from the example so the helpful comments are preserved.
            with open(ENV_EXAMPLE_PATH, "r", encoding="utf-8") as src, \
                    open(ENV_PATH, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        upsert_env_values(ENV_PATH, to_write)

    return client_id, client_secret, environment


# --- Local callback server ----------------------------------------------------

class _CallbackResult:
    """Shared mailbox the request handler drops the OAuth redirect params into."""

    def __init__(self) -> None:
        self.code: "str | None" = None
        self.realm_id: "str | None" = None
        self.state: "str | None" = None
        self.error: "str | None" = None
        self.done = threading.Event()


def _make_handler(expected_state: str, result: _CallbackResult):
    class Handler(BaseHTTPRequestHandler):
        # Silence the default stderr request logging.
        def log_message(self, *args, **kwargs):  # noqa: D401, ANN001
            return

        def _respond(self, title: str, body: str) -> None:
            html = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<title>QuickBooks setup</title></head>"
                "<body style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
                "max-width:520px;margin:80px auto;text-align:center;color:#1a1a1a'>"
                f"<h2>{title}</h2><p style='font-size:16px;line-height:1.5'>{body}</p>"
                "</body></html>"
            )
            encoded = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != REDIRECT_PATH:
                self.send_response(404)
                self.end_headers()
                return
            params = urllib.parse.parse_qs(parsed.query)
            result.state = (params.get("state") or [None])[0]
            result.error = (params.get("error") or [None])[0]
            result.code = (params.get("code") or [None])[0]
            result.realm_id = (params.get("realmId") or [None])[0]

            if result.error:
                self._respond(
                    "Authorization was cancelled",
                    "You (or QuickBooks) declined the connection. You can close "
                    "this tab and re-run the installer to try again.",
                )
            elif result.state != expected_state:
                result.error = "state_mismatch"
                self._respond(
                    "Security check failed",
                    "The response did not match this session. Please close this "
                    "tab and re-run the installer.",
                )
            elif not result.code:
                result.error = "no_code"
                self._respond(
                    "Something went wrong",
                    "QuickBooks did not return an authorization code. Close this "
                    "tab and re-run the installer.",
                )
            else:
                self._respond(
                    "You're connected!",
                    "QuickBooks authorization succeeded. You can close this tab "
                    "and return to the installer window.",
                )
            result.done.set()

    return Handler


# --- Token exchange -----------------------------------------------------------

def exchange_code_for_tokens(
    client_id: str, client_secret: str, code: str
) -> "dict[str, str]":
    """Swap the one-time authorization code for tokens at Intuit's token endpoint."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        resp = httpx.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        fail(f"Could not reach Intuit's token endpoint: {exc}\n"
             "Check your internet connection and try again.")

    if resp.status_code != 200:
        detail = resp.text[:300]
        hint = ""
        if resp.status_code in (400, 401):
            hint = (
                "\nThis usually means the Client ID/Secret are wrong, or the "
                f"Redirect URI\n  {REDIRECT_URI}\nis not listed under your app's "
                "'Redirect URIs' in the Intuit developer portal. Add it there and "
                "re-run."
            )
        fail(f"Intuit rejected the token request (HTTP {resp.status_code}): "
             f"{detail}{hint}")

    return resp.json()


# --- Orchestration ------------------------------------------------------------

def fail(message: str) -> "None":
    print(f"\n[X] {message}\n", file=sys.stderr)
    raise SystemExit(1)


def build_authorization_url(client_id: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "scope": SCOPE,
            "redirect_uri": REDIRECT_URI,
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


def start_callback_server(handler_factory) -> HTTPServer:
    try:
        return HTTPServer((REDIRECT_HOST, REDIRECT_PORT), handler_factory)
    except OSError as exc:
        fail(
            f"Could not open the local sign-in port {REDIRECT_PORT} "
            f"({exc.strerror or exc}).\n"
            "Another program (or a previous run) is probably using it. Close "
            "other apps\nor wait a few seconds, then run the installer again."
        )


def main() -> int:
    print("=" * 64)
    print("  QuickBooks Online - one-time connection setup")
    print("=" * 64)

    client_id, client_secret, environment = gather_credentials()
    print(f"\nUsing the '{environment}' environment.")

    state = secrets.token_urlsafe(24)
    result = _CallbackResult()
    server = start_callback_server(_make_handler(state, result))

    auth_url = build_authorization_url(client_id, state)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print(
        "\nOpening your web browser so you can sign in to QuickBooks and click "
        "'Connect'.\nIf it doesn't open automatically, paste this link into your "
        "browser:\n\n  " + auth_url + "\n"
    )
    try:
        webbrowser.open(auth_url)
    except Exception:  # noqa: BLE001 - headless boxes just use the printed link
        pass

    print("Waiting for you to approve the connection in the browser...")
    # Wait up to 5 minutes for the human to click through.
    if not result.done.wait(timeout=300):
        server.shutdown()
        fail("Timed out waiting for QuickBooks authorization (5 minutes). "
             "Re-run the installer to try again.")

    server.shutdown()

    if result.error == "access_denied":
        fail("You declined the QuickBooks connection. Re-run the installer when "
             "you're ready to approve it.")
    if result.error:
        fail(f"Authorization did not complete ({result.error}). Re-run the "
             "installer to try again.")
    if not result.code or not result.realm_id:
        fail("QuickBooks did not return the expected authorization details. "
             "Re-run the installer to try again.")

    print("Got it. Exchanging the code for your secure tokens...")
    tokens = exchange_code_for_tokens(client_id, client_secret, result.code)

    refresh_token = _clean(tokens.get("refresh_token", ""))
    if not refresh_token:
        fail("Intuit's response did not include a refresh token. Re-run the "
             "installer to try again.")

    upsert_env_values(
        ENV_PATH,
        {
            "QBO_REFRESH_TOKEN": refresh_token,
            "QBO_REALM_ID": result.realm_id,
            "QBO_ENVIRONMENT": environment,
        },
    )

    print("\n" + "=" * 64)
    print("  Success! QuickBooks is connected.")
    print("=" * 64)
    print(
        "\nYour refresh token and Company ID were saved securely to .env.\n"
        "You did not have to copy anything by hand - you're all set.\n"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled. Re-run the installer whenever you're ready.")
        raise SystemExit(1)
