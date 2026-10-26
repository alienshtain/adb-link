"""Contacts page."""
from __future__ import annotations

from gi.repository import Gtk, Pango
from .adbutil import adb, first_line
from .apps_helpers import avatar
from .phone_tools import DEFAULT_SUB, dial_cmd, digits, send_sms
from .ui import clear_children, close_on_escape


# ---------------------------------------------------------------- contacts page

class ContactRow(Gtk.ListBoxRow):
    def __init__(self, page, name, number):
        super().__init__(activatable=False, selectable=False)
        self.name, self.number = name, number
        box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
        box.append(avatar(name, 38))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text.append(Gtk.Label(label=name, xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["heading"]))
        text.append(Gtk.Label(label=number, xalign=0, css_classes=["dim-label", "caption"]))
        box.append(text)
        msg = Gtk.Button(icon_name="mail-message-new-symbolic", css_classes=["flat", "circular"],
                         valign=Gtk.Align.CENTER, tooltip_text="Send a message")
        call = Gtk.Button(icon_name="call-start-symbolic", css_classes=["circular", "call-answer"],
                          valign=Gtk.Align.CENTER, tooltip_text="Call")
        msg.connect("clicked", lambda _b: page.message(name, number))
        call.connect("clicked", lambda _b: page.call(name, number))
        box.append(msg)
        box.append(call)
        self.set_child(box)


class MessageWindow(Gtk.Window):
    def __init__(self, page, name, number):
        super().__init__(transient_for=page.win, modal=True, title=f"Message to {name}",
                         default_width=420, default_height=260)
        self.page, self.number = page, number
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14,
                      margin_bottom=14, margin_start=14, margin_end=14)
        box.append(Gtk.Label(label=f"{name}  {number}" if name != number else number, xalign=0,
                             css_classes=["heading"]))
        self.sim_label = Gtk.Label(label="", xalign=0, css_classes=["dim-label", "caption"])
        box.append(self.sim_label)
        self.text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8,
                                 left_margin=8, right_margin=8)
        scroller = Gtk.ScrolledWindow(vexpand=True, css_classes=["card"])
        scroller.set_child(self.text)
        box.append(scroller)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        self.send_btn = Gtk.Button(label="Send", css_classes=["suggested-action"])
        self.send_btn.connect("clicked", self._send)
        row.append(cancel)
        row.append(self.send_btn)
        box.append(row)
        self.set_child(box)
        close_on_escape(self)
        self.sim_label.set_text("Sent with: " + page.sim_text())

    def _send(self, _b):
        buf = self.text.get_buffer()
        body = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        if not body:
            return
        self.send_btn.set_sensitive(False)
        sub = self.page.selected_sub()

        def done(res):
            if isinstance(res, Exception):
                self.page.win.toast(f"Message failed: {res}")
                self.send_btn.set_sensitive(True)
                return
            sent, msg = res
            self.page.win.toast(msg)
            self.page.win.log(f"SMS to {self.number}: {msg}\n")
            if sent:
                self.close()
            else:
                self.send_btn.set_sensitive(True)
        self.page.win.bg(lambda: send_sms(self.number, body, sub), done)


