"""Commands page: list / grid of adb commands, editor."""
from __future__ import annotations

import json
import uuid
from . import compat
from gi.repository import Adw, Gtk, Pango
from .commanddata import (
    CATEGORIES,
    DEFAULT_COMMANDS,
    SORT_MODES,
    build,
    category_rank,
    section_of,
    fields_of,
)
from .ui import (
    IconField,
    PromptWindow,
    clear_children,
    close_on_escape,
    confirm_dialog,
    make_icon,
)


class EditWindow(Gtk.Window):
    def __init__(self, parent, command, categories, on_save, on_delete):
        super().__init__(transient_for=parent, modal=True, default_width=600,
                         title="Edit command" if command else "New command")
        self.command, self.on_save, self.on_delete = command, on_save, on_delete
        c = command or {"name": "", "category": "Custom", "icon": "utilities-terminal-symbolic",
                        "description": "", "cmd": "", "confirm": False}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.set_child(box)
        self.name = Gtk.Entry(hexpand=True, text=c["name"])
        self.category = Gtk.Entry(hexpand=True, text=c["category"],
                                  tooltip_text="Existing: " + ", ".join(categories))
        self.icon = IconField(c.get("icon", ""))
        self.desc = Gtk.Entry(hexpand=True, text=c["description"])
        self.cmd = Gtk.Entry(hexpand=True, text=c["cmd"], css_classes=["monospace"],
                             placeholder_text="adb shell pm enable {package}")
        self.confirm = Gtk.Switch(valign=Gtk.Align.CENTER, halign=Gtk.Align.START,
                                  active=bool(c.get("confirm")))
        for e in (self.name, self.cmd):
            e.connect("changed", lambda w: w.remove_css_class("error"))
        grid = Gtk.Grid(row_spacing=10, column_spacing=12)
        rows = [("Name", self.name), ("Category", self.category), ("Icon", self.icon),
                ("Description", self.desc), ("Command", self.cmd),
                ("Ask before running", self.confirm)]
        for i, (label, widget) in enumerate(rows):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
        box.append(grid)
        box.append(Gtk.Label(
            xalign=0, wrap=True, css_classes=["dim-label", "caption"],
            label="Put {name} anywhere in the command for a value you type when you run it, "
                  "e.g. adb shell pm enable {package}. Names ending in _file or apk get a file "
                  "chooser; names ending in _folder get a folder chooser."))
        buttons = Gtk.Box(spacing=8)
        if command:
            delete = Gtk.Button(label="Delete", css_classes=["destructive-action"])
            delete.connect("clicked", self._delete)
            buttons.append(delete)
        buttons.append(Gtk.Box(hexpand=True))
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        save = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save.connect("clicked", self._save)
        buttons.append(cancel)
        buttons.append(save)
        box.append(buttons)
        close_on_escape(self)

    def _save(self, _b):
        name, cmd = self.name.get_text().strip(), self.cmd.get_text().strip()
        bad = False
        for entry, value in ((self.name, name), (self.cmd, cmd)):
            if not value:
                entry.add_css_class("error")
                bad = True
        if bad:
            return
        data = {"id": self.command["id"] if self.command else "custom-" + uuid.uuid4().hex[:8],
                "name": name, "category": self.category.get_text().strip() or "Custom",
                "icon": self.icon.get_text(), "description": self.desc.get_text().strip(),
                "cmd": cmd, "confirm": self.confirm.get_active()}
        self.close()
        self.on_save(data)

    def _delete(self, _b):
        confirm_dialog(self, f"Delete “{self.command['name']}”?",
                       "This removes the command from your list.", "Delete",
                       lambda: (self.close(), self.on_delete(self.command["id"])))


# ---------------------------------------------------------------- commands page

def refresh_star(widget):
    fav = widget.cmd["id"] in widget.page.win.favorites
    widget.star.set_icon_name("starred-symbolic" if fav else "non-starred-symbolic")
    widget.star.set_tooltip_text("Remove from favorites" if fav else "Add to favorites")
    (widget.star.add_css_class if fav else widget.star.remove_css_class)("warning")


def make_buttons(widget):
    """star / edit / run buttons wired to the page, for a row or a tile."""
    page, command = widget.page, widget.cmd
    widget.star = Gtk.Button(valign=Gtk.Align.CENTER, css_classes=["flat", "circular"])
    widget.star.connect("clicked", lambda _b: page.toggle_favorite(command["id"]))
    edit = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER,
                      css_classes=["flat", "circular"], tooltip_text="Edit this command")
    edit.connect("clicked", lambda _b: page.on_edit(command))
    run = Gtk.Button(label="Run", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
    run.connect("clicked", lambda _b: page.on_run(command))
    return widget.star, edit, run


class CommandRow(Gtk.ListBoxRow):
    def __init__(self, page, command):
        super().__init__(activatable=False, selectable=False)
        self.page, self.cmd = page, command
        star, edit, run = make_buttons(self)
        box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=6, margin_end=10)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True,
                       valign=Gtk.Align.CENTER)
        text.append(Gtk.Label(label=command["name"], xalign=0, css_classes=["heading"]))
        if command["description"]:
            text.append(Gtk.Label(label=command["description"], xalign=0, wrap=True,
                                  css_classes=["dim-label"]))
        text.append(Gtk.Label(label=command["cmd"], xalign=0, ellipsize=Pango.EllipsizeMode.END,
                              css_classes=["monospace", "caption", "dim-label"]))
        for w in (star, make_icon(command.get("icon"), 28), text, edit, run):
            box.append(w)
        self.set_child(box)
        refresh_star(self)

    def refresh_star(self):
        refresh_star(self)


