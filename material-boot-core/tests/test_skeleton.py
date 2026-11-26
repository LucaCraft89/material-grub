import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import material_boot  # noqa: E402


class Skeleton(unittest.TestCase):
    def test_version_is_one_string_everywhere(self):
        v = (ROOT / "VERSION").read_text().strip()
        self.assertRegex(v, r"^\d+\.\d+\.\d+$")
        self.assertEqual(material_boot.__version__, v)
        m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
        self.assertEqual(m.group(1), v)

    def test_levels_with_the_other_repositories(self):
        # decision 18 of the plan: the three repositories start level at 1.0.0
        self.assertEqual(material_boot.__version__, "1.0.0")

    def test_plugin_api(self):
        self.assertEqual(material_boot.CORE_API, 2)

    def test_imports_with_nothing_installed(self):
        # the core must import on a bare system: Pillow is imported by the modules that draw (scenes, custom), never by the package or the pure
        # modules. Checked in a fresh interpreter, so the order of the tests (some of which import Pillow) cannot matter.
        code = (
            "import sys; import material_boot; from material_boot import overrides, palette, seeds; "
            "sys.exit(1 if 'PIL' in sys.modules else 0)"
        )
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