class ContactsPage(Gtk.Box):
    """Phone book of the phone: call or write to anyone with the SIM you choose."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.needs_reload = win, True
        self._sim_updating = False
        self.sim_choices = []  # [(label, slot, sub_id)]
        bar = Gtk.Box(spacing=8, margin_top=8, margin_bottom=4, margin_start=10, margin_end=10)
        self.search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search contacts")
        self.search.connect("search-changed", lambda _e: self.listbox.invalidate_filter())
        self.sim_dd = Gtk.DropDown(model=Gtk.StringList.new(["Phone default"]), tooltip_text="SIM card to use")
        self.sim_dd.connect("notify::selected", self._sim_changed)
        reload_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload contacts")
        reload_btn.connect("clicked", lambda _b: self.reload())
        for w in (self.search, Gtk.Label(label="SIM", css_classes=["dim-label"]), self.sim_dd, reload_btn):
            bar.append(w)
        self.append(bar)

        dial = Gtk.Box(spacing=8, margin_bottom=6, margin_start=10, margin_end=10)
        self.number = Gtk.Entry(hexpand=True, placeholder_text="Type a number to call or message")
        self.number.connect("activate", lambda _e: self._dial_call())
        msg = Gtk.Button(icon_name="mail-message-new-symbolic", tooltip_text="Message this number")
        call = Gtk.Button(icon_name="call-start-symbolic", css_classes=["call-answer"], tooltip_text="Call this number")
        msg.connect("clicked", lambda _b: self._dial_msg())
        call.connect("clicked", lambda _b: self._dial_call())
        for w in (self.number, msg, call):
            dial.append(w)
        self.append(dial)

        self.status = Gtk.Label(xalign=0, margin_start=14, margin_bottom=4, css_classes=["dim-label", "caption"])
        self.append(self.status)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"],
                                   margin_start=10, margin_end=10, margin_bottom=10)
        self.listbox.set_filter_func(self._match)
        self.listbox.set_placeholder(Gtk.Label(label="No contacts", css_classes=["dim-label"], margin_top=30))
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self.listbox)
        self.append(scroller)

    # ---- sim choice
    def _build_sims(self):
        sims = self.win.sims or []
        self.sim_choices = [(f"SIM {s['slot'] + 1}" + (f" - {s['name']}" if s["name"] else ""), s["slot"], s["sub"])
                            for s in sims]
        if not self.sim_choices:
            self.sim_choices = [("SIM 1", 0, DEFAULT_SUB), ("SIM 2", 1, DEFAULT_SUB)]
        self.sim_choices.append(("Phone default", -1, DEFAULT_SUB))
        self._sim_updating = True
        self.sim_dd.set_model(Gtk.StringList.new([c[0] for c in self.sim_choices]))
        want = self.win.pref("sim")
        self.sim_dd.set_selected(next((i for i, c in enumerate(self.sim_choices) if c[1] == want),
                                      len(self.sim_choices) - 1))
        self._sim_updating = False

    def _sim_changed(self, dropdown, _p):
        i = dropdown.get_selected()
        if not self._sim_updating and 0 <= i < len(self.sim_choices):
            self.win.set_pref("sim", self.sim_choices[i][1])

    def _choice(self):
        i = self.sim_dd.get_selected()
        return self.sim_choices[i] if 0 <= i < len(self.sim_choices) else ("Phone default", -1, DEFAULT_SUB)

    def selected_slot(self):
        return self._choice()[1]

    def selected_sub(self):
        return self._choice()[2]

    def sim_text(self):
        return self._choice()[0]

    # ---- list
    def reload(self):
        self.needs_reload = False
        self.status.set_text("Reading the phone book...")
        self.win.load_sims(self._build_sims)
        self.win.load_contacts(self._fill, force=True)

    def _fill(self):
        clear_children(self.listbox)
        contacts = self.win.contacts
        if contacts is None:
            self.status.set_text("Could not read the contacts. Is the phone connected?")
            return
        for name, number in contacts:
            self.listbox.append(ContactRow(self, name, number))
        self.status.set_text(f"{len(contacts)} contacts")

    def _match(self, row):
        q = self.search.get_text().strip().lower()
        return bool(not q or q in row.name.lower() or (digits(q) and digits(q) in digits(row.number)))

    # ---- actions
    def call(self, name, number):
        slot = self.selected_slot()
        self.win.toast(f"Calling {name}...")
        self.win.log(f"$ adb shell {dial_cmd(number, slot)}\n")

        def done(res):
            rc, out, err = res if not isinstance(res, Exception) else (1, "", str(res))
            text = (out + err).strip()
            if rc != 0 or "Error" in text or "xception" in text:
                self.win.toast(f"Call failed: {first_line(text)}")
        self.win.bg(lambda: adb("shell", dial_cmd(number, slot), timeout=20), done)

    def message(self, name, number):
        MessageWindow(self, name, number).present()

    def _typed(self):
        number = self.number.get_text().strip()
        if not digits(number):
            self.win.toast("Type a phone number first")
            return None
        return number

    def _dial_call(self):
        number = self._typed()
        if number:
            self.call(number, number)

    def _dial_msg(self):
        number = self._typed()
        if number:
            self.message(number, number)
