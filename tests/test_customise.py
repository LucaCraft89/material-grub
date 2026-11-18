"""cmd_classes.customise: hiding and reordering whole menuentry blocks of an annotated grub.cfg from overrides.json. stdlib only.
usage: python3 tests/test_customise.py"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import cmd_classes  # noqa: E402
import grubscript  # noqa: E402
import mgoverrides  # noqa: E402

CFG = """set timeout=5
### BEGIN /etc/grub.d/10_linux ###
menuentry 'Ubuntu' --class ubuntu {
  linux /vmlinuz
}
menuentry 'Debian GNU/Linux' --class debian {
  linux /vmlinuz
}
submenu 'Advanced options for Ubuntu' {
  menuentry 'Ubuntu, with Linux 6.8' { linux /v }
}
### END /etc/grub.d/10_linux ###
### BEGIN /etc/grub.d/30_os-prober ###
menuentry 'Windows Boot Manager' --class windows {
  chainloader /EFI/Microsoft/Boot/bootmgfw.efi
}
if [ "$grub_platform" = "efi" ]; then
  menuentry 'UEFI Firmware Settings' { fwsetup }
fi
### END /etc/grub.d/30_os-prober ###
"""


def ov(**kw):
    c, e, _ = mgoverrides.validate(kw)
    assert not e, e
    return c


def titles(text):
    return [e.title for e in grubscript.scan(text).entries]


class Customise(unittest.TestCase):
    def prep(self, cfg=CFG, bls=()):
        cmd_classes.rules, cmd_classes.alias2key = [], {}
        text, entries, bls_at = cmd_classes.annotate(cfg, list(bls), "/loader", False)
        return text, entries, bls_at

    def test_nothing_to_do_changes_nothing(self):
        t, e, b = self.prep()
        self.assertEqual(cmd_classes.customise(t, e, b, ov()), (t, e, b))

    def test_windows_first(self):
        t, e, b = self.prep()
        t2, e2, _ = cmd_classes.customise(t, e, b, ov(groups=["windows", "linux"]))
        self.assertEqual(titles(t2)[:2], ["Windows Boot Manager", "Ubuntu"])
        self.assertEqual(sorted(titles(t2)), sorted(titles(t)))
        self.assertEqual(
            [x["title"] for x in e2 if x["level"] == "top" and not x.get("parent")][0], "Windows Boot Manager"
        )
        self.assertIn("### END /etc/grub.d/10_linux ###", t2)  # the text between the blocks stays
        self.assertEqual(len(e2), len(e))

    def test_children_move_with_their_submenu(self):
        t, e, b = self.prep()
        t2, e2, _ = cmd_classes.customise(t, e, b, ov(order=[{"title": "advanced options"}]))
        self.assertEqual(titles(t2)[:2], ["Advanced options for Ubuntu", "Ubuntu, with Linux 6.8"])
        names = [x["title"] for x in e2]
        self.assertEqual(names.index("Ubuntu, with Linux 6.8"), names.index("Advanced options for Ubuntu") + 1)

    def test_custom_order(self):
        t, e, b = self.prep()
        t2, _, _ = cmd_classes.customise(t, e, b, ov(order=[{"title": "debian"}, {"title": "windows"}]))
        self.assertEqual(titles(t2)[:3], ["Debian GNU/Linux", "Windows Boot Manager", "Ubuntu"])

    def test_hidden_is_cut_out_and_commented(self):
        t, e, b = self.prep()
        t2, e2, _ = cmd_classes.customise(t, e, b, ov(entries=[{"match": {"title": "windows"}, "hidden": True}]))
        self.assertNotIn("Windows Boot Manager", titles(t2))
        self.assertIn("# material-grub: hidden by overrides.json: Windows Boot Manager", t2)
        self.assertNotIn("bootmgfw", t2)
        self.assertNotIn("Windows Boot Manager", [x["title"] for x in e2])

    def test_hiding_a_submenu_takes_its_children(self):
        t, e, b = self.prep()
        t2, e2, _ = cmd_classes.customise(
            t, e, b, ov(entries=[{"match": {"title": "advanced options"}, "hidden": True}])
        )
        self.assertEqual(titles(t2), ["Ubuntu", "Debian GNU/Linux", "Windows Boot Manager", "UEFI Firmware Settings"])
        self.assertEqual(len(e2), len(e) - 2)

    def test_guarded_entries_are_left_alone(self):
        t, e, b = self.prep()
        t2, e2, _ = cmd_classes.customise(
            t, e, b, ov(groups=["system", "linux"], entries=[{"match": {"title": "firmware"}, "hidden": True}])
        )
        self.assertIn("UEFI Firmware Settings", titles(t2))
        self.assertEqual(titles(t2)[-1], "UEFI Firmware Settings")

    def test_numeric_default_means_hands_off(self):
        t, e, b = self.prep('set default="0"\n' + CFG)
        logs = []
        r = cmd_classes.customise(t, e, b, ov(groups=["windows"]), log=logs.append)
        self.assertEqual(r, (t, e, b))
        self.assertTrue(logs)

    def test_bls_block_moves_as_one_item(self):
        cfg = "set timeout=5\nblscfg\nmenuentry 'Windows Boot Manager' --class windows {\n  true\n}\n"
        t, e, b = self.prep(cfg, bls=[Path("x.conf")])
        self.assertIn(cmd_classes.BLS_MARK, t)
        self.assertEqual(b, 0)
        t2, e2, b2 = cmd_classes.customise(t, e, b, ov(groups=["windows", "linux"]))
        self.assertLess(t2.index("Windows Boot Manager"), t2.index(cmd_classes.BLS_MARK))
        self.assertEqual(b2, 1)
        self.assertEqual(titles(t2)[0], "Windows Boot Manager")
        self.assertEqual(sorted(titles(t2)), sorted(titles(t)))


class Guarded(unittest.TestCase):
    def test_guarded_flag(self):
        sc = grubscript.scan(
            "if true; then\n  menuentry 'a' { x }\nfi\nfunction f {\n  menuentry 'b' { x }\n}\nmenuentry 'c' { x }\n"
        )
        self.assertEqual([(e.title, e.guarded) for e in sc.entries], [("a", True), ("b", True), ("c", False)])
        e = sc.entries[2]
        self.assertEqual(sc.text[e.start : e.end], "menuentry 'c' { x }")


if __name__ == "__main__":
    unittest.main()
