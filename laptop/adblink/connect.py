"""Connecting to the phone with adb: USB, Wi-Fi, Tailscale and Bluetooth tethering.

No GTK in here, so the command line, the window and the phone server can all use it.

The usual reasons adb "will not connect" and what this module does about each one:

* ``adb tcpip 5555`` is forgotten when the phone restarts      -> ``usb_to_wifi`` redoes it in one step
  and every host that worked once is remembered and re-tried automatically (``reconnect_saved``).
* Android 11 "Wireless debugging" needs a pairing code           -> ``pair`` + ``mdns_services``.
* "unauthorized": the phone is waiting for you to tap "Allow"    -> explained by ``explain``.
* The phone is on another network / Tailscale is off             -> ``diagnose`` checks step by step.
* Bluetooth: adb cannot talk over Bluetooth by itself. What works is *Bluetooth tethering*, which gives
  the laptop and the phone a small network. ``bluetooth_tether`` sets that up, then adb uses it as Wi-Fi.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field

from .paths import config_dir

ADB_TIMEOUT = 20


# ----------------------------------------------------------------------------- running adb

def adb_path():
    return shutil.which("adb")


def run(argv, timeout=ADB_TIMEOUT):
    """Run a program; returns (returncode, combined output). Never raises."""
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return 127, f"{argv[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, f"{argv[0]} timed out"
    except OSError as e:
        return 126, str(e)


def adb(*args, timeout=ADB_TIMEOUT):
    return run(["adb", *args], timeout)


@dataclass
class Device:
    serial: str
    state: str                      # device / offline / unauthorized / no permissions ...
    model: str = ""
    product: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def over_network(self):
        return ":" in self.serial or "._adb-tls-" in self.serial

    @property
    def ready(self):
        return self.state == "device"

    @property
    def label(self):
        name = (self.model or self.product or "Android phone").replace("_", " ")
        return f"{name}  ·  {self.serial}"


def parse_devices(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("List of", "*", "adb server")):
            continue
        m = re.match(r"(\S+)\s+(device|offline|unauthorized|no permissions|recovery|sideload|bootloader|host|authorizing)\b(.*)", line)
        if not m:
            continue
        info = dict(kv.split(":", 1) for kv in m.group(3).split() if ":" in kv)
        out.append(Device(m.group(1), m.group(2), info.get("model", ""), info.get("product", ""), info))
    return out


def devices():
    rc, out = adb("devices", "-l", timeout=10)
    return parse_devices(out) if rc == 0 else []


# ----------------------------------------------------------------------------- remembered hosts

def _hosts_file():
    return config_dir() / "hosts.json"


def saved_hosts():
    try:
        data = json.loads(_hosts_file().read_text("utf-8"))
        return [h for h in data if isinstance(h, dict) and h.get("host")]
    except (OSError, ValueError):
        return []


def save_host(host, port=5555, name=""):
    hosts = [h for h in saved_hosts() if not (h["host"] == host and int(h.get("port", 5555)) == int(port))]
    hosts.insert(0, {"host": host, "port": int(port), "name": name, "seen": int(time.time())})
    try:
        _hosts_file().write_text(json.dumps(hosts[:12], indent=1), "utf-8")
    except OSError:
        pass


def forget_host(host, port=None):
    hosts = [h for h in saved_hosts() if not (h["host"] == host and (port is None or int(h.get("port", 5555)) == int(port)))]
    try:
        _hosts_file().write_text(json.dumps(hosts, indent=1), "utf-8")
    except OSError:
        pass


# ----------------------------------------------------------------------------- explaining errors

HINTS = [
    (r"unauthorized|authorizing|failed to authenticate",
     "The phone is asking for permission. Look at the phone screen and tap Allow "
     "(tick \"Always allow from this computer\"). If no question appears: Developer options -> "
     "Revoke USB debugging authorizations, then plug the cable again."),
    (r"connection refused",
     "The phone is reachable but adb is not listening on that port. After a restart Android forgets "
     "network mode. Plug the USB cable once and press \"Switch to Wi-Fi\", or use Wireless debugging "
     "(Developer options) and pair with a code."),
    (r"timed out|no route to host|network is unreachable|cannot connect|unable to connect|10060|10061",
     "The phone cannot be reached on the network. Check that both are on the same Wi-Fi (or that "
     "Tailscale is on in both), that the phone screen is awake, and that the IP address did not change."),
    (r"offline",
     "The phone shows as offline. Unplug and replug the cable, or run \"adb kill-server\", then try again."),
    (r"no permissions|insufficient permissions|udev",
     "Linux is not letting your user open the phone. Install the android udev rules "
     "(package android-udev-rules / android-tools) and replug, or run adb as the same user that owns the session."),
    (r"wrong password|password not set|failed: ",
     "Pairing failed. On the phone open Developer options -> Wireless debugging -> "
     "\"Pair device with pairing code\" and use the *pairing* port and code shown there (they change every time)."),
    (r"not installed|command not found",
     "adb is not installed. Run:  adblink install-deps"),
]


def explain(text):
    low = (text or "").lower()
    for pat, hint in HINTS:
        if re.search(pat, low):
            return hint
    return ""


@dataclass
class Result:
    ok: bool
    message: str
    hint: str = ""


# ----------------------------------------------------------------------------- connect / pair

def clean_host(text):
    text = (text or "").strip()
    text = re.sub(r"^\w+://", "", text).split("/")[0]
    return text


def split_host_port(text, default=5555):
    text = clean_host(text)
    m = re.fullmatch(r"(\[[0-9a-fA-F:]+\]|[^:]+)(?::(\d{1,5}))?", text)
    if not m:
        return text, default
    return m.group(1), int(m.group(2) or default)


def connect(host, port=5555, timeout=8):
    host, p = split_host_port(host, port)
    target = f"{host}:{p}"
    rc, out = adb("connect", target, timeout=timeout + 4)
    ok = bool(re.match(r"\s*(already )?connected to", out, re.I))
    if ok:
        save_host(host, p)
        time.sleep(0.3)
        for d in devices():
            if d.serial == target and d.state == "unauthorized":
                return Result(False, "Connected, but the phone has not allowed this computer yet.", explain("unauthorized"))
        return Result(True, out.splitlines()[0] if out else f"connected to {target}")
    return Result(False, out.splitlines()[0] if out else "connection failed", explain(out))


def disconnect(host=None):
    return adb("disconnect", host) if host else adb("disconnect")


def pair(host_port, code):
    host, port = split_host_port(host_port, 0)
    if not port:
        return Result(False, "Write the pairing address like 192.168.1.20:37123 (the port shown in the pairing window).")
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        return Result(False, "The pairing code has 6 digits.")
    rc, out = adb("pair", f"{host}:{port}", code, timeout=25)
    if re.search(r"successfully paired", out, re.I):
        return Result(True, out.splitlines()[0])
    return Result(False, out.splitlines()[0] if out else "pairing failed", explain(out) or explain("wrong password"))


def mdns_services():
    """Phones that announce Wireless debugging: [{'name', 'kind': 'connect'|'pairing', 'host', 'port'}]."""
    rc, out = adb("mdns", "services", timeout=8)
    res = []
    for line in out.splitlines():
        m = re.match(r"(\S+)\s+_adb-tls-(connect|pairing)\._tcp\.?\s+(\S+?):(\d+)", line)
        if m:
            res.append({"name": m.group(1), "kind": m.group(2), "host": m.group(3), "port": int(m.group(4))})
    return res


def phone_wifi_ip(serial=None):
    """The phone's Wi-Fi address, read over the cable."""
    base = ["-s", serial] if serial else []
    for cmd in ("ip -f inet addr show wlan0", "ip route", "ifconfig wlan0"):
        rc, out = adb(*base, "shell", cmd, timeout=10)
        if rc != 0:
            continue
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out) or re.search(r"src (\d+\.\d+\.\d+\.\d+)", out) \
            or re.search(r"inet addr:(\d+\.\d+\.\d+\.\d+)", out)
        if m and not m.group(1).startswith("127."):
            return m.group(1)
    return ""


