#!/usr/bin/env bash
# Removes ADB Link (menu entry, autostart, program files). Your settings in ~/.config/adblink are kept
# unless you pass --purge.
set -u
DEST="${ADBLINK_DIR:-$HOME/.local/share/adblink}"
BIN="$HOME/.local/bin/adblink"
[ -x "$BIN" ] && "$BIN" uninstall || true
rm -f "$BIN"
rm -rf "$DEST"
[ "${1:-}" = "--purge" ] && rm -rf "$HOME/.config/adblink" "$HOME/.cache/adblink"
echo "ADB Link removed."
