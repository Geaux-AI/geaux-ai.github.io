#!/usr/bin/env bash
# Double-clickable macOS launcher. Finder runs this in Terminal; it just hands
# off to install.sh living next to it, so there is a single source of truth.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd)"
exec bash "$DIR/install.sh"
