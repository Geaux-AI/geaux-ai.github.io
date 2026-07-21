#!/usr/bin/env bash
# =============================================================================
# QuickBooks Online MCP server - one-step installer for non-technical users.
#
# Safe to run more than once. It will:
#   1. Check that Python 3 is installed (and tell you how to get it if not).
#   2. Build an isolated Python environment in this folder and install the
#      server's dependencies.
#   3. Create your .env file and collect your QuickBooks Client ID / Secret.
#   4. Open your browser to connect QuickBooks (mints the refresh token for you).
#   5. Add this server to Claude Desktop automatically (with a backup).
#   6. Tell you to restart Claude Desktop.
#
# Works on macOS and Linux. Windows users: see the README "Windows" note.
# =============================================================================

set -u

# --- Resolve this script's own folder (so double-clicking works anywhere) ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR" || exit 1

VENV_DIR="$SCRIPT_DIR/.venv"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
SERVER_PY="$SCRIPT_DIR/server.py"
GET_TOKEN_PY="$SCRIPT_DIR/get_token.py"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
TOKEN_CACHE="$SCRIPT_DIR/token-cache.json"

say()  { printf "%s\n" "$*"; }
step() { printf "\n==> %s\n" "$*"; }
ok()   { printf "    [ok] %s\n" "$*"; }
warn() { printf "    [!] %s\n" "$*"; }
die()  { printf "\n[X] %s\n\n" "$*" >&2; hold_open; exit 1; }

# Keep a double-clicked Terminal window open on exit so the user can read output.
hold_open() {
  if [ -t 0 ] && [ "${QBO_INSTALLER_HOLD:-1}" = "1" ]; then
    printf "\nPress Return to close this window."
    read -r _ || true
  fi
}

# --- OS detection -------------------------------------------------------------
OS="$(uname -s 2>/dev/null || echo unknown)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)      PLATFORM="other" ;;
esac

say "=============================================================="
say "  QuickBooks Online MCP - installer"
say "=============================================================="

# --- 1. Python 3 --------------------------------------------------------------
step "Checking for Python 3"
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)' >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  if [ "$PLATFORM" = "macos" ]; then
    die "Python 3.9+ is not installed.
    The easiest fix on a Mac:
      1. Open the App Store (or https://www.python.org/downloads/macos/).
      2. Install the latest Python 3.
      3. Double-click this installer again."
  elif [ "$PLATFORM" = "linux" ]; then
    die "Python 3.9+ is not installed.
    Install it, then run this again. For example:
      Debian/Ubuntu:  sudo apt-get install -y python3 python3-venv
      Fedora:         sudo dnf install -y python3"
  else
    die "Python 3.9+ is required. Please install it and run this again:
      https://www.python.org/downloads/"
  fi
fi
ok "Found $("$PY" --version 2>&1)"

# --- 2. Virtual environment + dependencies -----------------------------------
step "Setting up the Python environment (this can take a minute)"
if [ ! -d "$VENV_DIR" ]; then
  "$PY" -m venv "$VENV_DIR" || die "Could not create the Python environment.
    On Debian/Ubuntu you may need:  sudo apt-get install -y python3-venv"
  ok "Created isolated environment in .venv"
else
  ok "Reusing existing .venv"
fi

VENV_PY="$VENV_DIR/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$VENV_DIR/bin/python3"
[ -x "$VENV_PY" ] || die "The Python environment looks broken. Delete the .venv folder and re-run."

"$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1 || warn "Could not upgrade pip; continuing."
say "    Installing dependencies from requirements.txt ..."
"$VENV_PY" -m pip install -r "$REQUIREMENTS" >/dev/null 2>&1 \
  || die "Failed to install dependencies. Check your internet connection and re-run."
ok "Dependencies installed"

# --- 3. .env + QuickBooks app credentials ------------------------------------
step "Preparing your configuration file (.env)"
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    ok "Created .env from .env.example"
  else
    : > "$ENV_FILE"
    ok "Created a blank .env"
  fi
else
  ok "Found existing .env"
fi

# Read a value out of .env (first match), trimming whitespace.
read_env() {
  # shellcheck disable=SC2016
  "$VENV_PY" - "$ENV_FILE" "$1" <<'PYEOF'
import sys
path, key = sys.argv[1], sys.argv[2]
val = ""
try:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            if k.strip() == key:
                val = v.strip()
except OSError:
    pass
print(val)
PYEOF
}

CID="$(read_env QBO_CLIENT_ID)"
CSECRET="$(read_env QBO_CLIENT_SECRET)"
case "$CID" in ""|your_client_id_here) NEED_CID=1 ;; *) NEED_CID=0 ;; esac
case "$CSECRET" in ""|your_client_secret_here) NEED_CSECRET=1 ;; *) NEED_CSECRET=0 ;; esac

