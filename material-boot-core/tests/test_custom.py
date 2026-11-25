"""material_boot.custom.apply: how overrides rename and recolour entries. Needs a built material-grub package: MATERIAL_PKG=<dir> (skipped without).
(The tests that run the material-grub-scenes command on an overrides.json stay in material-grub.)"""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = Path(os.environ.get("MATERIAL_PKG", "/nonexistent/material-grub-package"))
sys.path.insert(0, str(ROOT))


@unittest.skipUnless((PKG / "classes.json").is_file(), "no built package (set MATERIAL_PKG)")
class Custom(unittest.TestCase):
    def test_a_distro_wide_name_does_not_rename_advanced_options(self):
        from material_boot import custom as mgcustom
        from material_boot import overrides as mgoverrides
        from material_boot import scenes as mgscenes

        ov, _, _ = mgoverrides.validate({"entries": [{"match": {"key": "fedora"}, "name": "Work laptop"}]})
        ents = [
            {"class": "mg_1", "key": "fedora", "kind": "kernel", "level": "top", "title": "Fedora"},
            {
                "class": "mg_2",
                "key": "fedora",
                "kind": "advanced",
                "level": "top",
                "title": "Advanced options for Fedora",
            },
            {"class": "mg_3", "key": "fedora", "kind": "rescue", "level": "top", "title": "Fedora rescue"},
        ]
        R = mgscenes.Renderer(PKG, 1080)
        mgcustom.apply(R, ov, ents, PKG, "16x9", (1920, 1080), json.loads((PKG / "classes.json").read_text()))
        self.assertEqual([R.title_for(e) for e in ents], ["Work laptop", "Advanced", "Rescue"])
        ov, _, _ = mgoverrides.validate({"entries": [{"match": {"class": "mg_2"}, "name": "More kernels"}]})
        ents2 = [dict(e, key="fedora") for e in ents]
        mgcustom.apply(R, ov, ents2, PKG, "16x9", (1920, 1080), json.loads((PKG / "classes.json").read_text()))
        self.assertEqual(R.title_for(ents2[1]), "More kernels")  # asked for this very entry: it is renamed


if __name__ == "__main__":
    unittest.main()
