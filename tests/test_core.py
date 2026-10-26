"""Tests that need no phone, no display and no root:  python3 -m unittest discover -s tests -v"""
import json
import os
import socket
import struct
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "laptop"))
_tmp = tempfile.mkdtemp(prefix="adblink-test-")
os.environ["XDG_CONFIG_HOME"] = _tmp + "/config"
os.environ["XDG_CACHE_HOME"] = _tmp + "/cache"
os.environ["HOME"] = _tmp

from adblink import connect as conn, deps  # noqa: E402
from adblink.server import inputdev, startup  # noqa: E402
from adblink.server.common import ApiError  # noqa: E402

DEVICES = """List of devices attached
R58M1234ABC            device usb:1-1 product:RMX2001 model:RMX2001 device:RMX2001L1 transport_id:3
192.168.1.20:5555      device product:RMX2001 model:RMX2001 device:RMX2001L1 transport_id:5
100.97.240.72:5555     unauthorized transport_id:6
adb-ABC123._adb-tls-connect._tcp offline
"""


class Connect(unittest.TestCase):
    def test_parse_devices(self):
        d = conn.parse_devices(DEVICES)
        self.assertEqual([x.serial for x in d], ["R58M1234ABC", "192.168.1.20:5555", "100.97.240.72:5555",
                                                 "adb-ABC123._adb-tls-connect._tcp"])
        self.assertEqual([x.state for x in d], ["device", "device", "unauthorized", "offline"])
        self.assertEqual([x.over_network for x in d], [False, True, True, True])
        self.assertEqual(d[0].model, "RMX2001")
        self.assertTrue(d[0].ready and not d[2].ready)

    def test_split_host_port(self):
        self.assertEqual(conn.split_host_port("192.168.1.20"), ("192.168.1.20", 5555))
        self.assertEqual(conn.split_host_port("http://10.0.0.5:37123/"), ("10.0.0.5", 37123))
        self.assertEqual(conn.split_host_port(" 100.64.0.1:5556 "), ("100.64.0.1", 5556))

    def test_explain(self):
        self.assertIn("Allow", conn.explain("error: device unauthorized."))
        self.assertIn("network mode", conn.explain("failed to connect to '1.2.3.4:5555': Connection refused").lower())
        self.assertIn("same Wi-Fi", conn.explain("failed to connect to x: Connection timed out"))
        self.assertEqual(conn.explain("all fine"), "")

    def test_connect_result_parsing(self):
        with mock.patch.object(conn, "adb", return_value=(0, "connected to 10.0.0.9:5555")), \
                mock.patch.object(conn, "devices", return_value=[conn.Device("10.0.0.9:5555", "device")]), \
                mock.patch.object(conn, "save_host") as save:
            r = conn.connect("10.0.0.9")
            self.assertTrue(r.ok)
            save.assert_called_once()
        with mock.patch.object(conn, "adb", return_value=(0, "failed to connect to '10.0.0.9:5555': Connection refused")):
            r = conn.connect("10.0.0.9")
            self.assertFalse(r.ok)
            self.assertIn("network mode", r.hint.lower())
        with mock.patch.object(conn, "adb", return_value=(0, "connected to 10.0.0.9:5555")), \
                mock.patch.object(conn, "devices", return_value=[conn.Device("10.0.0.9:5555", "unauthorized")]):
            r = conn.connect("10.0.0.9")
            self.assertFalse(r.ok)
            self.assertIn("Allow", r.hint)

    def test_pair_validation(self):
        self.assertFalse(conn.pair("192.168.1.2", "123456").ok)       # no port
        self.assertFalse(conn.pair("192.168.1.2:3000", "12").ok)      # short code
        with mock.patch.object(conn, "adb", return_value=(0, "Successfully paired to 192.168.1.2:3000 [guid=x]")):
            self.assertTrue(conn.pair("192.168.1.2:3000", "123 456").ok)
        with mock.patch.object(conn, "adb", return_value=(0, "Failed: Wrong password or password not set")):
            self.assertFalse(conn.pair("192.168.1.2:3000", "123456").ok)

    def test_mdns(self):
        out = ("List of discovered mdns services\n"
               "adb-R58M1234ABC-xyz\t_adb-tls-connect._tcp.\t192.168.1.20:41033\n"
               "adb-R58M1234ABC-xyz\t_adb-tls-pairing._tcp.\t192.168.1.20:37123\n")
        with mock.patch.object(conn, "adb", return_value=(0, out)):
            s = conn.mdns_services()
        self.assertEqual([(x["kind"], x["port"]) for x in s], [("connect", 41033), ("pairing", 37123)])

    def test_saved_hosts_roundtrip(self):
        conn._hosts_file().unlink(missing_ok=True)
        conn.save_host("1.2.3.4", 5555, "phone")
        conn.save_host("5.6.7.8", 5556)
        conn.save_host("1.2.3.4", 5555)
        h = conn.saved_hosts()
        self.assertEqual([x["host"] for x in h], ["1.2.3.4", "5.6.7.8"])
        conn.forget_host("1.2.3.4")
        self.assertEqual([x["host"] for x in conn.saved_hosts()], ["5.6.7.8"])

    def test_usb_to_wifi_flow(self):
        calls = []

        def fake_adb(*a, timeout=20):
            calls.append(a)
            if a[:3] == ("-s", "SER", "shell"):
                return 0, "3: wlan0    inet 192.168.1.77/24 brd 192.168.1.255 scope global wlan0"
            if "tcpip" in a:
                return 0, "restarting in TCP mode port: 5555"
            return 0, ""
        with mock.patch.object(conn, "adb", fake_adb), \
                mock.patch.object(conn, "devices", return_value=[conn.Device("SER", "device")]), \
                mock.patch.object(conn, "connect", return_value=conn.Result(True, "connected to 192.168.1.77:5555")), \
                mock.patch.object(conn.time, "sleep"):
            r = conn.usb_to_wifi()
        self.assertTrue(r.ok, r)
        self.assertIn("192.168.1.77", r.message)
        self.assertTrue(any("tcpip" in c for c in calls))

    def test_usb_to_wifi_without_usb_phone(self):
        with mock.patch.object(conn, "devices", return_value=[conn.Device("1.2.3.4:5555", "device")]):
            r = conn.usb_to_wifi()
        self.assertFalse(r.ok)
        self.assertIn("USB", r.message)


