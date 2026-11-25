"""How material-grub finds material-boot-core, what it says when it cannot, and that the old module names are the core's modules. stdlib only.
Needs the core: material-boot-core next to (or inside) the checkout, or MATERIAL_LIB. usage: python3 tests/test_core_link.py"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "install/bin"
sys.path.insert(0, str(BIN))
import mgcore  # noqa: E402

MOVED = {
    "mgoverrides": "overrides",
    "mgseeds": "seeds",
    "mgpalette": "palette",
    "mgscenes": "scenes",
    "mgcustom": "custom",
    "mgmigrate": "migrate",
    "mgpresets": "presets",
}


def fake_core(d, version="1.0.0", api=2):
    d = Path(d)
    (d / "material_boot").mkdir(parents=True)
    (d / "material_boot/__init__.py").write_text(f'__version__ = "{version}"\nCORE_API = {api}\n')
    return d


class Search(unittest.TestCase):
    def test_an_explicit_path_is_the_only_one_tried(self):
        with mock.patch.dict(os.environ, {"MATERIAL_LIB": "/nonexistent/lib"}):
            self.assertEqual(mgcore.candidates(), [Path("/nonexistent/lib")])
            self.assertIsNone(mgcore.find())  # no quiet fallback to some other copy

    def test_without_it_the_system_comes_first_then_the_checkouts(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MATERIAL_LIB", None)
            c = [str(p) for p in mgcore.candidates()]
        self.assertEqual(c[:3], list(mgcore.SYSTEM))
        self.assertTrue(all(p.endswith("material-boot-core") for p in c[3:]))
        self.assertIn(str(ROOT / "material-boot-core"), c)  # inside the checkout (what CI does)
        self.assertIn(str(ROOT.parent / "material-boot-core"), c)  # next to it

    def test_a_checkout_directory_is_recognised(self):
        with tempfile.TemporaryDirectory() as t:
            core = fake_core(Path(t) / "core")
            with mock.patch.dict(os.environ, {"MATERIAL_LIB": str(core)}):
                self.assertEqual(mgcore.find(), core)

    def test_the_system_path_is_what_an_installed_tool_uses(self):
        self.assertIn("/usr/share/material-boot/lib", mgcore.SYSTEM)
        self.assertIsNone(mgcore.system()) if not Path("/usr/share/material-boot/lib/material_boot").exists() else None


class Refusals(unittest.TestCase):
    def run_py(self, code, **env):
        e = dict(os.environ, **env)
        return subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=e, cwd=tempfile.gettempdir()
        )

    def test_a_missing_core_is_a_message_that_says_what_to_install(self):
        r = self.run_py(f"import sys; sys.path.insert(0, {str(BIN)!r}); import mgcore", MATERIAL_LIB="/nonexistent/lib")
        self.assertEqual(r.returncode, 1)
        self.assertIn("material-boot-core is not installed", r.stderr)
        self.assertIn("/nonexistent/lib", r.stderr)
        self.assertIn("bundle", r.stderr)

    def test_a_core_that_is_too_old_or_speaks_another_api(self):
        for version, api, text in (("0.9.0", 2, "does not fit"), ("1.0.0", 1, "plugin API 1")):
            with tempfile.TemporaryDirectory() as t:
                core = fake_core(Path(t) / "core", version, api)
                r = self.run_py(f"import sys; sys.path.insert(0, {str(BIN)!r}); import mgcore", MATERIAL_LIB=str(core))
                self.assertEqual(r.returncode, 1, (version, api))
                self.assertIn(text, r.stderr)
                self.assertIn("Update whichever of the two is older", r.stderr)

    def test_a_newer_core_is_fine(self):
        with tempfile.TemporaryDirectory() as t:
            core = fake_core(Path(t) / "core", "1.4.2", 2)
            r = self.run_py(
                f"import sys; sys.path.insert(0, {str(BIN)!r}); import mgcore; print(mgcore.ensure())",
                MATERIAL_LIB=str(core),
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(r.stdout.strip()), core)


class InstallerNeedsTheCore(unittest.TestCase):
    """A real install without the core on the system would leave tools that cannot start: refused before anything is touched."""

    def installer(self, **modes):
        sys.path.insert(0, str(ROOT / "install"))
        import installer

        inst = installer.Installer([])
        for k in ("ventoy", "stage", "preview", "dry", "uninstall"):
            setattr(inst, k, modes.get(k, False))
        return inst

    def test_a_real_install_is_refused_without_the_core_on_the_system(self):
        with mock.patch.object(mgcore, "system", return_value=None):
            with self.assertRaises(SystemExit) as e:
                self.installer().check_core()
        self.assertEqual(e.exception.code, 1)

    def test_the_message_says_what_to_do(self):
        import io
        from contextlib import redirect_stderr

        err = io.StringIO()
        with mock.patch.object(mgcore, "system", return_value=None), redirect_stderr(err), self.assertRaises(
            SystemExit
        ):
            self.installer().check_core()
        self.assertIn("material-boot-core is not installed on this system", err.getvalue())
        self.assertIn("/usr/share/material-boot/lib", err.getvalue())
        self.assertIn("bundle", err.getvalue())

    def test_the_modes_that_install_nothing_on_the_system_do_not_need_it(self):
        with mock.patch.object(mgcore, "system", return_value=None):
            for mode in ("ventoy", "stage", "preview", "dry", "uninstall"):
                self.installer(**{mode: True}).check_core()  # does not raise

    def test_with_the_core_installed_it_goes_on(self):
        with mock.patch.object(mgcore, "system", return_value=Path("/usr/share/material-boot/lib")):
            self.installer().check_core()


class ExportsWhatItFound(unittest.TestCase):
    """The installer builds in a temporary copy of the tree, and tests stage a copy of the package: the programs they start must find the same core."""

    def test_the_core_found_is_exported_to_the_children(self):
        import shutil

        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            bin_ = t / "repo/install/bin"
            bin_.mkdir(parents=True)
            shutil.copy(BIN / "mgcore.py", bin_ / "mgcore.py")
            core = fake_core(
                t / "repo/material-boot-core"
            )  # inside the checkout, found by walking up: no environment variable set
            env = {k: v for k, v in os.environ.items() if k != "MATERIAL_LIB"}
            code = (
                f"import sys; sys.path.insert(0, {str(bin_)!r}); import mgcore, os; print(os.environ['MATERIAL_LIB'])"
            )
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=t)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(r.stdout.strip()), core)

    def test_an_explicit_value_is_kept(self):
        with tempfile.TemporaryDirectory() as t:
            core = fake_core(Path(t) / "core")
            code = f"import sys; sys.path.insert(0, {str(BIN)!r}); import mgcore, os; print(os.environ['MATERIAL_LIB'])"
            r = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                env=dict(os.environ, MATERIAL_LIB=str(core)),
            )
            self.assertEqual(Path(r.stdout.strip()), core)


class Shims(unittest.TestCase):
    def test_each_old_name_is_the_cores_module(self):
        import importlib

        import material_boot

        for old, new in MOVED.items():
            with self.subTest(old):
                a = importlib.import_module(old)
                b = importlib.import_module(f"material_boot.{new}")
                self.assertIs(a, b)
                self.assertTrue(
                    Path(a.__file__).resolve().is_relative_to(Path(material_boot.__file__).resolve().parent)
                )

    def test_the_partly_moved_modules_still_offer_the_old_names(self):
        import mgdetect
        import mgrub
        from material_boot import conf, state, titles

        for name in ("load_conf", "write_conf", "CONF_DEFAULTS", "CONF_CHOICES"):
            self.assertIs(getattr(mgrub, name), getattr(conf, name), name)
        for name in ("parse_title", "key_for", "uid", "kind_of", "load_rules"):
            self.assertIs(getattr(mgrub, name), getattr(titles, name), name)
        for name in ("read", "record", "version_tuple", "owner_of", "state_path"):
            self.assertIs(getattr(mgdetect, name), getattr(state, name), name)
        # and what stayed is GRUB's own
        self.assertEqual(mgrub.snap("1920x1080"), "1920x1080")
        self.assertTrue(hasattr(mgrub, "apply_conf_to_theme") and hasattr(mgrub, "bls_call"))
        self.assertFalse(hasattr(mgdetect, "__nope__"))
        self.assertTrue(callable(mgdetect.detect))


if __name__ == "__main__":
    unittest.main()
