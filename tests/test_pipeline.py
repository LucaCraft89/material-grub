"""Pipeline test on a throw-away fake /boot (needs a built package and Pillow):
static grub.cfg edit (immutable mode), annotation, BLS mirrors, scenes, idempotency, bootupd-style rewrite, restore.
usage: python3 tests/test_pipeline.py [PKG_DIR]   (default dist/material-grub; skipped when it is missing)"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PKG = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ROOT / "dist/material-grub")
BIN = ROOT / "install/bin"
STATIC = "set timeout=5\nset timeout_style=hidden\nset menu_hide_ok=1\ninsmod part_gpt\ninsmod blscfg\nblscfg\n"
ENTRY = "title Fedora Linux {v} (Silverblue) (ostree:{n})\nversion {n}\noptions root=UUID=x rw\nlinux /vmlinuz-{n}\ninitrd /initrd-{n}\n"
def sha(p): return hashlib.sha1(Path(p).read_bytes()).hexdigest()

@unittest.skipUnless((PKG / "res").is_dir(), "no built package (run scripts/package.py --res 1920x1080 first)")
class Pipeline(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.boot = self.d / "boot"; (self.boot / "grub2").mkdir(parents=True)
        self.cfg = self.boot / "grub2/grub.cfg"; self.cfg.write_text(STATIC)
        self.entries = self.boot / "loader/entries"; self.entries.mkdir(parents=True)
        for n, v in ((2, "44.20260301.0"), (1, "44.20260201.0")): (self.entries / f"ostree-{n}-fedora.conf").write_text(ENTRY.format(v=v, n=n))
        self.bk = self.d / "backup"; self.state = self.d / "state/entries.json"
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)
    def run_all(self):
        py = sys.executable; gd = self.boot / "grub2"
        subprocess.run([py, BIN / "material-grub-static", self.cfg, "--mode", "1920x1080", "--pkg", PKG, "--backup", self.bk], check=True, capture_output=True)
        subprocess.run([py, BIN / "material-grub-classes", self.cfg, "--pkg", PKG, "--bls", self.entries, "--loader", self.boot / "loader", "--mirrors", gd / "material",
                        "--mirrorbase", "/grub2/material", "--fallback-all", "--state", self.state], check=True, capture_output=True)
        subprocess.run([py, BIN / "material-grub-scenes", "--theme", gd / "themes/material", "--pkg", PKG, "--state", self.state], check=True, capture_output=True)
    def test_blscfg_variants(self):
        gd = self.boot / "grub2"
        for body, structured in (("    blscfg --enable-fallback\n", True), ("blscfg --path /loader/entries\n", False), ("blscfg --show-default\n", False)):
            self.cfg.write_text(STATIC.replace("blscfg\n", body)); shutil.rmtree(self.bk, ignore_errors=True); shutil.rmtree(self.state.parent, ignore_errors=True)
            self.run_all(); t = self.cfg.read_text()
            self.assertIn("set theme=$prefix/themes/material/theme.txt", t, "theme must load whatever the blscfg form")
            self.assertEqual("material-top" in t, structured, body)
            if structured: self.assertIn("    set blsdir=", t); self.assertIn("blscfg --enable-fallback", t)
            else: self.assertIn(body.strip(), t)
    def test_no_blscfg_at_all(self):      # classic menuentry system (Debian/Arch style) run through the static path: theme + entries, no mirrors
        self.cfg.write_text("set timeout=5\nmenuentry 'Arch Linux' --class arch --class gnu-linux { true }\nsubmenu 'Advanced options for Arch' { menuentry 'Arch fallback' { true } }\n")
        self.run_all(); t = self.cfg.read_text()
        self.assertIn("static theme begin", t); self.assertNotIn("material-top", t); self.assertIn("--class arch", t)
        self.assertLess(t.index("static theme begin"), t.index("menuentry 'Arch Linux'"))
    def test_conf(self):
        conf = self.d / "m.conf"; conf.write_text("RAW_NAME=off\nCOUNTDOWN=off\nLOGO=off\nTIMEOUT=9\n"); os.environ["MATERIAL_CONF"] = str(conf)
        try: self.run_all()
        finally: del os.environ["MATERIAL_CONF"]
        th = (self.boot / "grub2/themes/material/theme.txt").read_text()
        for gone in ('id = "__timeout__"', "machine-logo.png", 'item_height = 34'): self.assertNotIn(gone, th)
        self.assertIn("boot_menu", th); self.assertIn("set timeout=9", self.cfg.read_text())
        self.assertFalse((self.boot / "grub2/themes/material/machine-logo.png").exists())
    def test_menu_order_and_unique_plain_classes(self):
        self.cfg.write_text(STATIC + "menuentry 'Windows Boot Manager (on /dev/sda1)' { true }\nmenuentry 'Windows Boot Manager (on /dev/sdb1)' { true }\n")
        self.run_all(); menu = json.loads((self.state.parent / "menu.json").read_text()); ents = {e["class"]: e for e in json.loads(self.state.read_text())}
        top = [ents[c] for c in menu[0]["items"]]
        self.assertEqual([e["kind"] for e in top], ["kernel", "advanced", "plain", "plain", "plain", "plain"], "default kernel, Advanced, then the grub.cfg entries in file order")
        self.assertEqual(len({e["class"] for e in top}), 6, "plain entries (two Windows installs) need unique classes")
        self.assertEqual(menu[1]["level"], "adv"); self.assertEqual(menu[1]["parent"], top[1]["class"]); self.assertEqual(len(menu[1]["items"]), 1)
        t = self.cfg.read_text(); self.assertIn("--class windows11", t); self.assertIn(f"--class {top[2]['class']} --class windows11", t)
    def test_runtime_cookie_and_hints(self):      # cookie and hint pills are drawn at config time: conf switches change the scenes, the build-time bg has neither
        from PIL import Image, ImageChops
        def scene(conf_text):
            conf = self.d / "m.conf"; conf.write_text(conf_text); os.environ["MATERIAL_CONF"] = str(conf)
            try: self.run_all()
            finally: del os.environ["MATERIAL_CONF"]
            return Image.open(next((self.boot / "grub2/themes/material/icons").glob("mg_*.png"))).convert("RGB")
        full = scene(""); nohint = scene("HINTS=off\n"); nocookie = scene("COOKIE=off\n"); neither = scene("HINTS=off\nCOOKIE=off\n")
        W, H = full.size
        self.assertIsNotNone(ImageChops.difference(full, nohint).getbbox()); self.assertIsNotNone(ImageChops.difference(full, nocookie).getbbox())
        self.assertGreater(ImageChops.difference(full, nohint).getbbox()[1], H * 0.8, "hints are at the bottom")
        self.assertGreater(ImageChops.difference(full, nocookie).getbbox()[0], W * 0.8, "cookie is top right")
        bg = Image.open(sorted((PKG / "scenes/16x9/bg").glob("fedora.png"))[0]).convert("RGB")
        self.assertEqual(bg.getpixel((W - 150, 140)), bg.getpixel((W // 2, 40)), "the build-time bg must not carry the cookie")
    def test_non_latin_titles(self):      # pills fall back to another installed font; the theme ships GRUB's unicode.pf2 when the system has it
        (self.entries / "ostree-4-fedora.conf").write_text(ENTRY.format(v="44.1", n=4).replace("(Silverblue)", "(Рабочая станция 日本語)"))
        self.run_all(); self.assertTrue(any((self.boot / "grub2/themes/material/icons").glob("mg_*.png")))
    def test_flow(self):
        self.run_all(); t = self.cfg.read_text()
        self.assertIn("set theme=$prefix/themes/material/theme.txt", t); self.assertIn("material-fallback", t); self.assertIn("'Restart'", t)
        self.assertLess(t.index("static theme begin"), t.index("structured BLS"), "theme block must come before the menu")
        gd = self.boot / "grub2"
        self.assertEqual(len(list((gd / "material/material-top").glob("*.conf"))), 1); self.assertEqual(len(list((gd / "material/material-adv").glob("*.conf"))), 1)
        for conf in (gd / "material").rglob("*.conf"): self.assertNotIn("\n\n", conf.read_text(), "blank line stops GRUB's BLS parser")
        self.assertTrue(any((gd / "themes/material/icons").glob("mg_*.png")))
        h = sha(self.cfg); self.run_all(); self.assertEqual(sha(self.cfg), h, "second run must not rewrite grub.cfg (path unit would loop)")
        # ostree swaps the deployment: newest entry appears, mirrors follow
        (self.entries / "ostree-3-fedora.conf").write_text(ENTRY.format(v="44.20260401.0", n=3)); self.run_all()
        top = next((gd / "material/material-top").glob("*.conf")).read_text(); self.assertIn("ostree:3", top)
        self.assertEqual(sha(self.cfg), h)
        # bootupd rewrites the static file: everything is re-applied identically
        self.cfg.write_text(STATIC); self.run_all(); self.assertEqual(sha(self.cfg), h)
        # restore gives back the pristine file
        subprocess.run([sys.executable, BIN / "material-grub-static", self.cfg, "--restore", "--backup", self.bk], check=True, capture_output=True)
        self.assertEqual(self.cfg.read_text(), STATIC)

if __name__ == "__main__":
    sys.argv = [sys.argv[0]]; unittest.main()