def usb_to_wifi(serial=None, port=5555):
    """With the phone on USB: turn network mode on, find its address and connect (remembered for next time)."""
    usb = [d for d in devices() if d.ready and not d.over_network]
    if serial is None:
        if not usb:
            return Result(False, "Plug the phone with the USB cable first (and allow USB debugging).",
                          explain("unauthorized") if any(d.state == "unauthorized" for d in devices()) else "")
        serial = usb[0].serial
    ip = phone_wifi_ip(serial)
    if not ip:
        return Result(False, "The phone has no Wi-Fi address. Connect it to Wi-Fi (or turn on Tailscale) and try again.")
    rc, out = adb("-s", serial, "tcpip", str(port), timeout=15)
    if rc != 0 and "restarting" not in out.lower():
        return Result(False, out or "adb tcpip failed", explain(out))
    time.sleep(2.0)
    res = Result(False, "")
    for _ in range(3):
        res = connect(ip, port, timeout=6)
        if res.ok:
            break
        time.sleep(1.2)
    if res.ok:
        res.message = f"Connected over Wi-Fi: {ip}:{port}. You can unplug the cable."
    return res


def reconnect_saved(max_hosts=4, timeout=4):
    """Try every remembered phone that is not connected right now. Returns the list of hosts that came back."""
    have = {d.serial for d in devices() if d.state in ("device", "unauthorized")}
    back = []
    for h in saved_hosts()[:max_hosts]:
        target = f"{h['host']}:{int(h.get('port', 5555))}"
        if target in have:
            continue
        if not port_open(h["host"], int(h.get("port", 5555)), timeout=1.2):
            continue
        res = connect(h["host"], int(h.get("port", 5555)), timeout=timeout)
        if res.ok:
            back.append(target)
    return back


