"""Call, contact, SMS and quick-toggle helpers that talk to the phone."""
from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import urllib
from .adbutil import adb
from .apps_helpers import pretty_name


# ---------------------------------------------------------------- main window

# ---------------------------------------------------------------- phone helpers (calls, contacts, SMS, toggles)

CALL_SCRIPT = "dumpsys telephony.registry | grep -E 'mCallState|mCallIncomingNumber'"
CONTACTS_CMD = ("content query --uri content://com.android.contacts/data/phones "
                "--projection display_name:data1")
SIMS_CMD = ("content query --uri content://telephony/siminfo "
            "--projection _id:sim_id:display_name:carrier_name")
DEFAULT_SUB = 2147483647  # Android's "use the default SIM"


def digits(text):
    return re.sub(r"\D", "", text or "")


def same_number(a, b):
    a, b = digits(a), digits(b)
    if not a or not b:
        return False
    return a == b or (len(a) >= 7 and len(b) >= 7 and a[-9:] == b[-9:])


def parse_call_state(text):
    """-> (state, number). state is 'idle', 'ringing' or 'offhook'."""
    states = [int(x) for x in re.findall(r"mCallState=(\d+)", text)]
    numbers = re.findall(r"mCallIncomingNumber=(\S*)", text)
    state = "ringing" if 1 in states else "offhook" if 2 in states else "idle"
    number = next((n for n in numbers if n and n.lower() != "null"), "")
    return state, number


def parse_contacts(text):
    """-> [(name, number)] sorted by name, without duplicates."""
    seen, out = set(), []
    for line in text.splitlines():
        m = re.match(r"Row: \d+ display_name=(.*?), data1=(.*)$", line.rstrip())
        if not m:
            continue
        name, number = m.group(1).strip(), m.group(2).strip()
        if not number or number.upper() == "NULL":
            continue
        key = (name.lower(), digits(number) or number)
        if key in seen:
            continue
        seen.add(key)
        out.append((name if name and name.upper() != "NULL" else number, number))
    out.sort(key=lambda c: c[0].lower())
    return out


def parse_sims(text):
    """-> [{'sub': int, 'slot': int, 'name': str}] for the SIM cards that are in use."""
    sims = []
    for line in text.splitlines():
        m = re.search(r"_id=(\d+), sim_id=(-?\d+), display_name=(.*?), carrier_name=(.*)$", line.rstrip())
        if m and int(m.group(2)) >= 0:
            name = m.group(3).strip()
            if not name or name.upper() == "NULL":
                name = m.group(4).strip() if m.group(4).upper() != "NULL" else ""
            sims.append({"sub": int(m.group(1)), "slot": int(m.group(2)), "name": name})
    sims.sort(key=lambda s: s["slot"])
    return sims


def dial_cmd(number, slot):
    """Shell command that starts a call. Phones differ in how they pick the SIM, so several
    well known extras are sent together."""
    uri = "tel:" + urllib.parse.quote(number, safe="+")
    cmd = "am start -a android.intent.action.CALL -d " + shlex.quote(uri)
    if slot >= 0:
        for key in ("com.android.phone.extra.slot", "slot", "simSlot", "slot_id", "phone"):
            cmd += f" --ei {key} {slot}"
        cmd += " --ez com.android.phone.force.slot true"
    return cmd


def sms_send_cmd(sdk, number, text, sub_id):
    q = shlex.quote
    if sdk >= 30:
        args = (f"i32 {sub_id} s16 com.android.mms.service s16 null s16 {q(number)} s16 null "
                f"s16 {q(text)} s16 null s16 null i32 0 i64 0")
    else:
        args = (f"i32 {sub_id} s16 com.android.mms.service s16 {q(number)} s16 null "
                f"s16 {q(text)} s16 null s16 null i32 0")
    return "service call isms 5 " + args


def sms_compose_cmd(number, text):
    return ("am start -a android.intent.action.SENDTO -d " + shlex.quote("sms:" + number) +
            " --es sms_body " + shlex.quote(text) + " --ez exit_on_sent true")


def send_sms(number, text, sub_id):
    """Send a text message through the phone. Returns (sent, message)."""
    rc, out, _err = adb("shell", "getprop ro.build.version.sdk", timeout=15)
    sdk = int(out.strip()) if out.strip().isdigit() else 30
    rc, out, err = adb("shell", sms_send_cmd(sdk, number, text, sub_id), timeout=30)
    if rc == 0 and re.search(r"Parcel\(\s*0{8}\b", out) and "xception" not in out + err:
        return True, "Message sent"
    adb("shell", sms_compose_cmd(number, text), timeout=20)
    return False, "The phone would not send it directly. The message is open on the phone: press Send there."


def pause_media():
    """Pauses every playing media player on this computer. Returns their names."""
    if not shutil.which("playerctl"):
        return []
    paused = []
    try:
        names = subprocess.run(["playerctl", "-l"], capture_output=True, text=True, timeout=5).stdout.split()
        for name in names:
            status = subprocess.run(["playerctl", "-p", name, "status"], capture_output=True,
                                    text=True, timeout=5).stdout.strip()
            if status == "Playing":
                subprocess.run(["playerctl", "-p", name, "pause"], timeout=5)
                paused.append(name)
    except (OSError, subprocess.SubprocessError):
        pass
    return paused


