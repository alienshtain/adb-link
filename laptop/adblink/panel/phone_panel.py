"""The phone-shaped control panel, info and notifications popovers."""
from __future__ import annotations

import re
import time
from .. import storage
from gi.repository import Adw, Gdk, GLib, Gtk, Pango
from .adbutil import adb, first_line, fmt_size
from .apps_helpers import avatar
from .phone_page import BATTERY_STATUS, STATS_SCRIPT, fmt_uptime, parse_stats
from .phone_tools import TOGGLES, parse_notifications, parse_toggles, toggles_script
from .panel_layout import ACTIONS, DEFAULT_LAYOUT, catalog, describe, exists, get_layout
from .ui import clear_children, confirm_dialog, make_icon


# ---------------------------------------------------------------- phone information (pop-up)

class PhoneInfo(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12,
                         margin_bottom=12, margin_start=12, margin_end=12, width_request=340)
        self.win, self.loading = win, False
        head = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        head.append(make_icon("battery-symbolic", 28))
        self.battery = Gtk.Label(css_classes=["title-1"])
        self.battery_detail = Gtk.Label(css_classes=["dim-label"], valign=Gtk.Align.END)
        head.append(self.battery)
        head.append(self.battery_detail)
        self.model = Gtk.Label(css_classes=["title-3"], margin_top=2)
        self.android = Gtk.Label(css_classes=["dim-label"])
        for w in (head, self.model, self.android):
            self.append(w)
        self.rows = {}
        group = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"], margin_top=6)
        for key, title, bar in (("storage", "Storage", True), ("memory", "Memory", True),
                                ("network", "Network", False), ("uptime", "Uptime", False),
                                ("screen", "Screen", False), ("build", "Build", False)):
            row = Adw.ActionRow(title=title, subtitle="-", activatable=False)
            progress = None
            if bar:
                progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=110)
                row.add_suffix(progress)
            group.append(row)
            self.rows[key] = (row, progress)
        self.append(group)
        refresh = Gtk.Button(label="Refresh", halign=Gtk.Align.CENTER, margin_top=4)
        refresh.connect("clicked", lambda _b: self.reload())
        self.append(refresh)

    def reload(self):
        if self.loading:
            return
        self.loading = True
        self.win.bg(lambda: adb("shell", STATS_SCRIPT, timeout=30), self._loaded)

    def _loaded(self, result):
        self.loading = False
        if isinstance(result, Exception):
            result = (1, "", str(result))
        rc, out, err = result
        if rc != 0 or "@@PROP" not in out:
            self.model.set_text(first_line(err or out, "No phone connected"))
            return
        self.show(parse_stats(out))

    def _set(self, key, text, fraction=None):
        row, progress = self.rows[key]
        row.set_subtitle(text or "-")
        if progress is not None and fraction is not None:
            progress.set_fraction(max(0.0, min(1.0, fraction)))

    def show(self, i):
        self.model.set_text(f"{i['maker'].capitalize()} {i['model']}".strip())
        self.android.set_text(f"Android {i['android']} (API {i['sdk']})  -  patch {i['patch']}"
                              if i["android"] else "")
        if "battery" in i:
            self.battery.set_text(f"{i['battery']}%")
            extra = [i["battery_state"] + (f" ({i['plugged']})" if i["plugged"] else "")]
            if "temp" in i:
                extra.append(f"{i['temp']:.0f} °C")
            self.battery_detail.set_text("  ".join(extra))
        if "disk_total" in i:
            self._set("storage", f"{fmt_size(i['disk_used'])} of {fmt_size(i['disk_total'])}",
                      i["disk_used"] / i["disk_total"])
        if "mem_total" in i:
            self._set("memory", f"{fmt_size(i['mem_used'])} of {fmt_size(i['mem_total'])}",
                      i["mem_used"] / i["mem_total"])
        if "uptime" in i:
            self._set("uptime", fmt_uptime(i["uptime"]))
        self._set("network", "\n".join(i["ips"]) if i["ips"] else "No IP address")
        self._set("screen", i["screen"])
        self._set("build", i["build"] or i["abi"])


# ---------------------------------------------------------------- notifications + quick settings (pop-up)