if [ "$NEED_CID" = "1" ] || [ "$NEED_CSECRET" = "1" ]; then
  say ""
  say "    I need your QuickBooks app's keys. Get them here (about 4 clicks):"
  say "      1. Go to https://developer.intuit.com and sign in."
  say "      2. Open your app under 'My Apps' (or create one with the"
  say "         'QuickBooks Online Accounting API' scope)."
  say "      3. Open 'Keys & credentials'."
  say "      4. Copy the Client ID and Client Secret."
  say "    While you're there, add this Redirect URI to the app:"
  say "         http://localhost:8000/callback"
  say ""
fi

# get_token.py handles the prompting/persistence, but prompt here too so the
# rest of the run has values even if the user cleared them. Empty answers are
# fine - get_token.py will re-prompt.
if [ "$NEED_CID" = "1" ]; then
  printf "    Paste your Client ID (or leave blank to enter it in the next step): "
  read -r ANSWER || true
  [ -n "${ANSWER:-}" ] && CID="$ANSWER"
fi
if [ "$NEED_CSECRET" = "1" ]; then
  printf "    Paste your Client Secret (or leave blank to enter it in the next step): "
  read -r ANSWER || true
  [ -n "${ANSWER:-}" ] && CSECRET="$ANSWER"
fi

# Persist anything we collected (preserving the rest of .env).
"$VENV_PY" - "$ENV_FILE" "$CID" "$CSECRET" <<'PYEOF'
import os, sys
path, cid, csecret = sys.argv[1], sys.argv[2], sys.argv[3]
updates = {}
if cid:
    updates["QBO_CLIENT_ID"] = cid
if csecret:
    updates["QBO_CLIENT_SECRET"] = csecret
if not updates:
    raise SystemExit(0)
lines = []
if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
out, remaining = [], dict(updates)
for line in lines:
    s = line.strip()
    done = False
    if s and not s.startswith("#") and "=" in s:
        k = s.split("=", 1)[0].strip()
        if k in remaining:
            out.append(f"{k}={remaining.pop(k)}\n"); done = True
    if not done:
        out.append(line if line.endswith("\n") else line + "\n")
for k, v in remaining.items():
    out.append(f"{k}={v}\n")
with open(path, "w", encoding="utf-8") as fh:
    fh.writelines(out)
PYEOF
ok "Configuration saved"

# --- 4. OAuth (browser) -------------------------------------------------------
step "Connecting to QuickBooks (a browser window will open)"
if "$VENV_PY" - "$ENV_FILE" <<'PYEOF'
import sys
path = sys.argv[1]
rt = ""
try:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("QBO_REFRESH_TOKEN="):
                rt = s.split("=", 1)[1].strip()
except OSError:
    pass
raise SystemExit(0 if rt and rt != "your_refresh_token_here" else 1)
PYEOF
then
  say "    You already have a saved QuickBooks connection."
  printf "    Reconnect / refresh it now? [y/N]: "
  read -r RECONNECT || true
  case "${RECONNECT:-}" in
    y|Y|yes|YES) RUN_OAUTH=1 ;;
    *) RUN_OAUTH=0; ok "Keeping your existing connection" ;;
  esac
else
  RUN_OAUTH=1
fi

if [ "${RUN_OAUTH:-1}" = "1" ]; then
  "$VENV_PY" "$GET_TOKEN_PY" || die "QuickBooks connection did not complete. You can re-run this installer to try again."
