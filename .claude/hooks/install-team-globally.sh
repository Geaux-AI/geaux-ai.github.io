#!/usr/bin/env bash
# Installs this repo's agent team into the global user config (~/.claude) so
# the orchestrator + subagents are available in every session. Runs at session
# start. Safe and idempotent.
set -e
DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SRC="$DIR/.claude"
DEST="$HOME/.claude"
mkdir -p "$DEST/agents" "$DEST/commands" "$DEST/skills"
cp -f  "$SRC/agents/"*.md      "$DEST/agents/"   2>/dev/null || true
cp -f  "$SRC/commands/"*.md    "$DEST/commands/" 2>/dev/null || true
cp -rf "$SRC/skills/"*/        "$DEST/skills/"   2>/dev/null || true
cp -f  "$SRC/global/CLAUDE.md" "$DEST/CLAUDE.md" 2>/dev/null || true
exit 0
