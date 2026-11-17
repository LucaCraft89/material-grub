"""Unit tests for the Ventoy target (no Ventoy, no QEMU): menu_class key selection, name matching, a full run on a fake stick, idempotency and uninstall.
usage: python3 tests/test_ventoy.py   (the run on a fake stick is skipped when dist/material-grub is not built)"""
import importlib.machinery, importlib.util, json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; PKG = ROOT / "dist/material-grub"; TOOL = ROOT / "install/bin/material-grub-ventoy"

def load_funcs():
    """pick_key / key_of live in the tool script (no .py suffix, and it runs on import), so exec only the function definitions."""
    src = TOOL.read_text(); ns = {"re": __import__("re"), "Path": Path, "mgrub": None, "PKG": PKG}
    sys.path.insert(0, str(ROOT / "install/bin")); import mgrub; ns["mgrub"] = mgrub
    s = src.index("GENERIC = {"); e = src.index("\ndef dynamic_rules"); exec(src[s:e], ns)
    for name in ("pick_key", "key_of", "dynamic_rules"):
        s = src.index(f"def {name}("); e = src.index("\ndef ", s + 1) if "\ndef " in src[s + 1:] else len(src); exec(src[s:e], ns)
    return ns["pick_key"], ns["key_of"], ns["dynamic_rules"]
pick_key, key_of, dynamic_rules = load_funcs()

class Keys(unittest.TestCase):
    def test_never_the_whole_name_never_over_30(self):
        for n in ("a.iso", "Fedora-Workstation-Live-x86_64-44-1.7.iso", "x" * 80 + ".iso"):
            k = pick_key(n, []); self.assertIn(k, n); self.assertNotEqual(k, n); self.assertLessEqual(len(k), 30)
    def test_unique_among_others(self):
        others = ["Fedora-Workstation-Live-x86_64-44-1.6.iso", "Fedora-Workstation-Live-x86_64-43-1.6.iso"]
        n = "Fedora-Workstation-Live-x86_64-44-1.7.iso"; k = pick_key(n, others)
        self.assertIn(k, n); self.assertFalse(any(k in o for o in others))
    def test_no_unique_key(self):
        self.assertIsNone(pick_key("a.iso", ["a.iso.bak", "xa.iso"]))

@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class Names(unittest.TestCase):
    def test_keys(self):
        import mgrub; rules = mgrub.load_rules(PKG)
        for n, k in (("archlinux-2026.11.01-x86_64.iso", "arch"), ("Fedora-Workstation-Live-x86_64-44-1.7.iso", "fedora"), ("ubuntu-24.04.1-desktop-amd64.iso", "ubuntu"),
                     ("Win11_24H2_English_x64.iso", "windows11"), ("Win10_22H2_x64.iso", "windows10"), ("gparted-live-1.6.iso", "iso"), ("KALI-linux-2026.3.iso", "kali")):
            self.assertEqual(key_of(n, rules), k, n)

LSBLK = json.dumps({"blockdevices": [
    {"name": "sda", "path": "/dev/sda", "type": "disk", "model": "Samsung SSD", "children": [{"name": "sda1", "path": "/dev/sda1", "label": "EFI", "fstype": "vfat", "size": 600000000, "type": "part", "mountpoints": ["/boot/efi"]}]},
    {"name": "sdb", "path": "/dev/sdb", "type": "disk", "model": "DataTraveler 3.0 ", "children": [
        {"name": "sdb1", "path": "/dev/sdb1", "label": "Ventoy", "fstype": "exfat", "size": 59000000000, "type": "part", "mountpoints": ["/run/media/u/Ventoy"]},
        {"name": "sdb2", "path": "/dev/sdb2", "label": "VTOYEFI", "fstype": "vfat", "size": 33554432, "type": "part", "mountpoints": [None]}]},
    {"name": "sdc", "path": "/dev/sdc", "type": "disk", "model": "Other", "children": [
        {"name": "sdc1", "path": "/dev/sdc1", "label": "Ventoy", "fstype": "ntfs", "size": 1000000000, "type": "part", "mountpoints": [None]},
        {"name": "sdc2", "path": "/dev/sdc2", "label": "VTOYEFI", "fstype": "vfat", "size": 33554432, "type": "part", "mountpoints": [None]}]}]})
class Sticks(unittest.TestCase):
    def test_parse_lsblk(self):
        sys.path.insert(0, str(ROOT / "install")); import ventoy_sticks as vs
        s = vs.parse_lsblk(LSBLK); self.assertEqual([x["path"] for x in s], ["/run/media/u/Ventoy", "dev:/dev/sdc1"])      # the system disk has no VTOYEFI; VTOYEFI itself is never listed
        self.assertEqual((s[0]["mounted"], s[0]["model"], s[1]["mounted"]), (True, "DataTraveler 3.0", False)); self.assertIn("not mounted", vs.describe(s[1]))
        self.assertEqual(vs.parse_lsblk("not json"), [])

def ventoy_class(rules, name):
    """What Ventoy does with menu_class: the first rule whose key is a (case-sensitive) substring of the file name wins."""
    return next((r["class"] for r in rules if r["key"] in name), None)