fi

# --- 5. Register with Claude Desktop -----------------------------------------
step "Adding this server to Claude Desktop"
if [ "$PLATFORM" = "macos" ]; then
  CLAUDE_DIR="$HOME/Library/Application Support/Claude"
elif [ "$PLATFORM" = "linux" ]; then
  CLAUDE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Claude"
else
  CLAUDE_DIR=""
fi
CLAUDE_CFG="$CLAUDE_DIR/claude_desktop_config.json"

MERGE_STATUS=0
if [ -n "$CLAUDE_DIR" ]; then
  "$VENV_PY" - "$CLAUDE_CFG" "$VENV_PY" "$SERVER_PY" "$ENV_FILE" "$TOKEN_CACHE" <<'PYEOF'
import json, os, shutil, sys, time

cfg_path, venv_py, server_py, env_file, token_cache = sys.argv[1:6]

def read_env(path):
    vals = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                vals[k.strip()] = v.strip()
    except OSError:
        pass
    return vals

env = read_env(env_file)
server_env = {}
for key in ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REFRESH_TOKEN",
            "QBO_REALM_ID", "QBO_ENVIRONMENT", "QBO_MINOR_VERSION"):
    v = env.get(key, "")
    if v and not v.startswith("your_"):
        server_env[key] = v
server_env["QBO_TOKEN_CACHE_FILE"] = token_cache

entry = {"command": venv_py, "args": [server_py], "env": server_env}

os.makedirs(os.path.dirname(cfg_path), exist_ok=True)

config = {}
if os.path.exists(cfg_path):
    try:
        with open(cfg_path, encoding="utf-8") as fh:
            config = json.load(fh)
        if not isinstance(config, dict):
            config = {}
    except (OSError, json.JSONDecodeError):
        # Unreadable/corrupt config: don't clobber it, bail so we print manual steps.
        print("MANUAL")
        raise SystemExit(3)
    # Back up before we touch a real file.
    backup = f"{cfg_path}.backup-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        shutil.copy2(cfg_path, backup)
        print(f"BACKUP {backup}")
    except OSError:
        pass

servers = config.get("mcpServers")
if not isinstance(servers, dict):
    servers = {}
servers["quickbooks"] = entry
config["mcpServers"] = servers

try:
    tmp = f"{cfg_path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
    os.replace(tmp, cfg_path)
    print(f"WROTE {cfg_path}")
except OSError as exc:
    print(f"MANUAL {exc}")
    raise SystemExit(3)
PYEOF
  MERGE_STATUS=$?
else
  MERGE_STATUS=3
fi

if [ "$MERGE_STATUS" -ne 0 ]; then
  warn "I couldn't update Claude Desktop's config automatically."
  say ""
  say "    Open (or create) this file:"
  if [ -n "$CLAUDE_CFG" ]; then
    say "      $CLAUDE_CFG"
  else
    say "      macOS: ~/Library/Application Support/Claude/claude_desktop_config.json"
    say "      Linux: ~/.config/Claude/claude_desktop_config.json"
    say "      Windows: %APPDATA%\\Claude\\claude_desktop_config.json"
  fi
  say "    and add this inside \"mcpServers\" (create it if missing):"
  say ""
  say '      "quickbooks": {'
  say "        \"command\": \"$VENV_PY\","
  say "        \"args\": [\"$SERVER_PY\"],"
  say "        \"env\": { \"QBO_TOKEN_CACHE_FILE\": \"$TOKEN_CACHE\" }"
  say "      }"
  say ""
  say "    (Your QuickBooks keys are already saved in .env for the values above.)"
else
  ok "Claude Desktop configuration updated"
fi

# --- 6. Done ------------------------------------------------------------------
say ""
say "=============================================================="
say "  You're done!"
say "=============================================================="
say ""
say "  Last step: fully QUIT and REOPEN Claude Desktop."
say "  (On a Mac, use Cmd+Q to quit, then open it again - a window"
say "   close is not enough.)"
say ""
say "  After it restarts, ask Claude to post a test transaction and"
say "  the QuickBooks tools will be available."
say ""
hold_open
exit 0