class NotificationsPanel(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12,
                         margin_bottom=12, margin_start=12, margin_end=12, width_request=360)
        self.win, self.loading, self.syncing, self.buttons = win, False, False, {}
        self.append(Gtk.Label(label="Quick settings", xalign=0, css_classes=["heading"]))
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, row_spacing=6,
                           column_spacing=6, min_children_per_line=2, max_children_per_line=3)
        for t in TOGGLES:
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=4, margin_bottom=4)
            icon = make_icon(t["icon"], 22)
            icon.set_halign(Gtk.Align.CENTER)
            content.append(icon)
            content.append(Gtk.Label(label=t["title"], css_classes=["caption"], wrap=True,
                                     justify=Gtk.Justification.CENTER, max_width_chars=12))
            btn = Gtk.ToggleButton(css_classes=["toggle-tile"])
            btn.set_child(content)
            btn.connect("toggled", self._toggled, t)
            self.buttons[t["key"]] = btn
            flow.append(btn)
        self.append(flow)
        head = Gtk.Box(spacing=6, margin_top=8)
        head.append(Gtk.Label(label="Notifications", xalign=0, hexpand=True, css_classes=["heading"]))
        shade = Gtk.Button(label="Open on phone", css_classes=["flat"])
        shade.connect("clicked", lambda _b: win.run_phone("cmd statusbar expand-notifications"))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", css_classes=["flat"], tooltip_text="Refresh")
        refresh.connect("clicked", lambda _b: self.reload())
        head.append(shade)
        head.append(refresh)
        self.append(head)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self.empty = Gtk.Label(label="No notifications", css_classes=["dim-label"], margin_top=14, margin_bottom=14)
        self.listbox.set_placeholder(self.empty)
        scroller = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=330,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self.listbox)
        self.append(scroller)

    def reload(self):
        if self.loading:
            return
        self.loading = True
        script = toggles_script() + "; echo @@NOTIF; dumpsys notification --noredact | head -n 5000"
        self.win.bg(lambda: adb("shell", script, timeout=40), self._loaded)

    def _loaded(self, result):
        self.loading = False
        if isinstance(result, Exception):
            result = (1, "", str(result))
        rc, out, err = result
        if rc != 0 or "@@" not in out:
            self.empty.set_text(first_line(err or out, "No phone connected"))
            clear_children(self.listbox)
            return
        head, _, notes = out.partition("@@NOTIF")
        self.syncing = True
        for key, on in parse_toggles(head).items():
            self.buttons[key].set_active(on)
        self.syncing = False
        clear_children(self.listbox)
        self.empty.set_text("No notifications")
        for n in parse_notifications(notes):
            row = Adw.ActionRow(title=GLib.markup_escape_text(n["title"] or n["app"]),
                                subtitle=GLib.markup_escape_text(n["text"]), activatable=False)
            row.set_subtitle_lines(2)
            row.add_prefix(avatar(n["app"], 34))
            row.add_suffix(Gtk.Label(label=n["app"], css_classes=["badge"], valign=Gtk.Align.CENTER))
            self.listbox.append(row)

    def _toggled(self, button, toggle):
        if self.syncing:
            return
        def finished():
            self.loading = False
            self.reload()
        _flip(self.win, toggle["key"], finished)


# ---------------------------------------------------------------- phone panel (right side of the window)

class AddActionWindow(Gtk.Window):
    """Pick what to put on the phone panel: phone buttons, quick settings, pages or your own commands."""

    def __init__(self, win, panel):
        super().__init__(title="Add to the phone panel", transient_for=win, modal=True,
                         default_width=420, default_height=560)
        self.win, self.panel = win, panel
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                      margin_start=12, margin_end=12)
        self.set_child(box)
        self.search = Gtk.SearchEntry(placeholder_text="Search")
        self.search.connect("search-changed", lambda *_: self._filter())
        box.append(self.search)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroller.set_child(self.content)
        box.append(scroller)
        done = Gtk.Button(label="Done", css_classes=["suggested-action"], halign=Gtk.Align.END)
        done.connect("clicked", lambda _b: self.close())
        box.append(done)
        self.rows = []
        have = set(panel.layout)
        for title, keys in catalog(win):
            group = Adw.PreferencesGroup(title=title)
            any_row = False
            for key in keys:
                icon, name, _short = describe(key, win)
                row = Adw.ActionRow(title=GLib.markup_escape_text(name), activatable=True)
                row.add_prefix(make_icon(icon, 20))
                mark = Gtk.Image(icon_name="object-select-symbolic" if key in have else "list-add-symbolic")
                row.add_suffix(mark)
                row.connect("activated", self._add, key, mark)
                group.add(row)
                self.rows.append((row, name.lower()))
                any_row = True
            if any_row:
                self.content.append(group)
            self.rows.append((group, ""))

    def _filter(self):
        q = self.search.get_text().strip().lower()
        for row, name in self.rows:
            if name:
                row.set_visible(not q or q in name)

    def _add(self, _row, key, mark):
        if self.panel.add(key):
            mark.set_from_icon_name("object-select-symbolic")
        else:
            self.win.toast("The panel is full (24 buttons)")


