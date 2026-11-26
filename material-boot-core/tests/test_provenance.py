"""Moved code must be the code that was there: every definition that was moved out of material-grub equals the original, statement for statement.

Needs a material-grub checkout at the commit named in each module's docstring: MATERIAL_GRUB=<dir> (skipped without; CI checks it out). The comparison is
on the syntax tree, so formatting and comments do not matter, but every expression does. Modules that were adapted on the way (palette, scenes, custom)
are not listed: their differences are small and are shown in the pull request that moved them.

To record a new move, add a line to PROVENANCE: (core file, original file, names) with the names of the top-level definitions that were moved, or None
when the whole file was copied.
"""

import ast
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRUB = Path(os.environ["MATERIAL_GRUB"]) if os.environ.get("MATERIAL_GRUB") else None

PROVENANCE = [
    ("material_boot/overrides.py", "install/bin/mgoverrides.py", None),
    ("material_boot/seeds.py", "install/bin/mgseeds.py", None),
    (
        "material_boot/conf.py",
        "install/bin/mgrub.py",
        ["CONF_DEFAULTS", "CONF_CHOICES", "load_conf", "_conf_ok", "write_conf"],
    ),
    ("material_boot/titles.py", "install/bin/mgrub.py", ["load_rules", "key_for", "uid", "parse_title", "kind_of"]),
    ("material_boot/catalog.py", "scripts/catalog.py", ["D", "X", "ENTRIES", "SEEDS", "CLASSES"]),
    ("material_boot/catalog.py", "install/bin/mgrub.py", ["GENERIC"]),
    (
        "material_boot/state.py",
        "install/bin/mgdetect.py",
        ["STATE_VERSION", "version_tuple", "_state_dir", "state_path", "read", "write", "record", "owner_of"],
    ),
    ("material_boot/events.py", "install/installer.py", ["LineEvents", "Tee", "open_log"]),
    (
        "material_boot/presets.py",
        "install/bin/mgpresets.py",
        [
            "FORMAT",
            "CONF_KEYS",
            "NAME",
            "MAX_ICON",
            "preset_dir",
            "check_name",
            "make",
            "build",
            "validate",
            "save",
            "listing",
            "apply",
            "load",
            "delete",
        ],
    ),
    (
        "material_boot/migrate.py",
        "install/bin/mgmigrate.py",
        ["Step", "ConfSamples", "STEPS", "context", "steps_for", "plan", "backup_dir", "_rel", "run"],
    ),
]


def definitions(tree):
    """{name: dump of the node} for the top-level functions, classes and plain assignments."""
    out = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out[n.name] = ast.dump(n)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = ast.dump(n.value)
    return out


@unittest.skipUnless(GRUB and GRUB.is_dir(), "no material-grub checkout (set MATERIAL_GRUB)")
class Provenance(unittest.TestCase):
    def test_every_moved_definition_is_the_original(self):
        for core_file, orig_file, names in PROVENANCE:
            with self.subTest(core=core_file, original=orig_file):
                a = ast.parse((ROOT / core_file).read_text())
                b = ast.parse((GRUB / orig_file).read_text())
                if names is None:
                    self.assertEqual(ast.dump(a), ast.dump(b), "the whole file should be a copy")
                    continue
                da, db = definitions(a), definitions(b)
                for n in names:
                    self.assertIn(n, da, f"{n} is not defined in {core_file}")
                    self.assertIn(n, db, f"{n} is not defined in {orig_file}")
                    self.assertEqual(da[n], db[n], f"{n} differs from the original")


if __name__ == "__main__":
    unittest.main()
