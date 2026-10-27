"""HTTP routes used by the phone app."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import socket
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .. import storage
from ..connect import connect, devices, pair
from .clipboard import _clip_state, set_clipboard
from .common import ApiError, FLAGS, VERSION, ctx, log
from .events import EVENTS
from .files import (
    IMAGE_EXT,
    make_thumb,
    need_exists,
    op_info,
    op_list,
    op_text,
    op_tree,
    resolve_path,
    safe_part,
    safe_rel,
    unique_path,
)
from .inputdev import do_input
from .notifications import show_notification
from .state import cmd_fields, fill_cmd
from .system import info_json, run_shell


# ----------------------------------------------------------------------------- http

MAX_JSON = 2_000_000


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ADBLink/" + VERSION

    def log_message(self, fmt, *args):
        log(self.address_string(), fmt % args)

    # ---- plumbing
    def send_json(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if self._unread:
            self.close_connection = True
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, data: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_JSON:
            raise ApiError(413, "Too big")
        raw = self.rfile.read(n) if n else b""
        self._unread = False
        if not raw:
            return {}
        try:
            v = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ApiError(400, "Bad JSON")
        if not isinstance(v, dict):
            raise ApiError(400, "Bad JSON")
        return v

    def authed(self) -> bool:
        h = self.headers.get("Authorization", "")
        if not h.startswith("Bearer "):
            return False
        name = ctx.state.token_name(h[7:].strip())
        if name is None:
            return False
        ctx.last_seen, ctx.last_phone, ctx.last_ip = time.time(), name, self.client_address[0]
        return True

    def handle_one(self, method):
        self._unread = method == "POST" and int(self.headers.get("Content-Length") or 0) > 0
        u = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        try:
            if method == "GET" and u.path == "/ping":
                return self.send_json(200, {"app": "adblink", "version": VERSION})
            if method == "POST" and u.path == "/pair":
                return self.route_pair()
            if not self.authed():
                raise ApiError(401, "not paired")
            self.route(method, u.path, q)
        except ApiError as e:
            self.send_json(e.status, {"error": e.msg})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception as e:  # never kill the server because of one request
            if FLAGS.verbose:
                traceback.print_exc()
            try:
                self.send_json(500, {"error": f"{type(e).__name__}: {e}"})
            except Exception:
                self.close_connection = True

    def do_GET(self):
        self.handle_one("GET")

    def do_POST(self):
        self.handle_one("POST")

    # ---- routes
    def route_pair(self):
        body = self.read_json()
        if not ctx.pairing.try_code(str(body.get("code", ""))):
            raise ApiError(403, "wrong code")
        token = ctx.state.add_token(str(body.get("name") or "Phone"))
        log("paired:", body.get("name"))
        self.send_json(200, {"token": token, "name": socket.gethostname()})

    def route(self, method, path, q):
        if method == "GET":
            if path == "/info":
                return self.send_json(200, info_json())
            if path == "/adb/devices":
                return self.send_json(200, {"devices": [d.__dict__ for d in devices()]})
            if path == "/commands":
                return self.send_json(200, ctx.state.commands_out())
            if path == "/files":
                return self.files_get(q)
            if path == "/events":
                after = int(q.get("after", 0))
                wait = max(0.0, min(float(q.get("wait", 0)), 30.0))
                last, events = EVENTS.wait(after, wait)
                return self.send_json(200, {"last": last, "events": events})
        else:
            if path == "/commands":
                return self.send_json(200, ctx.state.command_op(self.read_json()))
            if path == "/run":
                return self.run_saved(self.read_json())
            if path == "/shell":
                return self.shell(self.read_json())
            if path == "/files":
                return self.files_put(q)
            if path == "/clipboard":
                text = str(self.read_json().get("text", ""))
                if not set_clipboard(text):
                    raise ApiError(501, "No clipboard tool found (install wl-clipboard or xclip)")
                _clip_state["last"] = text
                return self.send_json(200, {"ok": True})
            if path == "/notify":
                b = self.read_json()
                if FLAGS.notifications:
                    show_notification(str(b.get("app", "")), str(b.get("title", "")),
                                      str(b.get("text", b.get("body", ""))))
                return self.send_json(200, {"ok": True})
            if path == "/input":
                return self.send_json(200, do_input(self.read_json()))
            if path == "/adb/connect":
                # the phone asks the computer to connect to it with adb (its own address by default)
                b = self.read_json()
                host = str(b.get("host") or self.client_address[0])
                res = connect(host, int(b.get("port", 5555)))
                return self.send_json(200, {"ok": res.ok, "message": res.message, "hint": res.hint})
            if path == "/adb/pair":
                b = self.read_json()
                res = pair(str(b.get("address", "")), str(b.get("code", "")))
                return self.send_json(200, {"ok": res.ok, "message": res.message, "hint": res.hint})
        raise ApiError(404, "Unknown address")

    def run_saved(self, body):
        c = ctx.state.find_command(str(body.get("id", "")))
        if not c:
            raise ApiError(404, "Command not found")
        values = body.get("values") or {}
        for f in cmd_fields(c["cmd"]):
            if not str(values.get(f, "")).strip():
                raise ApiError(400, f"Value needed: {(c.get('labels') or {}).get(f, f)}")
        res = run_shell(fill_cmd(c["cmd"], values), cwd=str(Path.home()), timeout=12, keep=True)
        res.pop("cwd", None)
        if res.get("running"):
            res["output"] = res.get("output") or "Still running in the background"
        self.send_json(200, res)

    def shell(self, body):
        if not FLAGS.shell:
            raise ApiError(403, "The terminal is switched off on this computer (--no-shell)")
        cmd = str(body.get("cmd", ""))
        if not cmd.strip():
            raise ApiError(400, "Empty command")
        cwd = str(body.get("cwd") or "") or str(Path.home())
        timeout = max(1, min(int(body.get("timeout", 60)), 300))
        res = run_shell(cmd, cwd=cwd, timeout=timeout, keep=False, track_cwd=True)
        if not res.get("cwd"):
            res["cwd"] = cwd if os.path.isdir(cwd) else str(Path.home())
        self.send_json(200, res)

    # ---- files
    def files_get(self, q):
        op = q.get("op", "list")
        path = q.get("path", "")
        if op == "list":
            return self.send_json(200, op_list(path, q.get("hidden") == "1"))
        if op == "info":
            return self.send_json(200, op_info(path))
        if op == "tree":
            return self.send_json(200, op_tree(path))
        if op == "text":
            return self.send_json(200, op_text(path, int(q.get("max", 200000))))
        if op == "thumb":
            p = resolve_path(path)
            need_exists(p)
            if p.is_dir():
                raise ApiError(400, "This is a folder")
            w = max(32, min(int(q.get("w", 128)), 4000))
            if p.suffix.lower() == ".gif" and p.stat().st_size <= 8_000_000:
                return self.send_file(p)
            data = make_thumb(p, w)
            if data is None:
                if p.suffix.lower() in IMAGE_EXT and p.stat().st_size <= 3_000_000:
                    return self.send_file(p)
                raise ApiError(415, "Cannot show this picture")
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return
        if op == "get":
            p = resolve_path(path)
            need_exists(p)
            if p.is_dir():
                raise ApiError(400, "This is a folder")
            return self.send_file(p)
        raise ApiError(400, "Unknown op")

    def send_file(self, p: Path):
        try:
            size = p.stat().st_size
            f = open(p, "rb")
        except PermissionError:
            raise ApiError(403, "Permission denied")
        with f:
            start, end, status = 0, size - 1, 200
            rng = self.headers.get("Range")
            if rng:
                m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                    end = min(end, size - 1)
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    status = 206
            length = end - start + 1 if size else 0
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(262144, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def files_put(self, q):
        if q.get("op") != "put":
            raise ApiError(400, "Unknown op")
        length_h = self.headers.get("Content-Length")
        if length_h is None:
            raise ApiError(411, "Content-Length is required")
        length = int(length_h)
        name = safe_part(os.path.basename((q.get("name") or "").replace("\\", "/")))
        if not name:
            raise ApiError(400, "Missing file name")
        to = q.get("to", "")
        root = resolve_path(to) if to else storage.folder("phone")
        dest = root.joinpath(*safe_rel(q.get("dir", "")))
        try:
            if root.exists() and not root.is_dir():
                raise ApiError(400, "Destination is not a folder")
            dest.mkdir(parents=True, exist_ok=True)
            target = unique_path(dest / name)
            part = dest / f".adblink-{secrets.token_hex(4)}.part"
            got = 0
            with open(part, "wb") as out:
                while got < length:
                    chunk = self.rfile.read(min(262144, length - got))
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
        except PermissionError:
            self.close_connection = True
            raise ApiError(403, "Permission denied on the computer")
        except OSError as e:
            self.close_connection = True
            raise ApiError(500, str(e))
        if got != length:
            self.close_connection = True
            try:
                part.unlink()
            except OSError:
                pass
            raise ApiError(400, "Upload was cut off")
        self._unread = False
        os.replace(part, target)
        log("received", target)
        self.send_json(200, {"ok": True, "path": target.as_posix(), "size": got})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64
