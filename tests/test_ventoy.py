"""Unit tests for the Ventoy target (no Ventoy, no QEMU): menu_class key selection, name matching, a full run on a fake stick, idempotency and uninstall.
usage: python3 tests/test_ventoy.py   (the run on a fake stick is skipped when dist/material-grub is not built)"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
TOOL = ROOT / "install/bin/material-grub-ventoy"

sys.path.insert(0, str(ROOT / "install/bin"))
from cmd_ventoy import dynamic_rules, key_of, pick_key


class Keys(unittest.TestCase):
    def test_never_the_whole_name_never_over_30(self):
        for n in ("a.iso", "Fedora-Workstation-Live-x86_64-44-1.7.iso", "x" * 80 + ".iso"):
            k = pick_key(n, [])
            self.assertIn(k, n)
            self.assertNotEqual(k, n)
            self.assertLessEqual(len(k), 30)

    def test_unique_among_others(self):
        others = ["Fedora-Workstation-Live-x86_64-44-1.6.iso", "Fedora-Workstation-Live-x86_64-43-1.6.iso"]
        n = "Fedora-Workstation-Live-x86_64-44-1.7.iso"
        k = pick_key(n, others)
        self.assertIn(k, n)
        self.assertFalse(any(k in o for o in others))

    def test_no_unique_key(self):
        self.assertIsNone(pick_key("a.iso", ["a.iso.bak", "xa.iso"]))


@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class Names(unittest.TestCase):
    def test_keys(self):
        import mgrub

        rules = mgrub.load_rules(PKG)
        for n, k in (
            ("archlinux-2026.11.01-x86_64.iso", "arch"),
            ("Fedora-Workstation-Live-x86_64-44-1.7.iso", "fedora"),
            ("ubuntu-24.04.1-desktop-amd64.iso", "ubuntu"),
            ("Win11_24H2_English_x64.iso", "windows11"),
            ("Win10_22H2_x64.iso", "windows10"),
            ("gparted-live-1.6.iso", "iso"),
            ("KALI-linux-2026.3.iso", "kali"),
        ):
            self.assertEqual(key_of(n, rules), k, n)


LSBLK = json.dumps(
    {
        "blockdevices": [
            {
                "name": "sda",
                "path": "/dev/sda",
                "type": "disk",
                "model": "Samsung SSD",
                "children": [
                    {
                        "name": "sda1",
                        "path": "/dev/sda1",
                        "label": "EFI",
                        "fstype": "vfat",
                        "size": 600000000,
                        "type": "part",
                        "mountpoints": ["/boot/efi"],
                    }
                ],
            },
            {
                "name": "sdb",
                "path": "/dev/sdb",
                "type": "disk",
                "model": "DataTraveler 3.0 ",
                "children": [
                    {
                        "name": "sdb1",
                        "path": "/dev/sdb1",
                        "label": "Ventoy",
                        "fstype": "exfat",
                        "size": 59000000000,
                        "type": "part",
                        "mountpoints": ["/run/media/u/Ventoy"],
                    },
                    {
                        "name": "sdb2",
                        "path": "/dev/sdb2",
                        "label": "VTOYEFI",
                        "fstype": "vfat",
                        "size": 33554432,
                        "type": "part",
                        "mountpoints": [None],
                    },
                ],
            },
            {
                "name": "sdc",
                "path": "/dev/sdc",
                "type": "disk",
                "model": "Other",
                "children": [
                    {
                        "name": "sdc1",
                        "path": "/dev/sdc1",
                        "label": "Ventoy",
                        "fstype": "ntfs",
                        "size": 1000000000,
                        "type": "part",
                        "mountpoints": [None],
                    },
                    {
                        "name": "sdc2",
                        "path": "/dev/sdc2",
                        "label": "VTOYEFI",
                        "fstype": "vfat",
                        "size": 33554432,
                        "type": "part",
                        "mountpoints": [None],
                    },
                ],
            },
        ]
    }
)
LSBLK_L = json.dumps(
    {
        "blockdevices": [
            {"path": "/dev/sda1", "label": "EFI", "type": "part", "pkname": "sda"},
            {"path": "/dev/sdb", "label": None, "type": "disk", "pkname": None},
            {"path": "/dev/sdb1", "label": "Ventoy", "type": "part", "pkname": "sdb"},
            {"path": "/dev/sdb2", "label": "VTOYEFI", "type": "part", "pkname": "sdb"},
            {"path": "/dev/sdc1", "label": "USBDATA", "type": "part", "pkname": "sdc"},
        ]
    }
)


class Verify(unittest.TestCase):
    def test_sibling_vtoyefi(self):
        sys.path.insert(0, str(ROOT / "install"))
        import ventoy_sticks as vs

        self.assertTrue(
            vs.sibling_vtoyefi(LSBLK_L, "/dev/sdb1")
        )  # fresh Ventoy data partition: verified even without a /ventoy folder
        self.assertFalse(
            vs.sibling_vtoyefi(LSBLK_L, "/dev/sdc1")
        )  # an ordinary USB disk, even if it has a folder called ventoy
        self.assertFalse(vs.sibling_vtoyefi(LSBLK_L, "/dev/nope"))
        self.assertFalse(vs.sibling_vtoyefi("garbage", "/dev/sdb1"))

    def test_folder_only_is_accepted_but_labelled(self):
        sys.path.insert(0, str(ROOT / "install"))
        import ventoy_sticks as vs

        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(vs.check(d))
            (Path(d) / "ventoy").mkdir()
            self.assertEqual(vs.check(d), "folder")


class Sticks(unittest.TestCase):
    def test_parse_lsblk(self):
        sys.path.insert(0, str(ROOT / "install"))
        import ventoy_sticks as vs

        s = vs.parse_lsblk(LSBLK)
        self.assertEqual(
            [x["path"] for x in s], ["/run/media/u/Ventoy", "dev:/dev/sdc1"]
        )  # the system disk has no VTOYEFI; VTOYEFI itself is never listed
        self.assertEqual((s[0]["mounted"], s[0]["model"], s[1]["mounted"]), (True, "DataTraveler 3.0", False))
        self.assertIn("not mounted", vs.describe(s[1]))
        self.assertEqual(vs.parse_lsblk("not json"), [])


def ventoy_class(rules, name):
    """What Ventoy does with menu_class: the first rule whose key is a (case-sensitive) substring of the file name wins."""
    return next((r["class"] for r in rules if r["key"] in name), None)


@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class Dynamic(unittest.TestCase):
    def test_rules(self):
        classes = json.loads((PKG / "classes.json").read_text())
        titles = json.loads((PKG / "titles.json").read_text())
        rules = dynamic_rules(classes, titles)
        self.assertGreater(len(rules), 400)
        self.assertTrue(all(3 <= len(r["key"]) <= 30 for r in rules))
        for name, cls in (
            ("Fedora-Workstation-Live-x86_64-44-1.7.iso", "mg_fedora"),
            ("FEDORA-44.iso", "mg_fedora"),
            ("ubuntu-24.04.1-desktop-amd64.iso", "mg_ubuntu"),
            ("kubuntu-24.04.iso", "mg_kubuntu"),
            ("archlinux-2026.11.01-x86_64.iso", "mg_arch"),
            ("linuxmint-22-cinnamon-64bit.iso", "mg_linuxmint"),
            ("EndeavourOS_Mercury-2026.iso", "mg_endeavouros"),
            ("openSUSE-Tumbleweed-DVD-x86_64-Current.iso", "mg_opensuse"),
            ("Win11_24H2_English_x64.iso", "mg_windows11"),
            ("Win10_22H2_x64.iso", "mg_windows10"),
            ("debian-live-13.0-amd64-gnome.iso", "mg_debian"),
            ("gparted-live-1.6.iso", None),
        ):
            self.assertEqual(ventoy_class(rules, name), cls, name)


@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class RealNames(unittest.TestCase):
    def test_iso_names(self):
        classes = json.loads((PKG / "classes.json").read_text())
        titles = json.loads((PKG / "titles.json").read_text())
        rules = dynamic_rules(classes, titles)
        bad = []
        rows = [
            l.split("\t")
            for l in (ROOT / "tests/iso_names.txt").read_text().splitlines()
            if l and not l.startswith("#")
        ]
        for name, key in rows:
            c = ventoy_class(rules, name)
            got = c[3:] if c else "iso"
            if got != key:
                bad.append((name, key, got))
        self.assertGreater(len(rows), 100)
        self.assertEqual(bad, [])


@unittest.skipUnless((PKG / "res").is_dir() and (PKG / "res/1920x1080").is_dir(), "no built 1920x1080 package")
class DynamicStick(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "ventoy").mkdir()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_tool(self, style):
        (self.d / "ventoy/material-grub.conf").write_text(f"STYLE={style}\n")
        subprocess.run(
            [sys.executable, str(TOOL), str(self.d), "--pkg", str(PKG), "--res", "1920x1080"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads((self.d / "ventoy/ventoy.json").read_text()), self.d / "ventoy/themes/material_1920x1080"

    def test_every_class_has_an_icon_and_no_file_is_needed(
        self,
    ):  # a stick with NO ISO at all: the theme must already cover every class a rule or a Ventoy menu can produce
        for style in ("full", "list"):
            j, th = self.run_tool(style)
            need = {r["class"] for r in j["menu_class"]} | {
                "vtoyiso",
                "vtoydir",
                "vtoyret",
                "F5tool",
                "F4boot",
                "debug_reboot",
                "debug_halt",
                "debug_efisetup",
                "boot_windows",
                "second_normal",
                "second_grub2",
                "second_wimboot",
                "second_memdisk",
                "second_checksum",
                "second_return",
                "mg_pnlug",
            }  # second_*: Ventoy's boot-mode menu
            for c in need:
                self.assertTrue((th / "icons" / f"{c}.png").exists(), (style, c))
            th_w, th_h = 1920, 1080
            txt = (th / "theme.txt").read_text()
            self.assertIn(
                "mgrow_*.png", txt
            )  # every style has GRUB's own list; in rail / clean it lies below the scene
            self.assertTrue((th / "mgsel_c.png").exists())
            self.assertEqual(
                "mg:filename" in txt, style != "list", style
            )  # full screen: the file name pill under the title
            if style != "list":
                from PIL import Image as I

                self.assertEqual(
                    I.open(th / "icons/mg_fedora.png")
                    .convert("RGBA")
                    .getpixel((th_w // 2, round(th_h * 0.68) + 36))[3],
                    0,
                    "hole for the file-name pill in the ISO scene",
                )
                self.assertEqual(
                    I.open(th / "icons/second_normal.png").convert("RGBA").getpixel((int(th_w * 0.47) + 300, 148))[3],
                    0,
                    "hole at the first row of a menu scene",
                )
            self.assertEqual(
                [r["class"] for r in j["menu_class"][:32]], ["mg_pnlug"] * 32, "PNLug in any letter case comes first"
            )
            self.assertEqual(len({r["key"] for r in j["menu_class"][:32]}), 32)
            self.assertIn("PnLuG", {r["key"] for r in j["menu_class"][:32]})
            logo = Image.open(th / "machine-logo.png").convert("RGBA")
            px = [logo.getpixel((x, y)) for x in range(logo.width) for y in range(logo.height)]
            self.assertTrue(
                any(a > 200 and b > r + 40 for r, g, b, a in px), "the real Ventoy logo is blue, not a dark V"
            )


@unittest.skipUnless((PKG / "res").is_dir() and (PKG / "res/1920x1080").is_dir(), "no built 1920x1080 package")
class Stick(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "ventoy").mkdir()
        (self.d / "ISO").mkdir()
        for n in ("Fedora-44.iso", "ubuntu-24.04.iso", "Win11_x64.iso"):
            (self.d / "ISO" / n).write_bytes(b"")
        self.vj = self.d / "ventoy/ventoy.json"
        self.vj.write_text(
            json.dumps({"control": [{"VTOY_DEFAULT_MENU_MODE": "1"}], "menu_class": [{"key": "mine", "class": "x"}]})
        )

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_tool(self, *a):
        (self.d / "ventoy/material-grub.conf").write_text("MODE=snapshot\n")
        return subprocess.run(
            [sys.executable, str(TOOL), str(self.d), "--pkg", str(PKG), "--res", "1920x1080", *a],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_install_rerun_uninstall(self):
        orig = json.loads(self.vj.read_text())
        self.run_tool()
        self.run_tool()  # twice: idempotent
        j = json.loads(self.vj.read_text())
        self.assertEqual(j["control"], orig["control"])
        self.assertEqual(
            j["menu_class"][0], {"key": "mine", "class": "x"}
        )  # the user's settings and rules survive, theirs first
        self.assertEqual(len(j["menu_class"]), 1 + 32 + 3)
        self.assertEqual(j["theme"]["gfxmode"], "1920x1080")
        icons = self.d / "ventoy/themes/material_1920x1080/icons"
        for m in j["menu_class"][1:]:
            self.assertTrue((icons / f"{m['class']}.png").exists(), m)
        self.assertTrue((self.d / "ventoy/ventoy.json.material-grub.bak").exists())
        self.run_tool("--uninstall")
        self.assertEqual(json.loads(self.vj.read_text()), orig)
        self.assertFalse((self.d / "ventoy/themes/material_1920x1080").exists())


class Custom(unittest.TestCase):
    """overrides on the stick (ventoy/material-grub-overrides.json): per-file colour / icon / name, the single seed, and a clean uninstall."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "ventoy").mkdir()
        (self.d / "ISO").mkdir()
        for n in ("Fedora-Workstation-44.iso", "ubuntu-24.04.iso"):
            (self.d / "ISO" / n).write_bytes(b"")
        self.vj = self.d / "ventoy/ventoy.json"
        self.vj.write_text(json.dumps({"menu_alias": [{"image": "/ISO/mine.iso", "alias": "Mine"}]}))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_tool(self, conf, ov=None, *a):
        (self.d / "ventoy/material-grub.conf").write_text(conf)
        if ov is not None:
            (self.d / "ventoy/material-grub-overrides.json").write_text(json.dumps(ov))
        r = subprocess.run(
            [sys.executable, str(TOOL), str(self.d), "--pkg", str(PKG), "--res", "1920x1080", *a],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout, json.loads(self.vj.read_text())

    def check(self, conf):
        orig_alias = json.loads(self.vj.read_text())["menu_alias"]
        ov = {"entries": [{"match": {"title": "Fedora"}, "name": "Work laptop", "color": "#E95420"}]}
        out, j = self.run_tool(conf, ov)
        first = j["menu_class"][0]
        self.assertTrue(first["class"].startswith("mgu_"), first)
        self.assertIn(first["key"], "Fedora-Workstation-44.iso")
        icons = self.d / "ventoy/themes/material_1920x1080/icons"
        self.assertTrue((icons / f"{first['class']}.png").exists())
        self.assertIn({"image": "/ISO/Fedora-Workstation-44.iso", "alias": "Work laptop"}, j["menu_alias"])
        self.assertEqual(j["menu_alias"][0], orig_alias[0])  # the user's alias stays first
        for m in j["menu_class"]:
            self.assertTrue((icons / f"{m['class']}.png").exists(), m)
        self.run_tool(conf, ov, "--uninstall")
        self.assertEqual(json.loads(self.vj.read_text())["menu_alias"], orig_alias)
        self.assertNotIn("menu_class", json.loads(self.vj.read_text()))

    def test_dynamic_list(self):
        self.check("STYLE=list\n")

    def test_dynamic_full(self):
        self.check("STYLE=full\n")

    def test_snapshot_list(self):
        self.check("MODE=snapshot\nSTYLE=list\n")

    def test_single_seed_and_user_picture(self):
        from PIL import Image

        (self.d / "ventoy/material-grub-icons").mkdir()
        Image.new("RGBA", (64, 64), (20, 160, 20, 255)).save(self.d / "ventoy/material-grub-icons/logo.png")
        ov = {
            "seed": {"mode": "single", "color": "#7E57C2"},
            "entries": [{"match": {"title": "ubuntu"}, "icon": "file:logo.png"}],
        }
        out, j = self.run_tool("STYLE=list\n", ov)
        self.assertEqual(j["menu_class"][0]["class"][:4], "mgu_")
        self.assertNotIn("cannot read", out)

    def test_bad_overrides_are_ignored_with_a_message(self):
        out, j = self.run_tool("STYLE=list\n", {"seed": {"mode": "rainbow"}})
        self.assertIn("overrides:", out)
        self.assertFalse(any(m["class"].startswith("mgu_") for m in j["menu_class"]))


if __name__ == "__main__":
    unittest.main()