# ----------------------------------------------------------------------------- finding the phone

def port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def tailscale_peers():
    """Addresses of Android devices on your tailnet (empty when Tailscale is not installed / running)."""
    if not shutil.which("tailscale"):
        return []
    rc, out = run(["tailscale", "status", "--json"], timeout=6)
    if rc != 0:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    peers = []
    for p in (data.get("Peer") or {}).values():
        if str(p.get("OS", "")).lower() == "android" and p.get("TailscaleIPs"):
            peers.append({"name": p.get("HostName", "phone"), "host": p["TailscaleIPs"][0], "online": bool(p.get("Online"))})
    return peers


def neighbours():
    rc, out = run(["ip", "-4", "neigh"], timeout=3)
    res = []
    for line in out.splitlines():
        m = re.match(r"(\d+\.\d+\.\d+\.\d+) dev (\S+).*?(REACHABLE|STALE|DELAY|PROBE)", line)
        if m:
            res.append(m.group(1))
    return res


def gateways():
    """Default gateways of every network card. When the phone shares its connection (hotspot, USB or
    Bluetooth tethering) the phone *is* the gateway."""
    rc, out = run(["ip", "-4", "route", "show"], timeout=3)
    res = []
    for line in out.splitlines():
        m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", line)
        if m and m.group(1) not in res:
            res.append(m.group(1))
    return res


def find_phone(port=5555):
    """Looks around for a phone with adb listening. Returns [{'host','port','via'}]."""
    seen, found = set(), []

    def add(host, why):
        if host and host not in seen and port_open(host, port, timeout=0.8):
            seen.add(host)
            found.append({"host": host, "port": port, "via": why})

    for h in saved_hosts():
        add(h["host"], "remembered")
    for p in tailscale_peers():
        if p["online"]:
            add(p["host"], "Tailscale")
    for g in gateways():
        add(g, "gateway (hotspot / tethering)")
    for n in neighbours():
        add(n, "same network")
    for s in mdns_services():
        if s["kind"] == "connect" and s["host"] not in seen:
            seen.add(s["host"])
            found.append({"host": s["host"], "port": s["port"], "via": "Wireless debugging"})
    return found


