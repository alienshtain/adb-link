"""One page, two parts: the phone itself, and the link with the ADB Link phone app."""
from __future__ import annotations

from gi.repository import Gtk


class PhoneLinkPage(Gtk.Box):
    def __init__(self, win, phone, link):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.phone, self.link = win, phone, link

        tabs = Gtk.Box(css_classes=["linked"], halign=Gtk.Align.CENTER, margin_top=10, margin_bottom=2)
        self.btn_phone = Gtk.ToggleButton(label="Phone", tooltip_text="Information and controls of the phone")
        self.btn_link = Gtk.ToggleButton(label="Phone app link",
                                         tooltip_text="Connect the ADB Link app on the phone to this computer")
        self.btn_link.set_group(self.btn_phone)
        self.btn_phone.set_active(True)
        self.btn_phone.connect("toggled", self._toggled)
        self.btn_link.connect("toggled", self._toggled)
        tabs.append(self.btn_phone)
        tabs.append(self.btn_link)
        self.append(tabs)

        self.stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(phone, "phone")
        self.stack.add_named(link, "link")
        self.append(self.stack)

    def _toggled(self, button):
        if button.get_active():
            self.stack.set_visible_child_name("link" if button is self.btn_link else "phone")
            self.reload_visible()

    def show(self, section):
        (self.btn_link if section == "link" else self.btn_phone).set_active(True)

    # the window asks every page whether it needs reloading
    @property
    def needs_reload(self):
        return self.phone.needs_reload

    @needs_reload.setter
    def needs_reload(self, value):
        self.phone.needs_reload = value

    def reload_visible(self):
        page = self.stack.get_visible_child()
        if getattr(page, "needs_reload", False):
            page.reload()

    def reload(self):
        self.reload_visible()
