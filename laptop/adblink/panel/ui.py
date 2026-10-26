"""Shared GTK helpers: CSS, dialogs, icons."""
from __future__ import annotations

from . import compat
from gi.repository import Adw, GLib, Gdk, Gtk
from .commanddata import ICON_CHOICES, NUMERIC, field_info


def clear_children(widget):
    if hasattr(widget, "remove_all"):  # ListBox / FlowBox (GTK 4.12+): keeps the placeholder
        widget.remove_all()
        return
    child = widget.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        widget.remove(child)
        child = nxt


def make_icon(name, px=24):
    """A theme icon, or (for emoji / unknown names) a text glyph of the same size."""
    name = (name or "").strip()
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    if name and theme.has_icon(name):
        img = Gtk.Image.new_from_icon_name(name)
        img.set_pixel_size(px)
        return img
    text = name[:2] if any(ord(c) > 127 for c in name) else "•"
    lbl = Gtk.Label()
    lbl.set_markup(f'<span size="{int(px * 0.72 * 1024)}">{GLib.markup_escape_text(text)}</span>')
    lbl.set_size_request(px, px)
    return lbl


CSS = """
.avatar { border-radius: 10px; color: white; font-weight: bold; }
.av0 { background: #3584e4; } .av1 { background: #26a269; } .av2 { background: #c64600; }
.av3 { background: #9141ac; } .av4 { background: #a51d2d; } .av5 { background: #986a44; }
.av6 { background: #1a5fb4; } .av7 { background: #5e5c64; }
.tile { padding: 12px; }
.badge { border-radius: 8px; padding: 0 6px; font-size: 0.8em; background: alpha(currentColor, 0.12); }
.badge-warn { background: alpha(#e5a50a, 0.35); }
.badge-bad { background: alpha(#e01b24, 0.30); }
.big-avatar { border-radius: 44px; font-size: 38px; }
.call-bar { background: #26a269; color: white; padding: 6px 12px; }
.call-answer { background: #26a269; color: white; }
.call-reject { background: #e01b24; color: white; }
.phone-body { border: 3px solid alpha(currentColor, 0.35); border-radius: 34px; padding: 14px 12px;
              background: alpha(currentColor, 0.04); }
.phone-sidekey { border-radius: 10px; min-width: 14px; min-height: 36px; padding: 4px 6px; }
.toggle-tile { border-radius: 14px; padding: 4px 6px; }
.tiny { min-width: 18px; min-height: 18px; padding: 0; }
.phone-app { background: alpha(@accent_bg_color, 0.18); }
.phone-nav { background: alpha(currentColor, 0.08); }
.info-bar { background: alpha(@warning_bg_color, 0.25); padding: 6px 12px; }
.toggle-tile:checked { background: @accent_bg_color; color: @accent_fg_color; }
"""


def install_css():
    provider = Gtk.CssProvider()
    if hasattr(provider, "load_from_string"):
        provider.load_from_string(CSS)
    else:
        provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


# ---------------------------------------------------------------- dialogs

def confirm_dialog(parent, message, detail, ok_label, on_ok):
    compat.confirm(parent, message, detail, ok_label, on_ok)


def close_on_escape(window):
    ctl = Gtk.EventControllerKey()
    ctl.connect("key-pressed", lambda _c, keyval, *_a: window.close() or True
                if keyval == Gdk.KEY_Escape else False)
    window.add_controller(ctl)


def choose_path(parent, kind, on_path):
    """kind: 'file' or 'folder'. Calls on_path(str)."""
    compat.pick(parent, kind, lambda paths: on_path(paths[0]))


