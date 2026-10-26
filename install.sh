#!/usr/bin/env bash
# ADB Link installer - one command, any Linux distro (apt / dnf / pacman / zypper).
#
#   curl -fsSL https://raw.githubusercontent.com/alienshtain/adb-link/main/install.sh | bash
#
# Options (put them after "bash -s --"):  --autostart   start hidden at login
#                                         --phone       also install the phone app on the USB-connected phone
#                                         --no-deps     do not install helper programs
set -euo pipefail

REPO="${ADBLINK_REPO:-alienshtain/adb-link}"
BRANCH="${ADBLINK_BRANCH:-main}"
DEST="${ADBLINK_DIR:-$HOME/.local/share/adblink}"
BIN="$HOME/.local/bin"
AUTOSTART=0; PHONE=0; DEPS=1
for a in "$@"; do
  case "$a" in
    --autostart) AUTOSTART=1 ;;
    --phone) PHONE=1 ;;
    --no-deps) DEPS=0 ;;
  esac
done

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] && [ -z "${ADBLINK_ALLOW_ROOT:-}" ] && die "Run this as your normal user (not root / sudo). It asks for the password only when needed."
[ "$(uname -s)" = Linux ] || die "ADB Link runs on Linux."

SUDO=""; [ "$(id -u)" != 0 ] && command -v sudo >/dev/null && SUDO="sudo"
pm_install() {
  if   command -v apt-get >/dev/null; then $SUDO apt-get update -qq || true; $SUDO apt-get install -y "$@"
  elif command -v dnf     >/dev/null; then $SUDO dnf install -y "$@"
  elif command -v pacman  >/dev/null; then $SUDO pacman -S --needed --noconfirm "$@"
  elif command -v zypper  >/dev/null; then $SUDO zypper --non-interactive install "$@"
  else die "No supported package manager found (apt, dnf, pacman, zypper)."; fi
}

# 1. what is needed just to get started
need=()
command -v python3 >/dev/null || need+=(python3)
command -v tar     >/dev/null || need+=(tar)
if ! command -v curl >/dev/null && ! command -v wget >/dev/null; then need+=(curl); fi
if [ "${#need[@]}" -gt 0 ]; then say "Installing: ${need[*]}"; pm_install "${need[@]}"; fi

# 2. get the code (from a checkout next to this script, else from GitHub)
src=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/laptop/adblink/__init__.py" ]; then
  src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  say "Installing from $src"
else
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  url="https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz"
  say "Downloading $url"
  if command -v curl >/dev/null; then curl -fsSL "$url" -o "$tmp/a.tgz"; else wget -qO "$tmp/a.tgz" "$url"; fi
  tar -xzf "$tmp/a.tgz" -C "$tmp"
  src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -n1)"
  [ -f "$src/laptop/adblink/__init__.py" ] || die "The download does not look like ADB Link."
fi

if [ "$src" != "$DEST" ]; then
  rm -rf "$DEST"; mkdir -p "$DEST"
  cp -r "$src/laptop" "$src/assets" "$DEST/"
  [ -d "$src/phone" ] && cp -r "$src/phone" "$DEST/"
  cp "$src/README.md" "$src/uninstall.sh" "$DEST/" 2>/dev/null || true
fi

# 3. the "adblink" command
mkdir -p "$BIN"
cat > "$BIN/adblink" <<WRAP
#!/usr/bin/env bash
export PYTHONPATH="$DEST/laptop\${PYTHONPATH:+:\$PYTHONPATH}"
exec /usr/bin/env python3 -m adblink "\$@"
WRAP
chmod +x "$BIN/adblink"
case ":$PATH:" in *":$BIN:"*) ;; *) say "Note: add $BIN to your PATH (log out and in again on most systems)."; export PATH="$BIN:$PATH" ;; esac

# 4. helper programs (adb, GTK 4, libadwaita, scrcpy, brightnessctl, playerctl ...)
if [ "$DEPS" = 1 ]; then
  say "Installing the programs ADB Link needs (asks for your password once)"
  "$BIN/adblink" install-deps || say "Some optional tools could not be installed - run: adblink doctor"
fi

# 5. app menu + icon
say "Adding ADB Link to the app menu"
if [ "$AUTOSTART" = 1 ]; then "$BIN/adblink" install --autostart; else "$BIN/adblink" install; fi

# 6. optional: phone app
if [ "$PHONE" = 1 ]; then
  say "Installing the phone app (phone needs USB debugging on)"
  "$BIN/adblink" install-phone || say "Skipped. Later: adblink install-phone"
fi

echo
say "Done.  Open \"ADB Link\" from the app menu, or run:  adblink"
echo "   Phone app:  adblink install-phone     (or download the APK from https://github.com/$REPO/releases)"
echo "   Problems?   adblink doctor"
