"""Command line: ``adblink`` (window), ``adblink server`` (no window), ``adblink doctor`` and friends."""
from __future__ import annotations

import argparse
import sys

from . import connect as conn
from . import deps
from .paths import APP_NAME, VERSION

HELP = f"""{APP_NAME} {VERSION}

  adblink                     open the window (the phone app server runs inside it)
  adblink --background        start hidden (calls and notifications still work)
  adblink server              only the server for the phone app, no window (for servers / SSH)
  adblink code                show the pairing code      adblink reset-tokens   forget all paired phones

  adblink doctor              show which helper programs are missing
  adblink install-deps        install everything that is missing (asks for your password)
  adblink setup-input         allow the phone touchpad / keyboard to control this computer (once)

  adblink install             add ADB Link to the app menu         adblink install --autostart   also start at login
  adblink uninstall           remove the menu entry and autostart

  adblink connect [HOST[:PORT]]   connect the phone with adb (no argument: reconnect / look for it)
  adblink pair HOST:PORT CODE     pair with Android 11+ "Wireless debugging"
  adblink wifi                    phone on USB -> switch it to Wi-Fi and connect
  adblink diagnose HOST[:PORT]    step by step: why can't I connect?
  adblink bluetooth               list paired Bluetooth phones;  adblink bluetooth MAC   join its tethering network
  adblink install-phone [APK]     install the ADB Link phone app on the connected phone (downloads the latest one)
"""


def cmd_server(argv):
    from .server import startup
    ap = argparse.ArgumentParser(prog="adblink server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=startup.DEFAULT_PORT)
    ap.add_argument("--no-shell", action="store_true", help="switch the phone terminal off")
    ap.add_argument("--no-clipboard", action="store_true")
    ap.add_argument("--no-notifications", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    return startup.serve_forever(a.host, a.port, shell=not a.no_shell, clipboard=not a.no_clipboard,
                                 notifications=not a.no_notifications, verbose=a.verbose)


def cmd_code(_argv):
    from .server import startup
    print(startup.pairing_code())
    return 0


def cmd_reset(_argv):
    from .server import startup
    startup.ensure_state().reset_tokens()
    print("All phones were unpaired.")
    return 0


def cmd_doctor(_argv):
    print(deps.doctor_text())
    miss = deps.missing()
    print()
    print("Everything needed is installed." if not miss else
          f"{len(miss)} missing. Run:  adblink install-deps")
    return 0


def cmd_install_deps(argv):
    levels = ("core", "recommended", "optional") if "--all" in argv else ("core", "recommended")
    miss = deps.missing(levels)
    if not miss:
        print("Everything needed is already installed.")
    else:
        print("Missing:", ", ".join(d.title for d in miss))
        done, failed = deps.install(miss)
        print(f"\nInstalled: {', '.join(done) or '-'}")
        if failed:
            print(f"Could not install: {', '.join(failed)} (not available for your system - they are optional)")
    from .server.inputdev import setup_input_permissions, uinput_status
    if not uinput_status()[0]:
        print("\nPhone touchpad / keyboard needs a one-time permission...")
        print(setup_input_permissions()[1])
    return 0


def cmd_setup_input(_argv):
    from .server.inputdev import setup_input_permissions
    ok, msg = setup_input_permissions()
    print(msg)
    return 0 if ok else 1


def cmd_install(argv):
    from . import desktop
    f = desktop.install_desktop()
    print(f"Added to the app menu: {f}")
    if "--autostart" in argv:
        desktop.set_autostart(True)
        print("It will start in the background when you log in.")
    return 0


def cmd_uninstall(_argv):
    from . import desktop
    desktop.uninstall_desktop()
    print("Removed the menu entry and autostart. (Your commands and pairings in ~/.config/adblink are kept.)")
    return 0


def _show(res):
    print(("OK: " if res.ok else "FAILED: ") + res.message)
    if res.hint:
        print("  -> " + res.hint)
    return 0 if res.ok else 1


def cmd_connect(argv):
    if argv:
        return _show(conn.connect(argv[0]))
    back = conn.reconnect_saved()
    if back:
        print("Reconnected: " + ", ".join(back))
        return 0
    found = conn.find_phone()
    if not found:
        print("No phone found. Plug it with USB and run:  adblink wifi\n"
              "or on Android 11+: Developer options -> Wireless debugging -> Pair with code, then:  adblink pair HOST:PORT CODE")
        return 1
    for f in found:
        print(f"found {f['host']}:{f['port']}  ({f['via']})")
    f = found[0]
    return _show(conn.connect(f["host"], f["port"]))


def cmd_pair(argv):
    if len(argv) < 2:
        print("usage: adblink pair HOST:PORT CODE")
        return 2
    res = conn.pair(argv[0], argv[1])
    code = _show(res)
    if res.ok:
        for s in conn.mdns_services():
            if s["kind"] == "connect":
                print(f"Now connecting to {s['host']}:{s['port']} ...")
                return _show(conn.connect(s["host"], s["port"]))
        print("Paired. Now connect with:  adblink connect HOST:PORT  (the port on the Wireless debugging screen)")
    return code


def cmd_wifi(_argv):
    return _show(conn.usb_to_wifi())


def cmd_diagnose(argv):
    if not argv:
        print("usage: adblink diagnose HOST[:PORT]")
        return 2
    for ok, text in conn.diagnose(argv[0]):
        print(("  ok   " if ok else "  FAIL ") + text)
    return 0


def cmd_bluetooth(argv):
    if argv:
        res = conn.bluetooth_tether(argv[0])
        if res.ok:
            print(f"Joined the phone's Bluetooth network. The phone is at {res.message}.")
            print(f"Now:  adblink connect {res.message}   (needs adb network mode: adblink wifi once over USB)")
            return 0
        return _show(res)
    devs = conn.bluetooth_devices()
    if not devs:
        print("No paired Bluetooth devices found (is bluez installed and Bluetooth on?)")
        return 1
    for d in devs:
        print(f"{d['mac']}  {d['name']}{'  (connected)' if d['connected'] else ''}")
    print("\nOn the phone turn on Bluetooth tethering, then:  adblink bluetooth MAC")
    return 0


def cmd_install_phone(argv):
    from . import phoneapp
    ok, msg = phoneapp.install_to_phone(argv[0] if argv else "")
    print(msg)
    return 0 if ok else 1


COMMANDS = {
    "server": cmd_server, "code": cmd_code, "reset-tokens": cmd_reset, "doctor": cmd_doctor,
    "install-deps": cmd_install_deps, "setup-input": cmd_setup_input, "install": cmd_install,
    "uninstall": cmd_uninstall, "connect": cmd_connect, "pair": cmd_pair, "wifi": cmd_wifi,
    "diagnose": cmd_diagnose, "bluetooth": cmd_bluetooth, "install-phone": cmd_install_phone,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    if argv and argv[0] in ("-V", "--version", "version"):
        print(f"{APP_NAME} {VERSION}")
        return 0
    if argv and argv[0] in COMMANDS:
        return COMMANDS[argv[0]](argv[1:]) or 0
    # no sub-command: the window (needs GTK 4 + libadwaita)
    try:
        from .panel.app import main as gui_main
    except (ImportError, ValueError) as e:
        print(f"The window needs GTK 4 and libadwaita ({e}).\nRun:  adblink install-deps\n"
              f"Without a window you can still use:  adblink server")
        return 1
    return gui_main(argv)
