"""Languages. English is the source text; Arabic is looked up in i18n_ar.

``tr("Some text")`` returns the Arabic text when the language is Arabic, otherwise the text itself.
Messages that contain numbers or names are matched with patterns (see i18n_ar.PATTERNS).
``install_gtk()`` makes every label, title, tooltip... in the window go through ``tr`` by itself.
"""
from __future__ import annotations

import json
import locale
import os
import re

from .paths import config_dir

LANGUAGES = {"auto": "Automatic", "en": "English", "ar": "العربية"}
_state = {"lang": None, "patterns": None}


def _chosen():
    try:
        data = json.loads((config_dir() / "panel.json").read_text())
        return str((data.get("prefs") or {}).get("language") or "auto")
    except (OSError, ValueError, AttributeError):
        return "auto"


def language():
    """'en' or 'ar'."""
    if _state["lang"] is None:
        choice = os.environ.get("ADBLINK_LANG") or _chosen()
        if choice not in ("en", "ar"):
            try:
                loc = locale.getlocale()[0] or os.environ.get("LANG", "")
            except ValueError:
                loc = os.environ.get("LANG", "")
            choice = "ar" if str(loc).lower().startswith("ar") else "en"
        _state["lang"] = choice
    return _state["lang"]


def set_language(code):
    _state["lang"] = None
    os.environ.pop("ADBLINK_LANG", None)
    return code


def is_rtl():
    return language() == "ar"


def _patterns():
    if _state["patterns"] is None:
        from .i18n_ar import PATTERNS
        _state["patterns"] = [(re.compile(p, re.S), t) for p, t in PATTERNS]
    return _state["patterns"]


def tr(text, *args):
    """Translate. Extra args fill {0}, {1} ... in the result."""
    if not isinstance(text, str) or not text or language() != "ar":
        return text.format(*args) if args and isinstance(text, str) else text
    from .i18n_ar import AR
    out = AR.get(text)
    if out is None:
        stripped = text.strip()
        if stripped != text and stripped in AR:
            out = text.replace(stripped, AR[stripped])
    if out is None:
        for rx, template in _patterns():
            m = rx.match(text)
            if m:
                out = template.format(*[tr(g) if g else g for g in m.groups()])
                break
    if out is None:
        out = text
    return out.format(*args) if args else out


# ---------------------------------------------------------------- make the whole window use tr()

_CTOR_KEYS = ("label", "title", "subtitle", "description", "tooltip_text", "placeholder_text", "body", "heading")


def install_gtk():
    """Wrap the GTK / libadwaita constructors and setters so every visible text is translated."""
    from gi.repository import Adw, Gio, GObject, Gtk
    if getattr(Gtk, "_adblink_i18n", False):
        return
    Gtk._adblink_i18n = True

    if is_rtl():
        Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
    if language() != "ar":
        return

    orig_init = GObject.Object.__init__

    def init(self, *a, **kw):
        for key in _CTOR_KEYS:
            if isinstance(kw.get(key), str):
                kw[key] = tr(kw[key])
        orig_init(self, *a, **kw)
    GObject.Object.__init__ = init

    def wrap(cls, name, index=0):
        orig = getattr(cls, name, None)
        if orig is None:
            return

        def setter(self, *a, **kw):
            if len(a) > index and isinstance(a[index], str):
                a = (*a[:index], tr(a[index]), *a[index + 1:])
            return orig(self, *a, **kw)
        setattr(cls, name, setter)

    for cls, names in (
            (Gtk.Label, ("set_text", "set_label")),
            (Gtk.Button, ("set_label",)),
            (Gtk.Widget, ("set_tooltip_text",)),
            (Gtk.Window, ("set_title",)),
            (Gtk.Editable, ("set_placeholder_text",)),
            (Adw.PreferencesGroup, ("set_title", "set_description")),
            (Adw.PreferencesRow, ("set_title",)),
            (Adw.ActionRow, ("set_subtitle",)),
            (Adw.StatusPage, ("set_title", "set_description")),
    ):
        for n in names:
            wrap(cls, n)
    wrap(Adw.ViewStack, "add_titled", 2)
    wrap(Adw.ViewStack, "add_titled_with_icon", 2)
    wrap(Adw.ViewStackPage, "set_title")
    wrap(Gio.Menu, "append", 0)
    wrap(Gio.Notification, "set_title")
    wrap(Gio.Notification, "set_body")
    orig_strings = Gtk.DropDown.new_from_strings

    def new_from_strings(strings):
        return orig_strings([tr(x) for x in strings])
    Gtk.DropDown.new_from_strings = staticmethod(new_from_strings)
    orig_note = Gio.Notification.new

    def note_new(title):
        return orig_note(tr(title))
    Gio.Notification.new = staticmethod(note_new)
    if hasattr(Gtk, "Entry"):
        wrap(Gtk.Entry, "set_placeholder_text")
    for cls_name in ("Toast",):
        cls = getattr(Adw, cls_name, None)
        if cls:
            wrap(cls, "set_title")
