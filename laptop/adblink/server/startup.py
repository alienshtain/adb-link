"""Start / stop the server. Used by the desktop app (in a thread) and by ``adblink server`` (headless)."""
from __future__ import annotations

import json
import re
import socket
import threading

from .clipboard import clipboard_watcher
from .common import FLAGS, IS_LINUX, VERSION, ctx, log, run_quiet, which
from .http import Handler, Server
from .inputdev import input_problem
from .notifications import dbus_notification_watcher
from .state import Pairing, State
from .system import capabilities, os_pretty

DEFAULT_PORT = 8765
_started = set()
DISCOVERY_PORT = 8766          # UDP: the phone shouts "ADBLINK?" and every server answers


def local_addresses():
    addrs = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        addrs.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    if which("ip"):
        rc, out, _ = run_quiet(["ip", "-4", "-o", "addr", "show"], timeout=3)
        for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)/", out.decode("utf-8", "replace")):
            addrs.append(m.group(1))
    try:
        for r in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.append(r[4][0])
    except OSError:
        pass
    seen, out = set(), []
    for a in addrs:
        if a.startswith("127.") or a.startswith("169.254.") or a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out


def is_tailscale(ip):
    p = ip.split(".")
    return len(p) == 4 and p[0] == "100" and 64 <= int(p[1]) <= 127


def ordered_addresses():
    addrs = local_addresses()
    ts = [a for a in addrs if is_tailscale(a)]
    return ts + [a for a in addrs if a not in ts]


def ensure_state():
    if ctx.state is None:
        ctx.state = State()
    if ctx.pairing is None:
        ctx.pairing = Pairing(ctx.state)
    return ctx.state


def pairing_code():
    ensure_state()
    return ctx.pairing.code


def new_code():
    ensure_state()
    ctx.pairing.new_code()
    return ctx.pairing.code


def discovery_loop(port, stop):
    """Answer the phone's broadcast so it can find this computer without typing an address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", DISCOVERY_PORT))
        s.settimeout(1.0)
    except OSError as e:
        log("discovery off:", e)
        return
    reply = json.dumps({"app": "adblink", "name": socket.gethostname(), "port": port,
                        "version": VERSION, "os": os_pretty()}).encode()
    while not stop.is_set():
        try:
            data, addr = s.recvfrom(256)
        except socket.timeout:
            continue
        except OSError:
            break
        if data.strip() == b"ADBLINK?":
            try:
                s.sendto(reply, addr)
            except OSError:
                pass
    s.close()


class ServerHandle:
    def __init__(self, httpd, host, port):
        self.httpd, self.host, self.port = httpd, host, port
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.5},
                                       name="adblink-http", daemon=True)

    def stop(self):
        self.stop_event.set()
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except OSError:
            pass


def start(host="0.0.0.0", port=DEFAULT_PORT, *, shell=True, clipboard=True, notifications=True,
          verbose=False, background=True):
    """Starts the server in a thread (background=True) and returns a ServerHandle.
    Raises OSError when the port is already in use."""
    FLAGS.verbose, FLAGS.shell, FLAGS.clipboard, FLAGS.notifications = verbose, shell, clipboard, notifications
    ensure_state()
    httpd = Server((host, port), Handler)
    handle = ServerHandle(httpd, host, port)
    if clipboard and "clipboard" not in _started:
        _started.add("clipboard")
        threading.Thread(target=clipboard_watcher, daemon=True).start()
    if notifications and "notifications" not in _started:
        _started.add("notifications")
        threading.Thread(target=dbus_notification_watcher, daemon=True).start()
    threading.Thread(target=discovery_loop, args=(port, handle.stop_event), daemon=True).start()
    if background:
        handle.thread.start()
    return handle


def status():
    """What the window shows: addresses, code, which features work."""
    ensure_state()
    caps = capabilities()
    return {"name": socket.gethostname(), "os": os_pretty(), "addresses": ordered_addresses(),
            "code": ctx.pairing.code, "paired": ctx.state.phones(), "caps": caps,
            "last_seen": ctx.last_seen, "last_phone": ctx.last_phone}


def banner(port):
    st = status()
    lines = [f"\n  ADB Link {VERSION}  -  {st['name']}  ({st['os']})",
             "  ------------------------------------------------"]
    for a in st["addresses"] or ["<your-ip>"]:
        lines.append(f"  Address : {a}:{port}" + ("   (Tailscale)" if is_tailscale(a) else ""))
    lines.append(f"  Code    : {st['code']}   (changes after every pairing)")
    caps = st["caps"]
    lines.append(f"  Input   : {caps['input'] or 'NOT READY - ' + (input_problem() or 'run: adblink setup-input')}")
    lines.append(f"  Terminal: {'on' if FLAGS.shell else 'off'}\n")
    return "\n".join(lines)


def serve_forever(host, port, **flags):
    """Headless mode: print the address and block until Ctrl+C."""
    import time
    try:
        handle = start(host, port, **flags)
    except OSError as e:
        print(f"Cannot use port {port}: {e}\nIs ADB Link already running? Try another one with --port.")
        return 1
    print(banner(port), flush=True)
    if IS_LINUX and which("notify-send") and not ctx.state.has_tokens():
        run_quiet(["notify-send", "-a", "ADB Link", "ADB Link is ready",
                   f"Pairing code {ctx.pairing.code}  -  address {(ordered_addresses() or ['?'])[0]}:{port}"], timeout=5)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nStopped.")
        handle.stop()
    return 0
