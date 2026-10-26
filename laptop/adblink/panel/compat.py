"""Small wrappers so the window also works on older GTK / libadwaita (Ubuntu 22.04, Debian 12)
as well as on the newest ones."""
from __future__ import annotations

from gi.repository import Adw, Gio, GLib, Gtk


def content(icon, label):
    """An icon with a text label for a button (Adw.ButtonContent needs libadwaita 1.2)."""
    if hasattr(Adw, "ButtonContent"):
        return Adw.ButtonContent(icon_name=icon, label=label)
    box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
    box.append(Gtk.Image.new_from_icon_name(icon))
    box.append(Gtk.Label(label=label))
    return box


def confirm(parent, message, detail, ok_label, on_ok):
    if hasattr(Gtk, "AlertDialog"):
        dialog = Gtk.AlertDialog()
        dialog.set_message(message)
        dialog.set_detail(detail)
        dialog.set_buttons(["Cancel", ok_label])
        dialog.set_cancel_button(0)
        dialog.set_default_button(1)

        def chosen(dlg, result):
            try:
                index = dlg.choose_finish(result)
            except GLib.Error:
                return
            if index == 1:
                on_ok()

        dialog.choose(parent, None, chosen)
        return
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.QUESTION,
                               text=message, secondary_text=detail)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button(ok_label, Gtk.ResponseType.OK)

    def response(dlg, rid):
        dlg.destroy()
        if rid == Gtk.ResponseType.OK:
            on_ok()

    dialog.connect("response", response)
    dialog.present()


def _filters(spec):
    """spec: [(name, [suffixes])] ('*' = everything) -> Gio.ListStore of Gtk.FileFilter"""
    store = Gio.ListStore.new(Gtk.FileFilter)
    for name, suffixes in spec or []:
        f = Gtk.FileFilter()
        f.set_name(name)
        for ext in suffixes:
            f.add_pattern("*" if ext == "*" else f"*.{ext}")
            if ext != "*":
                f.add_pattern(f"*.{ext.upper()}")
        store.append(f)
    return store


def pick(parent, kind, on_paths, title="", multiple=False, filters=None):
    """kind: 'file' | 'folder'. Calls on_paths(list_of_str) with at least one path."""
    title = title or ("Choose a folder" if kind == "folder" else "Choose files" if multiple else "Choose a file")
    if hasattr(Gtk, "FileDialog"):
        dialog = Gtk.FileDialog()
        dialog.set_title(title)
        if filters:
            dialog.set_filters(_filters(filters))

        def done(dlg, result):
            try:
                if kind == "folder":
                    got = [dlg.select_folder_finish(result)]
                elif multiple:
                    lst = dlg.open_multiple_finish(result)
                    got = [lst.get_item(i) for i in range(lst.get_n_items())]
                else:
                    got = [dlg.open_finish(result)]
            except GLib.Error:
                return
            paths = [g.get_path() for g in got if g is not None and g.get_path()]
            if paths:
                on_paths(paths)

        if kind == "folder":
            dialog.select_folder(parent, None, done)
        elif multiple:
            dialog.open_multiple(parent, None, done)
        else:
            dialog.open(parent, None, done)
        return
    action = Gtk.FileChooserAction.SELECT_FOLDER if kind == "folder" else Gtk.FileChooserAction.OPEN
    chooser = Gtk.FileChooserNative.new(title, parent, action, "_Open", "_Cancel")
    chooser.set_select_multiple(bool(multiple) and kind != "folder")
    for name, suffixes in filters or []:
        f = Gtk.FileFilter()
        f.set_name(name)
        for ext in suffixes:
            f.add_pattern("*" if ext == "*" else f"*.{ext}")
        chooser.add_filter(f)

    def response(ch, rid):
        paths = []
        if rid == Gtk.ResponseType.ACCEPT:
            files = ch.get_files()
            paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
        ch.destroy()
        paths = [p for p in paths if p]
        if paths:
            on_paths(paths)

    chooser.connect("response", response)
    chooser.show()
    pick._keep = chooser  # keep a reference alive while it is open
