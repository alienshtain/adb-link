"""The built-in adb commands and the placeholder helpers."""
from __future__ import annotations

import re
import shlex


CATEGORIES = ["Connection", "Apps", "Files", "Screen", "Control", "Info"]
# The Commands page has two parts: setting up adb / showing devices, and everything done on the phone.
SETUP_CATEGORIES = {"Connection"}


def section_of(command):
    return 0 if command.get("category") in SETUP_CATEGORIES else 1


# defaults that were removed (the Apps page does these) or rewritten in newer versions
REMOVED_DEFAULTS = {"uninstall", "remove-system", "restore"}
REWRITTEN_DEFAULTS = {"pull", "screenshot", "record", "type"}
SORT_MODES = ["Category", "Name A-Z", "Name Z-A", "Favorites first"]

# Icons offered in the icon picker (only the ones your theme has are shown).
# Any emoji or any other icon name can be typed instead.
ICON_CHOICES = [
    "phone-symbolic", "utilities-terminal-symbolic", "computer-symbolic",
    "network-wireless-symbolic", "network-transmit-receive-symbolic",
    "network-offline-symbolic", "bluetooth-symbolic", "airplane-mode-symbolic",
    "folder-symbolic", "folder-download-symbolic", "document-send-symbolic",
    "document-save-symbolic", "document-open-symbolic", "text-x-generic-symbolic",
    "package-x-generic-symbolic", "drive-harddisk-symbolic",
    "view-refresh-symbolic", "system-shutdown-symbolic", "system-reboot-symbolic",
    "system-lock-screen-symbolic", "edit-delete-symbolic", "user-trash-symbolic",
    "list-add-symbolic", "edit-find-symbolic", "edit-undo-symbolic",
    "media-record-symbolic", "media-playback-start-symbolic",
    "media-playback-stop-symbolic", "camera-photo-symbolic",
    "audio-volume-high-symbolic", "display-brightness-symbolic",
    "input-keyboard-symbolic", "input-mouse-symbolic", "go-home-symbolic",
    "go-previous-symbolic", "go-next-symbolic", "view-list-symbolic",
    "view-grid-symbolic", "view-fullscreen-symbolic", "process-stop-symbolic",
    "window-close-symbolic", "emblem-system-symbolic", "preferences-system-symbolic",
    "applications-system-symbolic", "dialog-information-symbolic",
    "dialog-warning-symbolic", "emblem-ok-symbolic", "starred-symbolic",
    "weather-clear-symbolic", "find-location-symbolic",
]

# placeholder -> (label, default value, kind)  kind: text | file | folder
FIELDS = {
    "package": ("Package name", "", "text"),
    "keyword": ("Search keyword", "", "text"),
    "ip_port": ("Phone IP:port (e.g. 100.x.x.x:5555)", "", "text"),
    "apk": ("APK file", "", "file"),
    "local_file": ("File to send to the phone", "", "file"),
    "remote_path": ("Path on the phone", "/sdcard/DCIM/Camera", "text"),
    "remote_dir": ("Folder on the phone", "/sdcard/", "text"),
    "seconds": ("Seconds (1-180)", "30", "text"),
    "x": ("X position", "500", "text"),
    "y": ("Y position", "1000", "text"),
    "text": ("Text to type", "", "text"),
    "url": ("Link to open", "https://", "text"),
}
NUMERIC = {"seconds", "x", "y"}
PLACEHOLDER = re.compile(r"\{(\w+)\}")
SEGMENT_SPLIT = re.compile(r"\|\||&&|[|;]")
ON_PHONE = re.compile(r"\badb\s+(?:-\S+\s+)*(?:shell|exec-out)\b")


def D(cid, name, category, icon, description, command, confirm=False):
    return {"id": cid, "name": name, "category": category, "icon": icon,
            "description": description, "cmd": command, "confirm": confirm}


