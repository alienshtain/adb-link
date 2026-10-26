"""Saved commands, paired phones and the pairing code."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import threading
import time
from .common import ApiError, IS_MAC, IS_WIN, state_dir


def C(id_, name, icon, color, confirm, cmd, labels=None):
    return {"id": id_, "name": name, "icon": icon, "color": color, "confirm": confirm, "cmd": cmd,
            "labels": labels or {}}


def default_commands():
    if IS_MAC:
        return [
            C("lock", "Lock", "lock", "#3584E4", False, "pmset displaysleepnow"),
            C("sleep", "Sleep", "bedtime", "#5E5CE6", True, "pmset sleepnow"),
            C("shutdown", "Shut down", "power_settings_new", "#E5484D", True,
              "osascript -e 'tell app \"System Events\" to shut down'"),
            C("vol_up", "Volume up", "volume_up", "#30A46C", False,
              "osascript -e 'set volume output volume ((output volume of (get volume settings)) + 6)'"),
            C("vol_down", "Volume down", "volume_down", "#30A46C", False,
              "osascript -e 'set volume output volume ((output volume of (get volume settings)) - 6)'"),
            C("url", "Open link", "link", "#0091FF", False, "open {url}", {"url": "Link"}),
        ]
    if IS_WIN:
        return [
            C("lock", "Lock", "lock", "#3584E4", False, "rundll32.exe user32.dll,LockWorkStation"),
            C("sleep", "Sleep", "bedtime", "#5E5CE6", True,
              "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"),
            C("shutdown", "Shut down", "power_settings_new", "#E5484D", True, "shutdown /s /t 5"),
            C("reboot", "Restart", "restart_alt", "#F76B15", True, "shutdown /r /t 5"),
            C("url", "Open link", "link", "#0091FF", False, "start \"\" {url}", {"url": "Link"}),
        ]
    return [
        C("lock", "Lock", "lock", "#3584E4", False,
          "loginctl lock-session || xdg-screensaver lock || gnome-screensaver-command -l || "
          "cinnamon-screensaver-command -l || xflock4 || dm-tool lock"),
        C("sleep", "Sleep", "bedtime", "#5E5CE6", True, "systemctl suspend"),
        C("shutdown", "Shut down", "power_settings_new", "#E5484D", True, "systemctl poweroff"),
        C("reboot", "Restart", "restart_alt", "#F76B15", True, "systemctl reboot"),
        C("vol_up", "Volume up", "volume_up", "#30A46C", False,
          "pactl set-sink-volume @DEFAULT_SINK@ +5% || amixer -q set Master 5%+"),
        C("vol_down", "Volume down", "volume_down", "#30A46C", False,
          "pactl set-sink-volume @DEFAULT_SINK@ -5% || amixer -q set Master 5%-"),
        C("mute", "Mute", "volume_off", "#8E4EC6", False,
          "pactl set-sink-mute @DEFAULT_SINK@ toggle || amixer -q set Master toggle"),
        C("play", "Play / pause", "play_arrow", "#12A594", False, "playerctl play-pause"),
        C("next", "Next", "skip_next", "#12A594", False, "playerctl next"),
        C("prev", "Previous", "skip_previous", "#12A594", False, "playerctl previous"),
        C("url", "Open link", "link", "#0091FF", False, "xdg-open {url}", {"url": "Link"}),
    ]


PLACEHOLDER = re.compile(r"(?<!\$)\{([A-Za-z_][A-Za-z0-9_]*)\}")


def cmd_fields(cmd: str):
    """Names written as {name} in a command become input fields. {{ and }} are literal braces."""
    seen = []
    for m in PLACEHOLDER.finditer(cmd.replace("{{", "").replace("}}", "")):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fill_cmd(cmd: str, values: dict):
    def quote(v):
        v = str(v)
        if IS_WIN:
            return '"' + v.replace('"', '\\"') + '"'
        return shlex.quote(v)

    s = cmd.replace("{{", "\x00L").replace("}}", "\x00R")
    s = PLACEHOLDER.sub(lambda m: quote(values.get(m.group(1), "")), s)
    return s.replace("\x00L", "{").replace("\x00R", "}")


class State:
    def __init__(self):
        self.dir = state_dir()
        self.path = self.dir / "state.json"
        self.lock = threading.RLock()
        self.data = {"tokens": {}, "commands": None}
        try:
            self.data.update(json.loads(self.path.read_text("utf-8")))
        except (OSError, ValueError):
            pass
        if not isinstance(self.data.get("commands"), list):
            self.data["commands"] = default_commands()
            self.save()

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def add_token(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.data["tokens"][self._hash(token)] = {"name": name[:60], "created": int(time.time())}
            self.save()
        return token

    def check_token(self, token: str) -> bool:
        with self.lock:
            return self._hash(token) in self.data["tokens"]

    def token_name(self, token: str):
        """Name of the phone that owns this token, or None."""
        with self.lock:
            rec = self.data["tokens"].get(self._hash(token))
            return rec.get("name", "Phone") if rec else None

    def phones(self):
        with self.lock:
            return [dict(v) for v in self.data["tokens"].values()]

    def has_tokens(self) -> bool:
        return bool(self.data["tokens"])

    def reset_tokens(self):
        with self.lock:
            self.data["tokens"] = {}
            self.save()

    # ---- commands
    def commands_out(self):
        out = []
        with self.lock:
            for c in self.data["commands"]:
                fields = cmd_fields(c.get("cmd", ""))
                labels = {f: (c.get("labels") or {}).get(f, f) for f in fields}
                out.append({
                    "id": c["id"], "name": c.get("name", ""), "icon": c.get("icon", ""),
                    "color": c.get("color", ""), "confirm": bool(c.get("confirm")),
                    "cmd": c.get("cmd", ""), "fields": fields, "labels": labels,
                })
        return out

    def find_command(self, cid):
        with self.lock:
            for c in self.data["commands"]:
                if c["id"] == cid:
                    return dict(c)
        return None

    def command_op(self, body: dict):
        op = body.get("op")
        with self.lock:
            cmds = self.data["commands"]
            if op == "save":
                c = body.get("command") or {}
                name = str(c.get("name", "")).strip()
                cmd = str(c.get("cmd", "")).strip()
                if not name or len(name) > 60:
                    raise ApiError(400, "Name is required (max 60 characters)")
                if not cmd or len(cmd) > 4000:
                    raise ApiError(400, "Command is required")
                color = str(c.get("color", "") or "")
                if color and not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                    raise ApiError(400, "Bad color")
                item = {"id": str(c.get("id") or secrets.token_hex(4)), "name": name,
                        "icon": str(c.get("icon", ""))[:40], "color": color,
                        "confirm": bool(c.get("confirm")), "cmd": cmd,
                        "labels": {str(k)[:40]: str(v)[:60] for k, v in (c.get("labels") or {}).items()}}
                for i, old in enumerate(cmds):
                    if old["id"] == item["id"]:
                        cmds[i] = item
                        break
                else:
                    cmds.append(item)
            elif op == "delete":
                cmds[:] = [c for c in cmds if c["id"] != body.get("id")]
            elif op == "order":
                ids = [str(i) for i in (body.get("ids") or [])]
                by_id = {c["id"]: c for c in cmds}
                new = [by_id[i] for i in ids if i in by_id]
                new += [c for c in cmds if c["id"] not in ids]
                cmds[:] = new
            elif op == "reset":
                cmds[:] = default_commands()
            else:
                raise ApiError(400, "Unknown op")
            self.save()
        return self.commands_out()


class Pairing:
    """A 6 digit code; wrong guesses are limited so it cannot be brute-forced."""

    def __init__(self, state: State):
        self.state = state
        self.lock = threading.Lock()
        self.fails = 0
        self.locked_until = 0.0
        self.code = ""
        self.new_code()

    def new_code(self):
        self.code = f"{secrets.randbelow(10 ** 6):06d}"
        try:
            p = self.state.dir / "pair-code"
            p.write_text(self.code, "utf-8")
            os.chmod(p, 0o600)
        except OSError:
            pass

    def try_code(self, code: str) -> bool:
        with self.lock:
            now = time.time()
            if now < self.locked_until:
                raise ApiError(429, "Too many wrong codes, wait a minute")
            if hmac.compare_digest(str(code).strip(), self.code):
                self.fails = 0
                self.new_code()
                return True
            self.fails += 1
            if self.fails >= 5:
                self.fails = 0
                self.locked_until = now + 60
                self.new_code()
            return False
