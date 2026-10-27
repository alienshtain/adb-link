"""The clipboard, handled inside the window's own process (no helper program is started)."""
from __future__ import annotations

from gi.repository import GLib

from ..server import clipboard as clip
from ..server.events import EVENTS


class GtkClipboard:
    def __init__(self, display):
        self.cb = display.get_clipboard()
        self.text = None
        self.cb.connect("changed", self._changed)
        GLib.idle_add(self._changed)

    def _changed(self, *_a):
        if self.cb.is_local():      # we put it there ourselves
            return False
        self.cb.read_text_async(None, self._read)
        return False

    def _read(self, cb, result):
        try:
            text = cb.read_text_finish(result)
        except GLib.Error:
            return
        if text is None:
            return
        self.text = text
        if text != clip._clip_state["last"]:
            clip._clip_state["last"] = text
            if text.strip():
                EVENTS.add({"type": "clipboard", "text": text})

    # -- used from the server thread
    def get(self):
        return self.text

    def set(self, text):
        self.text = text
        clip._clip_state["last"] = text
        GLib.idle_add(self.cb.set, text)
        return True


def install(display):
    """Make the server use the window's clipboard."""
    if display is not None:
        clip.PROVIDER = GtkClipboard(display)