DEFAULT_COMMANDS = [
    D("devices", "List devices", "Connection", "phone-symbolic",
      "Shows the phones connected by USB or network.", "adb devices"),
    D("restart-server", "Restart adb server", "Connection", "view-refresh-symbolic",
      "Fixes adb when it stops seeing the phone.",
      "adb kill-server && adb start-server && adb devices"),
    D("tcpip", "Enable network mode", "Connection", "network-wireless-symbolic",
      "Phone must be on USB. Makes it listen on port 5555 for Wi-Fi or Tailscale.",
      "adb tcpip 5555"),
    D("connect", "Connect over network", "Connection", "network-transmit-receive-symbolic",
      "Connects to the phone by IP address (Wi-Fi or Tailscale).", "adb connect {ip_port}"),
    D("disconnect", "Disconnect network", "Connection", "network-offline-symbolic",
      "Drops all network connections to phones.", "adb disconnect"),
    D("usb", "Back to USB mode", "Connection", "go-previous-symbolic",
      "Switches adb on the phone back to USB.", "adb usb"),
    D("list-all", "List all packages", "Apps", "view-list-symbolic",
      "Every package installed on the phone.", "adb shell pm list packages"),
    D("list-user", "List installed apps", "Apps", "view-list-symbolic",
      "Only apps you installed (no system apps).", "adb shell pm list packages -3"),
    D("list-system", "List system apps", "Apps", "view-list-symbolic",
      "Only pre-installed system apps.", "adb shell pm list packages -s"),
    D("list-disabled", "List disabled apps", "Apps", "view-list-symbolic",
      "Apps that are currently disabled.", "adb shell pm list packages -d"),
    D("find-package", "Find package name", "Apps", "edit-find-symbolic",
      "Searches package names by keyword, e.g. weather or youtube.",
      "adb shell pm list packages | grep -i {keyword}"),
    D("install", "Install APK", "Apps", "document-save-symbolic",
      "Installs an APK file from your computer (keeps data if already installed).",
      "adb install -r {apk}"),
    D("disable", "Disable app", "Apps", "process-stop-symbolic",
      "Hides the app and stops it running. Can be enabled again.",
      "adb shell pm disable-user --user 0 {package}"),
    D("enable", "Enable app", "Apps", "media-playback-start-symbolic",
      "Turns a disabled app back on.", "adb shell pm enable {package}"),
    D("clear", "Clear app data", "Apps", "edit-clear-all-symbolic",
      "Deletes the app's data and cache (like a fresh install).",
      "adb shell pm clear {package}", True),
    D("force-stop", "Force stop app", "Apps", "window-close-symbolic",
      "Stops the app immediately.", "adb shell am force-stop {package}"),
    D("push", "Send file to phone", "Files", "document-send-symbolic",
      "Copies a file from your computer to the phone's Download folder.",
      "adb push {local_file} /sdcard/Download/"),
    D("pull", "Get file from phone", "Files", "folder-download-symbolic",
      "Copies a file or folder from the phone to Documents/ADB Link/Phone files on your computer.",
      'd="${ADBLINK_DIR:-$HOME/Documents/ADB Link}/Phone files"; mkdir -p "$d" && adb pull {remote_path} "$d/" '
      '&& echo "Saved in $d"'),
    D("ls", "List phone folder", "Files", "folder-symbolic",
      "Shows the files inside a folder on the phone.", "adb shell ls {remote_dir}"),
    D("screenshot", "Take screenshot", "Screen", "camera-photo-symbolic",
      "Saves a screenshot of the phone in Documents/ADB Link/Screenshots.",
      'd="${ADBLINK_DIR:-$HOME/Documents/ADB Link}/Screenshots"; mkdir -p "$d" && '
      'adb exec-out screencap -p > "$d/adb-screenshot-$(date +%Y%m%d-%H%M%S).png" && echo "Saved in $d"'),
    D("record", "Record screen", "Screen", "media-record-symbolic",
      "Records the screen for the given seconds (max 180), then saves the video in Documents/ADB Link/Recordings.",
      'd="${ADBLINK_DIR:-$HOME/Documents/ADB Link}/Recordings"; mkdir -p "$d" && '
      "adb shell screenrecord --time-limit {seconds} /sdcard/adb-rec.mp4 "
      '&& adb pull /sdcard/adb-rec.mp4 "$d/adb-rec-$(date +%Y%m%d-%H%M%S).mp4" '
      '&& adb shell rm /sdcard/adb-rec.mp4 && echo "Saved in $d"'),
    D("power", "Power button", "Control", "system-shutdown-symbolic",
      "Wakes or locks the screen.", "adb shell input keyevent 26"),
    D("home", "Home button", "Control", "go-home-symbolic",
      "Goes to the home screen.", "adb shell input keyevent 3"),
    D("back", "Back button", "Control", "go-previous-symbolic",
      "Presses Back.", "adb shell input keyevent 4"),
    D("recents", "Recent apps", "Control", "view-grid-symbolic",
      "Opens the recent apps screen.", "adb shell input keyevent 187"),
    D("tap", "Tap screen", "Control", "input-mouse-symbolic",
      "Taps at the given screen coordinates.", "adb shell input tap {x} {y}"),
    D("type", "Type text", "Control", "input-keyboard-symbolic",
      "Types text into the focused field on the phone. Arabic and other languages work too.",
      "adblink type {text}"),
    D("open-url", "Open link", "Control", "go-next-symbolic",
      "Opens a web link in the phone's default browser.",
      "adb shell am start -a android.intent.action.VIEW -d {url}"),
    D("reboot", "Reboot phone", "Control", "system-reboot-symbolic",
      "Restarts the phone.", "adb reboot", True),
    D("model", "Phone model", "Info", "phone-symbolic",
      "Shows the phone's model name.", "adb shell getprop ro.product.model"),
    D("android", "Android version", "Info", "dialog-information-symbolic",
      "Shows the Android version number.", "adb shell getprop ro.build.version.release"),
    D("battery", "Battery status", "Info", "battery-symbolic",
      "Battery level, charging state, temperature.", "adb shell dumpsys battery"),
    D("storage", "Storage usage", "Info", "drive-harddisk-symbolic",
      "Shows used and free space.", "adb shell df -h"),
    D("wifi-ip", "Phone Wi-Fi IP", "Info", "network-wireless-symbolic",
      "Shows the phone's Wi-Fi IP address (useful for network connect).",
      "adb shell ip addr show wlan0"),
    D("logcat", "Recent system log", "Info", "text-x-generic-symbolic",
      "Last 200 lines of the phone's system log.", "adb logcat -d | tail -n 200"),
]