# ----------------------------------------------------------------------------- Bluetooth

def bluetooth_devices():
    """Paired Bluetooth devices: [{'mac','name','connected'}]."""
    if not shutil.which("bluetoothctl"):
        return []
    rc, out = run(["bluetoothctl", "devices", "Paired"], timeout=6)
    if rc != 0 or not out.strip():
        rc, out = run(["bluetoothctl", "devices"], timeout=6)
    res = []
    for line in out.splitlines():
        m = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)", line.strip())
        if m:
            info = run(["bluetoothctl", "info", m.group(1)], timeout=5)[1]
            res.append({"mac": m.group(1), "name": m.group(2), "connected": "Connected: yes" in info,
                        "tether": "Network Access Point" in info or "NAP" in info})
    return res


def bluetooth_interface():
    """(interface, gateway) of an active Bluetooth network (bnep0), or ('', '')."""
    rc, out = run(["ip", "-4", "-o", "addr", "show"], timeout=3)
    for line in out.splitlines():
        m = re.match(r"\d+:\s+(bnep\d+|bt-pan\S*)\s+inet (\d+\.\d+\.\d+\.\d+)/", line)
        if m:
            r2 = run(["ip", "-4", "route", "show", "dev", m.group(1)], timeout=3)[1]
            g = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", r2)
            guess = g.group(1) if g else re.sub(r"\.\d+$", ".1", m.group(2))
            return m.group(1), guess
    return "", ""


def bluetooth_tether(mac):
    """Join the phone's Bluetooth tethering network. On the phone turn on Settings -> Hotspot & tethering ->
    Bluetooth tethering first. Returns Result; on success the message holds the phone's address."""
    if not shutil.which("bluetoothctl"):
        return Result(False, "bluetoothctl is missing. Run:  adblink install-deps")
    run(["bluetoothctl", "connect", mac], timeout=15)
    iface, gw = bluetooth_interface()
    if not iface and shutil.which("nmcli"):
        name = "adblink-bt-" + mac.replace(":", "")
        if run(["nmcli", "-t", "-f", "NAME", "connection", "show"], timeout=5)[1].count(name) == 0:
            run(["nmcli", "connection", "add", "type", "bluetooth", "con-name", name,
                 "bluetooth.bdaddr", mac, "bluetooth.type", "panu"], timeout=10)
        run(["nmcli", "connection", "up", name], timeout=25)
        for _ in range(10):
            iface, gw = bluetooth_interface()
            if iface:
                break
            time.sleep(1)
    if not iface:
        return Result(False, "Could not join the phone's Bluetooth network.",
                      "On the phone: turn on Bluetooth tethering (Settings -> Hotspot & tethering). "
                      "On the laptop: make sure the phone is paired in Bluetooth settings, then try again. "
                      "Or connect from the system menu: Bluetooth -> your phone -> \"Connect to network\".")
    return Result(True, gw)


# ----------------------------------------------------------------------------- one-shot report

def diagnose(host, port=5555):
    """Step-by-step test used by the 'Why can't I connect?' button. Returns [(ok, text)]."""
    steps = []
    if not adb_path():
        return [(False, "adb is not installed. Run:  adblink install-deps")]
    steps.append((True, "adb is installed"))
    host, port = split_host_port(host, port)
    rc, out = run(["ping", "-c", "1", "-W", "2", host], timeout=5)
    steps.append((rc == 0, f"{host} answers ping" if rc == 0 else
                  f"{host} does not answer ping (the phone may be asleep, or ping may be blocked)"))
    open_ = port_open(host, port, timeout=2.0)
    steps.append((open_, f"port {port} is open" if open_ else
                  f"port {port} is closed. After a restart: plug USB and press \"Switch to Wi-Fi\""))
    if open_:
        res = connect(host, port, timeout=8)
        steps.append((res.ok, res.message))
        if not res.ok and res.hint:
            steps.append((False, res.hint))
    return steps