class Deps(unittest.TestCase):
    def test_report_and_install_command(self):
        rep = deps.report(("core", "recommended", "optional"))
        keys = [d.key for d, _ok in rep]
        self.assertIn("adb", keys)
        self.assertIn("brightnessctl", keys)
        for mgr in ("apt", "dnf", "pacman", "zypper"):
            for d in deps.DEPS:
                self.assertIn(mgr, d.pkgs, f"{d.key} has no package name for {mgr}")
            self.assertTrue(deps.install_command(mgr, ["x"]))

    def test_session_guess(self):
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}):
            self.assertEqual(deps.session(), ("gnome", "wayland"))
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "x11"}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            self.assertEqual(deps.session(), ("kde", "x11"))


class Input(unittest.TestCase):
    def test_combo(self):
        self.assertEqual(inputdev.parse_combo("ctrl+shift+t"), (["ctrl", "shift"], "t"))
        self.assertEqual(inputdev.parse_combo("super"), ([], "super"))
        self.assertEqual(inputdev.parse_combo("alt+tab"), (["alt"], "tab"))
        for bad in ("", "hyper+x", "ctrl+nope"):
            with self.assertRaises(ApiError):
                inputdev.parse_combo(bad)

    def test_every_ascii_char_has_a_key(self):
        for ch in "abcXYZ0189 !@#$%^&*()_+-=[]{};:'\",.<>/?\\|`~\n\t":
            self.assertIn(ch, inputdev.CHARS, ch)
            name, _shift = inputdev.CHARS[ch]
            self.assertIn(name, inputdev.KEYS, ch)

    def test_uinput_events(self):
        r, w = os.pipe()
        u = inputdev.UInput()
        u.fd = w   # pretend the device is open
        u.move(5, -3)
        u.click("right")
        u.scroll(dy=2)
        u.key("ctrl+c")
        u.text("Hi")
        os.close(w)
        data = os.read(r, 100000)
        size = u.struct.size
        self.assertEqual(len(data) % size, 0)
        evs = [struct.unpack("llHHi", data[i:i + size])[2:] for i in range(0, len(data), size)]
        self.assertIn((2, 0, 5), evs)            # REL_X
        self.assertIn((2, 1, -3), evs)           # REL_Y
        self.assertIn((1, 0x111, 1), evs)        # right button down
        self.assertIn((1, 0x111, 0), evs)        # ... and up
        self.assertIn((2, 8, 2), evs)            # wheel
        self.assertIn((1, 29, 1), evs)           # ctrl down
        self.assertIn((1, 46, 1), evs)           # c
        self.assertIn((1, 42, 1), evs)           # shift for "H"
        self.assertIn((1, 35, 1), evs)           # h
        self.assertEqual(evs[-1][:2], (0, 0))    # ends with a sync event

    def test_input_without_backend_explains(self):
        with mock.patch.object(inputdev, "input_backend", return_value=None), \
                mock.patch.object(inputdev, "uinput_status", return_value=(False, "No permission for /dev/uinput. Run once:  adblink setup-input")):
            with self.assertRaises(ApiError) as cm:
                inputdev.do_input({"kind": "move", "dx": 1, "dy": 1})
        self.assertEqual(cm.exception.status, 501)
        self.assertIn("setup-input", cm.exception.msg)

    def test_do_input_dispatch(self):
        be = mock.Mock()
        be.name = "fake"
        be.can_type.return_value = True
        with mock.patch.object(inputdev, "_backend", return_value=be):
            inputdev.do_input({"kind": "move", "dx": 4, "dy": 5})
            be.move.assert_called_with(4, 5)
            inputdev.do_input({"kind": "click", "button": "right", "count": 2})
            be.click.assert_called_with("right", 2)
            inputdev.do_input({"kind": "down"})
            be.button.assert_called_with("left", True)
            inputdev.do_input({"kind": "scroll", "dy": 3})
            be.scroll.assert_called_with(3, 0)
            inputdev.do_input({"kind": "key", "key": "ctrl+v"})
            be.key.assert_called_with("ctrl+v")
            inputdev.do_input({"kind": "text", "text": "hello"})
            be.text.assert_called_with("hello")
            with self.assertRaises(ApiError):
                inputdev.do_input({"kind": "explode"})


