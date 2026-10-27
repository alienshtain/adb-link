import json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "laptop"))


class Features(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp + "/c"
        os.environ["HOME"] = self.tmp

    def test_storage_default_and_custom(self):
        from adblink import storage
        self.assertTrue(str(storage.save_root()).endswith("Documents/ADB Link"))
        cfg = Path(self.tmp, "c", "adblink")
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "panel.json").write_text(json.dumps({"prefs": {"save_dir": self.tmp + "/mine"}}))
        self.assertEqual(str(storage.save_root()), self.tmp + "/mine")
        self.assertTrue(storage.folder("shots").is_dir())

    def test_ascii_typing_command(self):
        from adblink import phonetype
        self.assertEqual(phonetype.ascii_command("a b"), "input text a%sb")

    def test_arabic_goes_through_phone_app(self):
        from adblink import phonetype
        calls = []

        def fake(*args, **kw):
            calls.append(args[-1])
            if "pm list packages" in args[-1]:
                return 0, "package:" + phonetype.PHONE_APP
            if "am broadcast" in args[-1]:
                return 0, "Broadcast completed: result=1"
            return 0, ""
        phonetype.conn.adb = fake
        ok, _ = phonetype.type_text("مرحبا")
        self.assertTrue(ok)
        self.assertTrue(any("TypeReceiver" in c for c in calls))
        self.assertTrue(any("keyevent 279" in c for c in calls))

    def test_arabic_without_helper_explains(self):
        from adblink import phonetype
        phonetype.conn.adb = lambda *a, **k: (0, "")
        ok, msg = phonetype.type_text("مرحبا")
        self.assertFalse(ok)
        self.assertIn("install-phone", msg)

    def test_translation(self):
        os.environ["ADBLINK_LANG"] = "ar"
        from adblink import i18n
        i18n._state["lang"] = None
        self.assertEqual(i18n.tr("Cancel"), "إلغاء")
        self.assertIn("/tmp/x", i18n.tr("Saved /tmp/x"))
        self.assertEqual(i18n.tr("never translated text"), "never translated text")
        os.environ["ADBLINK_LANG"] = "en"
        i18n._state["lang"] = None
        self.assertEqual(i18n.tr("Cancel"), "Cancel")

    def test_patterns_valid(self):
        import re
        from adblink.i18n_ar import PATTERNS
        for p, t in PATTERNS:
            n = re.compile(p).groups
            for i in re.findall(r"\{(\d+)\}", t):
                self.assertLess(int(i), n, (p, t))

    def test_removed_commands(self):
        try:
            import gi  # noqa: F401
            gi.require_version("Gtk", "4.0")
        except (ImportError, ValueError):
            self.skipTest("PyGObject / GTK 4 not available")
        from adblink.panel.commanddata import DEFAULT_COMMANDS, section_of
        ids = {c["id"] for c in DEFAULT_COMMANDS}
        self.assertFalse(ids & {"uninstall", "remove-system", "restore"})
        self.assertEqual(section_of({"category": "Connection"}), 0)
        self.assertEqual(section_of({"category": "Apps"}), 1)


if __name__ == "__main__":
    unittest.main()
