"""mgpalette (the vendored colour science the installed tools use) must give exactly what the build's pinned materialyoucolor gives.
The build copy is only importable in a build venv, so that half is skipped elsewhere. usage: python3 tests/test_palette.py"""

import random
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import mgpalette  # noqa: E402

SEEDS = ["#0B3D2E", "#294172", "#E95420", "#A80030", "#FFB300", "#808080", "#101010", "#FFFFFF", "#000000"]
SEEDS += ["#%06X" % random.Random(7).randrange(1 << 24) for _ in range(40)]


class Palette(unittest.TestCase):
    def test_shape(self):
        for dark in (True, False):
            p = mgpalette.scheme("#0B3D2E", dark)
            self.assertEqual(tuple(p), mgpalette.ROLES)
            self.assertTrue(all(re.fullmatch(r"#[0-9A-F]{6}", v) for v in p.values()))

    def test_dark_and_light_differ(self):
        d, l = mgpalette.scheme("#E95420", True), mgpalette.scheme("#E95420", False)
        self.assertNotEqual(d["surface"], l["surface"])

    def test_grey_seed_is_grey(self):
        for v in mgpalette.scheme("#808080", True).values():
            r, g, b = (int(v[i : i + 2], 16) for i in (1, 3, 5))
            self.assertLessEqual(max(r, g, b) - min(r, g, b), 2)

    def test_known_value(self):  # the green seed of the theme: matches the build's primary
        self.assertEqual(mgpalette.scheme("#0B3D2E", True)["primary"], "#E7FFF2")

    def test_vendored_copy_is_the_same_as_the_pip_one(self):
        venv = ROOT / ".venv/bin/python"
        if not venv.exists():
            self.skipTest("no .venv with materialyoucolor")
        code = (
            "import sys,json; sys.path.insert(0,%r); sys.path.insert(0,%r); import palettes;"
            "out={}\n"
            "for s in %r:\n"
            "  for d in (True,False):\n"
            "    palettes.SCHEME='dark' if d else 'light'; out[s+str(d)]=palettes.scheme(s)\n"
            "print(json.dumps(out))"
        ) % (str(ROOT / "scripts"), str(ROOT / "scripts"), SEEDS)
        import json

        r = subprocess.run([str(venv), "-c", code], capture_output=True, text=True)
        if r.returncode:
            self.skipTest("the .venv cannot import the build modules: " + r.stderr[-200:])
        ref = json.loads(r.stdout)
        for s in SEEDS:
            for d in (True, False):
                self.assertEqual(ref[s + str(d)], mgpalette.scheme(s, d), (s, d))


if __name__ == "__main__":
    unittest.main()