class PromptWindow(Gtk.Window):
    """Asks for the values a command needs (package name, IP, file...)."""

    def __init__(self, parent, title, description, keys, saved, on_done):
        super().__init__(transient_for=parent, modal=True, title=title,
                         default_width=500, resizable=False)
        self.on_done = on_done
        self.entries = {}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.set_child(box)
        if description:
            box.append(Gtk.Label(label=description, xalign=0, wrap=True,
                                 css_classes=["dim-label"]))
        grid = Gtk.Grid(row_spacing=10, column_spacing=12)
        box.append(grid)
        for row, key in enumerate(keys):
            label, default, kind = field_info(key)
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            entry = Gtk.Entry(hexpand=True, width_chars=28, activates_default=True)
            entry.set_text(saved.get(key) or default)
            entry.connect("changed", lambda e: e.remove_css_class("error"))
            self.entries[key] = entry
            grid.attach(entry, 1, row, 1, 1)
            if kind in ("file", "folder"):
                browse = Gtk.Button(label="Browse...")
                browse.connect("clicked", lambda _b, e=entry, k=kind:
                               choose_path(self, k, e.set_text))
                grid.attach(browse, 2, row, 1, 1)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        run = Gtk.Button(label="Run", css_classes=["suggested-action"])
        run.connect("clicked", self._submit)
        buttons.append(cancel)
        buttons.append(run)
        box.append(buttons)
        self.set_default_widget(run)
        close_on_escape(self)

    def _submit(self, _button):
        values, ok = {}, True
        for key, entry in self.entries.items():
            value = entry.get_text().strip()
            bad = not value or (key in NUMERIC and not value.isdigit())
            if key == "seconds" and value.isdigit() and not 1 <= int(value) <= 180:
                bad = True
            if bad:
                entry.add_css_class("error")
                ok = False
            values[key] = value
        if ok:
            self.close()
            self.on_done(values)


class IconField(Gtk.Box):
    """Preview + text entry (icon name or emoji) + a picker with common icons."""

    def __init__(self, value):
        super().__init__(spacing=8)
        self.preview = Gtk.Box()
        self.entry = Gtk.Entry(hexpand=True, placeholder_text="icon name, or paste an emoji")
        self.entry.connect("changed", lambda *_a: self._update())
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=6, max_children_per_line=8)
        popover = Gtk.Popover()
        for name in ICON_CHOICES:
            if theme.has_icon(name):
                btn = Gtk.Button(css_classes=["flat"], tooltip_text=name)
                btn.set_child(make_icon(name, 20))
                btn.connect("clicked", lambda _b, n=name: (self.entry.set_text(n), popover.popdown()))
                flow.append(btn)
        scroller = Gtk.ScrolledWindow(min_content_width=340, min_content_height=240)
        scroller.set_child(flow)
        popover.set_child(scroller)
        picker = Gtk.MenuButton(label="Choose", popover=popover)
        for w in (self.preview, self.entry, picker):
            self.append(w)
        self.entry.set_text(value or "")
        self._update()

    def _update(self):
        clear_children(self.preview)
        self.preview.append(make_icon(self.entry.get_text(), 24))

    def get_text(self):
        return self.entry.get_text().strip()


def button_content(icon, label, css=None):
    btn = Gtk.Button(css_classes=css or [])
    btn.set_child(compat.content(icon, label))
    return btn


class InfoBar(Gtk.Revealer):
    """A thin bar under the title: a message, an optional action button and a close button."""

    def __init__(self):
        super().__init__(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        box = Gtk.Box(spacing=8, css_classes=["info-bar"])
        self.label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.button = Gtk.Button(valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        self.button.connect("clicked", lambda _b: self._action and self._action())
        close = Gtk.Button(icon_name="window-close-symbolic", css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
        close.connect("clicked", lambda _b: self.set_reveal_child(False))
        for w in (self.label, self.button, close):
            box.append(w)
        self.set_child(box)
        self._action = None

    def show_msg(self, text, label="", action=None):
        self.label.set_text(text)
        self._action = action
        self.button.set_visible(bool(label))
        self.button.set_label(label)
        self.set_reveal_child(True)

    def hide_bar(self):
        self.set_reveal_child(False)
