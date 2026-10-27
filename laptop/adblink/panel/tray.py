"""A small icon in the system tray (like Discord): click for Open / Quit.

Uses the StatusNotifierItem D-Bus protocol that KDE, Cinnamon, XFCE, MATE and GNOME (with the
AppIndicator extension, preinstalled on Ubuntu) understand. When there is no tray the app simply
goes on without it.
"""
from __future__ import annotations

import os

from gi.repository import Gio, GLib

from ..paths import APP_ID, APP_NAME

ITEM_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <signal name="NewIcon"/>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
</node>"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/><arg type="as" direction="in"/>
      <arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/>
    </method>
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
  </interface>
</node>"""

ITEM_PATH, MENU_PATH = "/StatusNotifierItem", "/MenuBar"


class Tray:
    """items: [(label, callback)]; the first one is also run when the icon is clicked."""

    def __init__(self, items, icon_dirs=()):
        self.items = list(items)
        self.icon_path = ":".join(str(d) for d in icon_dirs)
        self.conn = None
        self.ok = False
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.revision = 1
        try:
            self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._export()
            Gio.bus_own_name_on_connection(self.conn, self.name, Gio.BusNameOwnerFlags.NONE,
                                           self._name_acquired, None)
        except GLib.Error:
            self.conn = None

    # ---- setup
    def _export(self):
        item = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.conn.register_object(ITEM_PATH, item, self._item_call, self._item_get, None)
        self.conn.register_object(MENU_PATH, menu, self._menu_call, self._menu_get, None)

    def _name_acquired(self, conn, _name):
        conn.call(
            "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher",
            "RegisterStatusNotifierItem", GLib.Variant("(s)", (self.name,)), None,
            Gio.DBusCallFlags.NONE, 2000, None, self._registered)

    def _registered(self, conn, result):
        try:
            conn.call_finish(result)
            self.ok = True
        except GLib.Error:
            self.ok = False     # no tray on this desktop

    # ---- the item
    def _item_get(self, _c, _s, _p, _i, prop):
        values = {
            "Category": GLib.Variant("s", "ApplicationStatus"), "Id": GLib.Variant("s", APP_ID),
            "Title": GLib.Variant("s", APP_NAME), "Status": GLib.Variant("s", "Active"),
            "WindowId": GLib.Variant("i", 0), "IconName": GLib.Variant("s", APP_ID),
            "IconThemePath": GLib.Variant("s", self.icon_path), "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", MENU_PATH),
        }
        return values.get(prop)

    def _item_call(self, _c, _s, _p, _i, method, params, invocation):
        if method == "Activate" and self.items:
            GLib.idle_add(self.items[0][1])
        invocation.return_value(None)

    # ---- the menu
    def _entry(self, index, label):
        return (index, {"label": GLib.Variant("s", label), "enabled": GLib.Variant("b", True),
                        "visible": GLib.Variant("b", True)}, [])

    def _menu_get(self, _c, _s, _p, _i, prop):
        return {"Version": GLib.Variant("u", 3), "TextDirection": GLib.Variant("s", "ltr"),
                "Status": GLib.Variant("s", "normal"),
                "IconThemePath": GLib.Variant("as", [])}.get(prop)

    def _menu_call(self, _c, _s, _p, _i, method, params, invocation):
        if method == "GetLayout":
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, self._layout_tuple())))
        elif method == "GetGroupProperties":
            ids = params.unpack()[0]
            rows = [(i + 1, {"label": GLib.Variant("s", label)}) for i, (label, _cb) in enumerate(self.items)
                    if not ids or (i + 1) in ids]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (rows,)))
        elif method == "GetProperty":
            invocation.return_value(GLib.Variant("(v)", (GLib.Variant("s", ""),)))
        elif method == "Event":
            ident, event, _data, _ts = params.unpack()
            if event == "clicked" and 1 <= ident <= len(self.items):
                GLib.idle_add(self.items[ident - 1][1])
            invocation.return_value(None)
        elif method == "EventGroup":
            for ident, event, _data, _ts in params.unpack()[0]:
                if event == "clicked" and 1 <= ident <= len(self.items):
                    GLib.idle_add(self.items[ident - 1][1])
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        else:
            invocation.return_error_literal(Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, method)

    def _layout_tuple(self):
        kids = [GLib.Variant("(ia{sv}av)", self._entry(i + 1, label)) for i, (label, _cb) in enumerate(self.items)]
        return (0, {"children-display": GLib.Variant("s", "submenu")}, kids)

    def close(self):
        self.conn = None