class Server(unittest.TestCase):
    def test_start_ping_discovery_adb_routes_stop(self):
        port = 18765
        handle = startup.start("127.0.0.1", port, shell=False, clipboard=False, notifications=False)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=5) as r:
                self.assertEqual(json.load(r)["app"], "adblink")
            # the phone's UDP search
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.sendto(b"ADBLINK?", ("127.0.0.1", startup.DISCOVERY_PORT))
            data, _ = s.recvfrom(1000)
            info = json.loads(data)
            self.assertEqual((info["app"], info["port"]), ("adblink", port))
            # pairing then the adb helper endpoints
            code = startup.pairing_code()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/pair", data=json.dumps({"code": code, "name": "T"}).encode(), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                token = json.load(r)["token"]
            with mock.patch("adblink.server.http.connect", return_value=conn.Result(False, "failed to connect", "hint!")) as c:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/adb/connect", data=b"{}", method="POST",
                                             headers={"Authorization": "Bearer " + token})
                with urllib.request.urlopen(req, timeout=5) as r:
                    body = json.load(r)
                self.assertEqual(body, {"ok": False, "message": "failed to connect", "hint": "hint!"})
                self.assertEqual(c.call_args[0][0], "127.0.0.1")     # defaults to the phone's own address
            self.assertTrue(startup.status()["paired"])
        finally:
            handle.stop()
        time.sleep(0.3)
        with self.assertRaises(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=2)


if __name__ == "__main__":
    unittest.main()