class PhonePanel(Gtk.Box):
    """The phone drawn on the right of the window: status bar, a grid of shortcuts you arrange yourself,
    the three navigation keys at the bottom and the power / volume keys on its side."""

    COLUMNS = 4
    MAX_ITEMS = 24

    def __init__(self, win):
        super().__init__(spacing=6, margin_top=8, margin_bottom=10, margin_start=6, margin_end=12)
        self.win, self.editing = win, False
        self.layout = get_layout(win.settings, win)
        self.set_size_request(300, -1)
        phone = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True,
                        css_classes=["phone-body"])

        # status bar: info icon, name + battery, edit pencil, notifications icon
        bar = Gtk.Box(spacing=2)
        self.info = PhoneInfo(win)
        info_pop = Gtk.Popover()
        info_pop.set_child(self.info)
        info_pop.connect("show", lambda *_: self.info.reload())
        info_btn = Gtk.MenuButton(icon_name="dialog-information-symbolic", popover=info_pop,
                                  css_classes=["flat", "circular"], tooltip_text="Phone information")
        self.notes = NotificationsPanel(win)
        notes_pop = Gtk.Popover()
        notes_pop.set_child(self.notes)
        notes_pop.connect("show", lambda *_: self.notes.reload())
        notes_btn = Gtk.MenuButton(icon_name="preferences-system-notifications-symbolic", popover=notes_pop,
                                   css_classes=["flat", "circular"],
                                   tooltip_text="Notifications and quick settings")
        self.edit_btn = Gtk.ToggleButton(icon_name="document-edit-symbolic", css_classes=["flat", "circular"],
                                         tooltip_text="Arrange the buttons")
        self.edit_btn.connect("toggled", lambda b: self.set_editing(b.get_active()))
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        self.title = Gtk.Label(label="No phone", css_classes=["heading"], ellipsize=Pango.EllipsizeMode.END)
        self.battery = Gtk.Label(css_classes=["dim-label", "caption"])
        middle.append(self.title)
        middle.append(self.battery)
        for w in (info_btn, middle, self.edit_btn, notes_btn):
            bar.append(w)
        phone.append(bar)

        self.hint = Gtk.Label(label="Drag a button to move it, or use the arrows. Press + to add more.",
                              wrap=True, css_classes=["dim-label", "caption"], visible=False)
        phone.append(self.hint)
        self.grid = Gtk.Grid(column_spacing=6, row_spacing=8, halign=Gtk.Align.CENTER, margin_top=2)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=False)
        scroller.set_child(self.grid)
        phone.append(scroller)
        self.edit_bar = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, visible=False)
        reset = Gtk.Button(label="Reset")
        reset.connect("clicked", lambda _b: self.reset())
        done = Gtk.Button(label="Done", css_classes=["suggested-action"])
        done.connect("clicked", lambda _b: self.edit_btn.set_active(False))
        self.edit_bar.append(reset)
        self.edit_bar.append(done)
        phone.append(self.edit_bar)

        nav = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER, margin_top=4)
        for key in ("back", "home", "recents"):
            icon, tip, _short = describe(key)
            btn = Gtk.Button(css_classes=["circular", "phone-nav"], tooltip_text=tip)
            btn.set_size_request(46, 46)
            btn.set_child(make_icon(icon, 20))
            btn.connect("clicked", lambda _b, k=key: self.run(k))
            nav.append(btn)
        phone.append(nav)
        self.append(phone)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.START, margin_top=96)
        for key, css in (("volup", []), ("voldown", []), ("power", ["destructive-action"])):
            icon, tip, _short = describe(key)
            btn = Gtk.Button(css_classes=["phone-sidekey", *css], tooltip_text=tip)
            btn.set_child(make_icon(icon, 16))
            btn.connect("clicked", lambda _b, k=key: self.run(k))
            side.append(btn)
        self.append(side)
        self.rebuild()
        GLib.timeout_add_seconds(30, self._timer)

    # ---- the arrangement
    def save(self):
        self.win.settings["panel_layout"] = list(self.layout)
        self.win.save()

    def add(self, key):
        if len(self.layout) >= self.MAX_ITEMS:
            return False
        if key not in self.layout:
            self.layout.append(key)
            self.save()
            self.rebuild()
        return True

    def remove(self, index):
        if 0 <= index < len(self.layout):
            del self.layout[index]
            self.save()
            self.rebuild()

    def move(self, src, dst):
        if src == dst or not (0 <= src < len(self.layout)) or not (0 <= dst < len(self.layout)):
            return
        self.layout.insert(dst, self.layout.pop(src))
        self.save()
        self.rebuild()

    def reset(self):
        self.layout = list(DEFAULT_LAYOUT)
        self.win.settings.pop("panel_layout", None)
        self.win.save()
        self.rebuild()

    def set_editing(self, on):
        self.editing = on
        self.hint.set_visible(on)
        self.edit_bar.set_visible(on)
        self.rebuild()

    def rebuild(self):
        clear_children(self.grid)
        self.layout = [k for k in self.layout if exists(k, self.win)]
        for i, key in enumerate(self.layout):
            self.grid.attach(self._tile(i, key), i % self.COLUMNS, i // self.COLUMNS, 1, 1)
        if self.editing and len(self.layout) < self.MAX_ITEMS:
            i = len(self.layout)
            add = Gtk.Button(css_classes=["circular", "phone-app", "suggested-action"], tooltip_text="Add a button",
                             halign=Gtk.Align.CENTER)
            add.set_size_request(46, 46)
            add.set_child(make_icon("list-add-symbolic", 20))
            add.connect("clicked", lambda _b: AddActionWindow(self.win, self).present())
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, width_request=62)
            box.append(add)
            box.append(Gtk.Label(label="Add", css_classes=["caption"]))
            self.grid.attach(box, i % self.COLUMNS, i // self.COLUMNS, 1, 1)

    def _tile(self, index, key):
        icon, tip, short = describe(key, self.win)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, width_request=62, halign=Gtk.Align.CENTER)
        btn = Gtk.Button(css_classes=["circular", "phone-app"], tooltip_text=tip, halign=Gtk.Align.CENTER)
        btn.set_size_request(46, 46)
        btn.set_child(make_icon(icon, 20))
        label = Gtk.Label(label=short, css_classes=["caption"], ellipsize=Pango.EllipsizeMode.END, max_width_chars=9)
        box.append(btn)
        box.append(label)
        if not self.editing:
            btn.connect("clicked", lambda _b, k=key: self.run(k))
            return box
        # editing: remove button on the corner, arrows below, drag to move
        btn.set_sensitive(True)
        arrows = Gtk.Box(spacing=0, halign=Gtk.Align.CENTER)
        left = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["flat", "circular", "tiny"],
                          tooltip_text="Move earlier")
        left.connect("clicked", lambda _b, i=index: self.move(i, i - 1))
        right = Gtk.Button(icon_name="go-next-symbolic", css_classes=["flat", "circular", "tiny"],
                           tooltip_text="Move later")
        right.connect("clicked", lambda _b, i=index: self.move(i, i + 1))
        arrows.append(left)
        arrows.append(right)
        box.append(arrows)
        overlay = Gtk.Overlay()
        overlay.set_child(box)
        rm = Gtk.Button(icon_name="window-close-symbolic", css_classes=["circular", "destructive-action", "tiny"],
                        halign=Gtk.Align.END, valign=Gtk.Align.START, tooltip_text="Remove from the panel")
        rm.connect("clicked", lambda _b, i=index: self.remove(i))
        overlay.add_overlay(rm)
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect("prepare", lambda _s, _x, _y, i=index: Gdk.ContentProvider.new_for_value(str(i)))
        btn.add_controller(source)
        target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)
        target.connect("drop", lambda _t, value, _x, _y, i=index: (self.move(int(value), i), True)[1])
        overlay.add_controller(target)
        return overlay

    # ---- running a button
    def run(self, key):
        run_action(self.win, key)

    # ---- phone name + battery in the status bar
    def _timer(self):
        if self.get_mapped() and self.win._serial:
            self.refresh()
        return True

    def refresh(self):
        script = "getprop ro.product.model; dumpsys battery | grep -E 'level|status'"
        self.win.bg(lambda: adb("shell", script, timeout=15), self._refreshed)

    def _refreshed(self, res):
        if isinstance(res, Exception) or res[0] != 0:
            self.title.set_text("No phone")
            self.battery.set_text("")
            return
        lines = res[1].splitlines()
        self.title.set_text(lines[0].strip() if lines else "Phone")
        level = re.search(r"level:\s*(\d+)", res[1])
        status = re.search(r"status:\s*(\d+)", res[1])
        if level:
            state = BATTERY_STATUS.get(status.group(1), "") if status else ""
            self.battery.set_text(f"{level.group(1)}%  {state}".strip())