def resume_media(names):
    for name in names:
        try:
            subprocess.run(["playerctl", "-p", name, "play"], timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass


def _is(*values):
    return lambda v: v in values


TOGGLES = [
    {"key": "dnd", "title": "Do not disturb", "icon": "weather-clear-night-symbolic",
     "get": "settings get global zen_mode", "is_on": _is("1"),
     "on": "cmd notification set_dnd priority", "off": "cmd notification set_dnd off"},
    {"key": "silent", "title": "Mute all", "icon": "audio-volume-muted-symbolic",
     "get": "settings get global zen_mode", "is_on": _is("2"),
     "on": "cmd notification set_dnd none", "off": "cmd notification set_dnd off"},
    {"key": "wifi", "title": "Wi-Fi", "icon": "network-wireless-symbolic",
     "get": "settings get global wifi_on", "is_on": _is("1"),
     "on": "svc wifi enable", "off": "svc wifi disable"},
    {"key": "airplane", "title": "Airplane mode", "icon": "airplane-mode-symbolic",
     "get": "settings get global airplane_mode_on", "is_on": _is("1"),
     "on": "cmd connectivity airplane-mode enable", "off": "cmd connectivity airplane-mode disable"},
    {"key": "bluetooth", "title": "Bluetooth", "icon": "bluetooth-symbolic",
     "get": "settings get global bluetooth_on", "is_on": _is("1"),
     "on": "svc bluetooth enable; cmd bluetooth_manager enable",
     "off": "svc bluetooth disable; cmd bluetooth_manager disable"},
    {"key": "data", "title": "Mobile data", "icon": "network-cellular-symbolic",
     "get": "settings get global mobile_data", "is_on": _is("1"),
     "on": "svc data enable", "off": "svc data disable"},
    {"key": "location", "title": "Location", "icon": "find-location-symbolic",
     "get": "settings get secure location_mode", "is_on": lambda v: v not in ("", "0", "null"),
     "on": "cmd location set-location-enabled true", "off": "cmd location set-location-enabled false"},
    {"key": "rotate", "title": "Auto-rotate", "icon": "object-rotate-right-symbolic",
     "get": "settings get system accelerometer_rotation", "is_on": _is("1"),
     "on": "settings put system accelerometer_rotation 1",
     "off": "settings put system accelerometer_rotation 0"},
    {"key": "saver", "title": "Battery saver", "icon": "battery-level-50-symbolic",
     "get": "settings get global low_power", "is_on": _is("1"),
     "on": "settings put global low_power 1", "off": "settings put global low_power 0"},
    {"key": "awake", "title": "Stay awake", "icon": "weather-clear-symbolic",
     "get": "settings get global stay_on_while_plugged_in",
     "is_on": lambda v: v not in ("", "0", "null"),
     "on": "svc power stayon true", "off": "svc power stayon false"},
]


def toggles_script():
    return "; ".join(f"echo @@{t['key']}; {t['get']}" for t in TOGGLES)


def parse_toggles(text):
    """-> {key: bool} from the output of toggles_script()."""
    values, cur = {}, None
    for line in text.splitlines():
        if line.startswith("@@"):
            cur = line[2:].strip()
            values[cur] = ""
        elif cur and cur in {t["key"] for t in TOGGLES} and not values[cur]:
            values[cur] = line.strip()
    return {t["key"]: bool(t["is_on"](values.get(t["key"], ""))) for t in TOGGLES if t["key"] in values}


def parse_notifications(text):
    """-> [{'app', 'title', 'text', 'key'}] from `dumpsys notification --noredact`."""
    out, seen = [], set()

    def clean(value):
        value = value.strip()
        m = re.match(r"^[\w.]+ \((.*)\)$", value)
        return (m.group(1) if m else value).strip()

    for block in re.split(r"\n(?=\s*NotificationRecord\()", text)[1:]:
        pkg = re.search(r"\bpkg=(\S+)", block)
        key = re.search(r"\bkey=(\S+)", block)
        flags = re.search(r"\bflags=0x([0-9a-fA-F]+)", block)
        if not pkg or not key or key.group(1) in seen:
            continue
        if flags and int(flags.group(1), 16) & (0x2 | 0x40 | 0x200):  # ongoing, service, group summary
            continue
        title = re.search(r"android\.title=(.*)", block)
        body = re.search(r"android\.(?:bigText|text)=(.*)", block)
        title, body = clean(title.group(1)) if title else "", clean(body.group(1)) if body else ""
        if title.lower() == "null":
            title = ""
        if body.lower() == "null":
            body = ""
        if not title and not body:
            continue
        seen.add(key.group(1))
        out.append({"app": pretty_name(pkg.group(1)), "title": title, "text": body, "key": key.group(1)})
    return out[:40]