@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class Dynamic(unittest.TestCase):
    def test_rules(self):
        classes = json.loads((PKG / "classes.json").read_text()); titles = json.loads((PKG / "titles.json").read_text()); rules = dynamic_rules(classes, titles)
        self.assertGreater(len(rules), 400); self.assertTrue(all(3 <= len(r["key"]) <= 30 for r in rules))
        for name, cls in (("Fedora-Workstation-Live-x86_64-44-1.7.iso", "mg_fedora"), ("FEDORA-44.iso", "mg_fedora"), ("ubuntu-24.04.1-desktop-amd64.iso", "mg_ubuntu"), ("kubuntu-24.04.iso", "mg_kubuntu"),
                          ("archlinux-2026.11.01-x86_64.iso", "mg_arch"), ("linuxmint-22-cinnamon-64bit.iso", "mg_linuxmint"), ("EndeavourOS_Mercury-2026.iso", "mg_endeavouros"),
                          ("openSUSE-Tumbleweed-DVD-x86_64-Current.iso", "mg_opensuse"), ("Win11_24H2_English_x64.iso", "mg_windows11"), ("Win10_22H2_x64.iso", "mg_windows10"),
                          ("debian-live-13.0-amd64-gnome.iso", "mg_debian"), ("gparted-live-1.6.iso", None)):
            self.assertEqual(ventoy_class(rules, name), cls, name)

@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class RealNames(unittest.TestCase):
    def test_iso_names(self):
        classes = json.loads((PKG / "classes.json").read_text()); titles = json.loads((PKG / "titles.json").read_text()); rules = dynamic_rules(classes, titles); bad = []
        rows = [l.split("\t") for l in (ROOT / "tests/iso_names.txt").read_text().splitlines() if l and not l.startswith("#")]
        for name, key in rows:
            c = ventoy_class(rules, name); got = c[3:] if c else "iso"
            if got != key: bad.append((name, key, got))
        self.assertGreater(len(rows), 100); self.assertEqual(bad, [])

@unittest.skipUnless((PKG / "res").is_dir() and (PKG / "res/1920x1080").is_dir(), "no built 1920x1080 package")
class DynamicStick(unittest.TestCase):
    def setUp(self): self.d = Path(tempfile.mkdtemp()); (self.d / "ventoy").mkdir()
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)
    def run_tool(self, style):
        (self.d / "ventoy/material-grub.conf").write_text(f"STYLE={style}\n")
        subprocess.run([sys.executable, str(TOOL), str(self.d), "--pkg", str(PKG), "--res", "1920x1080"], capture_output=True, text=True, check=True)
        return json.loads((self.d / "ventoy/ventoy.json").read_text()), self.d / "ventoy/themes/material_1920x1080"
    def test_every_class_has_an_icon_and_no_file_is_needed(self):       # a stick with NO ISO at all: the theme must already cover every class a rule or a Ventoy menu can produce
        for style in ("rail", "clean", "list"):
            j, th = self.run_tool(style); need = {r["class"] for r in j["menu_class"]} | {"vtoyiso", "vtoydir", "vtoyret", "F5tool", "F4boot", "debug_reboot", "debug_halt", "debug_efisetup", "boot_windows"}
            for c in need: self.assertTrue((th / "icons" / f"{c}.png").exists(), (style, c))
            txt = (th / "theme.txt").read_text(); self.assertEqual("mgrow_*.png" in txt, style == "list", style)
            if style == "list": self.assertTrue((th / "mgsel_c.png").exists())

@unittest.skipUnless((PKG / "res").is_dir() and (PKG / "res/1920x1080").is_dir(), "no built 1920x1080 package")
class Stick(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); (self.d / "ventoy").mkdir(); (self.d / "ISO").mkdir()
        for n in ("Fedora-44.iso", "ubuntu-24.04.iso", "Win11_x64.iso"): (self.d / "ISO" / n).write_bytes(b"")
        self.vj = self.d / "ventoy/ventoy.json"; self.vj.write_text(json.dumps({"control": [{"VTOY_DEFAULT_MENU_MODE": "1"}], "menu_class": [{"key": "mine", "class": "x"}]}))
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)
    def run_tool(self, *a):
        (self.d / "ventoy/material-grub.conf").write_text("MODE=snapshot\n")
        return subprocess.run([sys.executable, str(TOOL), str(self.d), "--pkg", str(PKG), "--res", "1920x1080", *a], capture_output=True, text=True, check=True)
    def test_install_rerun_uninstall(self):
        orig = json.loads(self.vj.read_text()); self.run_tool(); self.run_tool()      # twice: idempotent
        j = json.loads(self.vj.read_text())
        self.assertEqual(j["control"], orig["control"]); self.assertEqual(j["menu_class"][0], {"key": "mine", "class": "x"})   # the user's settings and rules survive, theirs first
        self.assertEqual(len(j["menu_class"]), 1 + 3); self.assertEqual(j["theme"]["gfxmode"], "1920x1080")
        icons = self.d / "ventoy/themes/material_1920x1080/icons"
        for m in j["menu_class"][1:]: self.assertTrue((icons / f"{m['class']}.png").exists(), m)
        self.assertTrue((self.d / "ventoy/ventoy.json.material-grub.bak").exists())
        self.run_tool("--uninstall"); self.assertEqual(json.loads(self.vj.read_text()), orig); self.assertFalse((self.d / "ventoy/themes/material_1920x1080").exists())

if __name__ == "__main__": unittest.main()