def run_action(win, key):
    """Do what a panel button says."""
    if key.startswith("toggle:"):
        return _flip(win, key[7:])
    if key.startswith("page:"):
        win.show_page(key[5:])
        return None
    if key.startswith("cmd:"):
        for c in win.commands:
            if c["id"] == key[4:]:
                return win.commands_page.on_run(c)
        return None
    icon, tip, short, kind, arg = ACTIONS[key]
    if kind == "shell":
        win.run_phone(arg, tip)
    elif kind == "confirm-shell":
        confirm_dialog(win, f"{tip}?", "The phone will restart.", "Restart", lambda: win.run_phone(arg, tip))
    elif kind == "scrcpy":
        win.phone.start_scrcpy([])
    elif kind == "bright":
        _brightness(win, 1 if arg == "+" else -1)
    elif kind == "shot":
        _screenshot(win)
    return None


def _flip(win, key, on_done=None):
    toggle = next(t for t in TOGGLES if t["key"] == key)

    def work():
        rc, out, err = adb("shell", toggles_script(), timeout=20)
        if rc != 0:
            raise RuntimeError(first_line(out + err))
        was_on = parse_toggles(out).get(key, False)
        want = not was_on
        rc, out, err = adb("shell", toggle["off"] if was_on else toggle["on"], timeout=20)
        if rc != 0:
            return toggle["title"], want, False, first_line(out + err)
        time.sleep(1.5)                       # let the phone apply it, then check what really happened
        rc, out, err = adb("shell", toggles_script(), timeout=20)
        now = parse_toggles(out).get(key, want) if rc == 0 else want
        if now != want and key == "bluetooth" and want:
            # some phones refuse "svc bluetooth": ask with the system's own dialog instead
            adb("shell", "am start -a android.bluetooth.adapter.action.REQUEST_ENABLE", timeout=15)
            return toggle["title"], want, False, "Confirm on the phone screen"
        return toggle["title"], want, now == want, "" if now == want else "The phone did not allow this change"

    def done(res):
        if isinstance(res, Exception):
            win.toast(f"{toggle['title']}: {res}")
            if on_done:
                on_done()
            return
        title, want, ok, note = res
        win.toast(f"{title}: {'on' if want else 'off'}" if ok else f"{title}: {note}")
        if on_done:
            on_done()
    win.bg(work, done)