class CommandTile(Gtk.FlowBoxChild):
    def __init__(self, page, command):
        super().__init__()
        self.page, self.cmd = page, command
        star, edit, run = make_buttons(self)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       css_classes=["card", "tile"], width_request=190)
        top = Gtk.Box()
        top.append(star)
        top.append(Gtk.Box(hexpand=True))
        top.append(edit)
        card.append(top)
        icon = make_icon(command.get("icon"), 40)
        icon.set_halign(Gtk.Align.CENTER)
        card.append(icon)
        card.append(Gtk.Label(label=command["name"], wrap=True, justify=Gtk.Justification.CENTER,
                              css_classes=["heading"]))
        card.append(Gtk.Label(label=command["description"], wrap=True, lines=2, vexpand=True,
                              ellipsize=Pango.EllipsizeMode.END, max_width_chars=24,
                              justify=Gtk.Justification.CENTER, css_classes=["dim-label", "caption"]))
        run.set_halign(Gtk.Align.FILL)
        card.append(run)
        self.set_child(card)
        refresh_star(self)

    def refresh_star(self):
        refresh_star(self)


class CommandsPage(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        mode = win.settings.get("sort", 0)
        self.sort_mode = mode if mode in range(len(SORT_MODES)) else 0
        self.search_text, self.only_favs, self.widgets = "", False, []
        self.section = 1 if win.settings.get("section", 1) == 1 else 0

        parts = Gtk.Box(css_classes=["linked"], halign=Gtk.Align.CENTER, margin_top=10)
        self.sec_setup = Gtk.ToggleButton(label="Devices and adb setup",
                                          tooltip_text="Show the connected phones and prepare adb")
        self.sec_phone = Gtk.ToggleButton(label="On the phone", tooltip_text="Commands that act on the phone")
        self.sec_phone.set_group(self.sec_setup)
        (self.sec_phone if self.section == 1 else self.sec_setup).set_active(True)
        self.sec_setup.connect("toggled", self._on_section)
        self.sec_phone.connect("toggled", self._on_section)
        parts.append(self.sec_setup)
        parts.append(self.sec_phone)
        self.append(parts)

        bar = Gtk.Box(spacing=8, margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search commands")
        search.connect("search-changed", self._on_search)
        fav = Gtk.ToggleButton(icon_name="starred-symbolic", tooltip_text="Show favorites only")
        fav.connect("toggled", self._on_fav_filter)
        sort = Gtk.DropDown.new_from_strings(SORT_MODES)
        sort.set_selected(self.sort_mode)
        sort.connect("notify::selected", self._on_sort)
        self.list_btn = Gtk.ToggleButton(icon_name="view-list-symbolic", tooltip_text="List view")
        self.grid_btn = Gtk.ToggleButton(icon_name="view-grid-symbolic", tooltip_text="Boxes view")
        self.grid_btn.set_group(self.list_btn)
        views = Gtk.Box(css_classes=["linked"])
        views.append(self.list_btn)
        views.append(self.grid_btn)
        add = Gtk.Button(css_classes=["suggested-action"], tooltip_text="Add your own command")
        add.set_child(compat.content("list-add-symbolic", "New command"))
        add.connect("clicked", lambda _b: self.on_edit(None))
        for w in (search, fav, Gtk.Label(label="Sort", css_classes=["dim-label"]), sort, views, add):
            bar.append(w)
        self.append(bar)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["rich-list"])
        self.listbox.set_header_func(self._header_func)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                min_children_per_line=2, max_children_per_line=6,
                                row_spacing=10, column_spacing=10, valign=Gtk.Align.START,
                                margin_top=6, margin_bottom=12, margin_start=12, margin_end=12)
        for container in (self.listbox, self.flow):
            container.set_sort_func(self._sort_func)
            container.set_filter_func(self._filter_func)
        self.listbox.set_placeholder(Gtk.Label(label="No commands match.", margin_top=24,
                                               margin_bottom=24, css_classes=["dim-label"]))
        self.stack = Gtk.Stack(vexpand=True)
        for name, widget in (("list", self.listbox), ("grid", self.flow)):
            scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroller.set_child(widget)
            self.stack.add_named(scroller, name)
        self.append(self.stack)
        view = win.settings.get("view", "list")
        (self.grid_btn if view == "grid" else self.list_btn).set_active(True)
        self.stack.set_visible_child_name("grid" if view == "grid" else "list")
        self.list_btn.connect("toggled", self._on_view)
        self.grid_btn.connect("toggled", self._on_view)
        self.reload()

    # ---- building / refreshing
    def reload(self):
        clear_children(self.listbox)
        clear_children(self.flow)
        self.widgets = []
        for command in self.win.commands:
            row, tile = CommandRow(self, command), CommandTile(self, command)
            self.listbox.append(row)
            self.flow.append(tile)
            self.widgets += [row, tile]
        self.refresh()

    def refresh(self):
        for container in (self.listbox, self.flow):
            container.invalidate_sort()
            container.invalidate_filter()
        self.listbox.invalidate_headers()

    def _key(self, command):
        name = command["name"].lower()
        if self.sort_mode == 0:
            return (category_rank(command["category"]), self.win.commands.index(command))
        if self.sort_mode == 3:
            return ((0, "") if command["id"] in self.win.favorites else (1, ""), name)
        return ((0, ""), name)

    def _sort_func(self, a, b):
        ka, kb = self._key(a.cmd), self._key(b.cmd)
        result = (ka > kb) - (ka < kb)
        return -result if self.sort_mode == 2 else result

    def _on_section(self, button):
        if button.get_active():
            self.section = 1 if button is self.sec_phone else 0
            self.win.settings["section"] = self.section
            self.win.save()
            self.refresh()

    def _filter_func(self, child):
        command = child.cmd
        if not self.search_text and section_of(command) != self.section:
            return False
        if self.only_favs and command["id"] not in self.win.favorites:
            return False
        if self.search_text:
            text = " ".join([command["name"], command["description"], command["cmd"],
                             command["category"]]).lower()
            return self.search_text in text
        return True

    def _header_func(self, row, before):
        if self.sort_mode == 0 and (before is None or before.cmd["category"] != row.cmd["category"]):
            row.set_header(Gtk.Label(label=row.cmd["category"], xalign=0, margin_top=14,
                                     margin_bottom=4, margin_start=12, css_classes=["title-4"]))
        else:
            row.set_header(None)

    # ---- toolbar handlers
    def _on_search(self, entry):
        self.search_text = entry.get_text().strip().lower()
        self.refresh()

    def _on_fav_filter(self, button):
        self.only_favs = button.get_active()
        self.refresh()

    def _on_sort(self, dropdown, _pspec):
        self.sort_mode = dropdown.get_selected()
        self.win.settings["sort"] = self.sort_mode
        self.win.save()
        self.refresh()

    def _on_view(self, button):
        if button.get_active():
            view = "grid" if button is self.grid_btn else "list"
            self.stack.set_visible_child_name(view)
            self.win.settings["view"] = view
            self.win.save()

    def toggle_favorite(self, cid):
        favs = self.win.favorites
        favs.discard(cid) if cid in favs else favs.add(cid)
        self.win.settings["favorites"] = sorted(favs)
        self.win.save()
        for w in self.widgets:
            w.refresh_star()
        self.refresh()

    # ---- running
    def on_run(self, command):
        keys = fields_of(command["cmd"])

        def with_values(values):
            if values:
                self.win.settings.setdefault("values", {}).update(values)
                self.win.save()
            final = build(command["cmd"], values)
            go = lambda: self.win.run_shell(
                final, on_done=self.win.refresh_devices if command["category"] == "Connection" else None)
            if command["confirm"]:
                confirm_dialog(self.win, f"Run “{command['name']}”?", final, "Run", go)
            else:
                go()

        if keys:
            PromptWindow(self.win, command["name"], command["description"], keys,
                         self.win.settings.get("values", {}), with_values).present()
        else:
            with_values({})

    # ---- editing
    def on_edit(self, command):
        cats = list(dict.fromkeys(CATEGORIES + [c["category"] for c in self.win.commands]))
        EditWindow(self.win, command, cats, self.save_command, self.delete_command).present()

    def save_command(self, data):
        commands = self.win.commands
        for i, c in enumerate(commands):
            if c["id"] == data["id"]:
                commands[i] = data
                break
        else:
            commands.append(data)
        self.win.save()
        self.reload()

    def delete_command(self, cid):
        self.win.settings["commands"] = [c for c in self.win.commands if c["id"] != cid]
        self.win.favorites.discard(cid)
        self.win.settings["favorites"] = sorted(self.win.favorites)
        self.win.save()
        self.reload()

    def reset_defaults(self):
        def do():
            self.win.settings["commands"] = json.loads(json.dumps(DEFAULT_COMMANDS))
            self.win.save()
            self.reload()
            self.win.toast("Commands reset to the defaults")
        confirm_dialog(self.win, "Reset all commands?",
                       "This replaces your command list (including your edits and custom "
                       "commands) with the original set.", "Reset", do)
