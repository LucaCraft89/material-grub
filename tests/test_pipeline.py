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