# ------------------------------------------------------------ small helpers

def fields_of(command_text):
    """Placeholders used by a command, in order, without duplicates."""
    return list(dict.fromkeys(PLACEHOLDER.findall(command_text)))


def field_info(key):
    """(label, default, kind) for a variable; unknown names get sensible defaults."""
    if key in FIELDS:
        return FIELDS[key]
    kind = "file" if key.endswith(("file", "apk")) else "folder" if key.endswith("folder") else "text"
    return (key.replace("_", " ").capitalize(), "", kind)


def build(command_text, values):
    """Fill {variables} with shell-safe values.

    Values used after `adb shell` / `adb exec-out` are quoted twice, because
    both your shell and the phone's shell read them.
    """
    bounds, pos = [], 0
    for m in SEGMENT_SPLIT.finditer(command_text):
        bounds.append((pos, m.start()))
        pos = m.end()
    bounds.append((pos, len(command_text)))

    def sub(m):
        quoted = shlex.quote(values[m.group(1)])
        segment = next((command_text[a:b] for a, b in bounds if a <= m.start() < b), "")
        if ON_PHONE.search(segment):
            quoted = shlex.quote(quoted)
        return quoted

    return PLACEHOLDER.sub(sub, command_text)


def category_rank(category):
    return (CATEGORIES.index(category), "") if category in CATEGORIES else (len(CATEGORIES), category.lower())