def _brightness(win, direction):
    """Brightness up / down by 10 percent of whatever scale this phone uses (255, 1023, 2047 ...)."""
    def work():
        rc, out, err = adb("shell", "dumpsys power | grep -E 'mScreenBrightnessSetting(Minimum|Maximum)'; "
                                    "echo CUR=$(settings get system screen_brightness)", timeout=20)
        if rc != 0:
            raise RuntimeError(first_line(out + err))
        top = re.search(r"mScreenBrightnessSettingMaximum=(\d+)", out)
        low = re.search(r"mScreenBrightnessSettingMinimum=(\d+)", out)
        cur = re.search(r"CUR=(\d+)", out)
        top = int(top.group(1)) if top else 255
        low = max(1, int(low.group(1))) if low else 1
        cur = int(cur.group(1)) if cur else top // 2
        new = min(top, max(low, cur + direction * max(1, round(top / 10))))
        adb("shell", f"settings put system screen_brightness_mode 0; settings put system screen_brightness {new}",
            timeout=20)
        rc, out, _e = adb("shell", "settings get system screen_brightness", timeout=15)
        if rc == 0 and out.strip() != str(new):      # the phone ignored the value: use the brightness keys
            adb("shell", "input keyevent " + ("221" if direction > 0 else "220"), timeout=15)
        return round(new * 100 / top)

    def done(res):
        win.toast(str(res) if isinstance(res, Exception) else f"Brightness {res}%")
    win.bg(work, done)


def _screenshot(win):
    def work():
        rc, out, err = adb("exec-out", "screencap", "-p", timeout=30, binary=True)
        if rc != 0 or not out:
            raise RuntimeError(first_line(err.decode("utf-8", "replace") if isinstance(err, bytes) else err,
                                          "screenshot failed"))
        target = storage.folder("shots") / time.strftime("adb-screenshot-%Y%m%d-%H%M%S.png")
        target.write_bytes(out)
        return target

    def done(res):
        win.toast(f"Screenshot: {res}" if isinstance(res, Exception) else f"Saved {res}")
    win.bg(work, done)
