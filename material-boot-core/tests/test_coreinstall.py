"""The core's own install part (material_boot.coreinstall): files in place, the shared data built for the scheme, atomic swaps. Real data build on a staged root
(needs Pillow and rsvg-convert or ImageMagick; skipped without)."""

import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import material_boot  # noqa: E402
from material_boot import coreinstall as ci  # noqa: E402

CAN_BUILD = not ci.missing_tools()


def make_bundle(dest):
    """What a bundle holds for the core: lib/material_boot, scripts/build_data.py, assets/, bin/material-boot (copied from this checkout)."""
    dest = Path(dest)
    ign = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(ROOT / "material_boot", dest / "lib/material_boot", ignore=ign)
    (dest / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts/build_data.py", dest / "scripts/build_data.py")
    shutil.copytree(ROOT / "assets", dest / "assets")
    (dest / "bin").mkdir()
    shutil.copy(ROOT / "bin/material-boot", dest / "bin/material-boot")
    return dest


def ctx(root, source=None, how="source", scheme="dark", dry=False):
    return SimpleNamespace(root=str(root), source=source, how=how, conf={"SCHEME": scheme}, dry_run=dry)


@unittest.skipUnless(CAN_BUILD, "needs Pillow and rsvg-convert (or ImageMagick)")
class Install(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bundle = make_bundle(Path(cls.tmp.name) / "bundle")
        cls.root = Path(cls.tmp.name) / "root"  # one real install, shared by the read-only tests
        cls.result = ci.hook_install(ctx(cls.root, cls.bundle))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.p = ci.prefix(self.root)

    def test_the_files_are_in_place(self):
        self.assertTrue(self.result["changed"])
        for d in ci.COPIED:
            self.assertTrue((self.p / d).is_dir(), d)
        self.assertTrue((self.p / "plugins.d").is_dir())
        self.assertEqual((self.p / "lib/material_boot/VERSION").read_text().strip(), material_boot.__version__)

    def test_the_command_is_installed_executable(self):
        shim = ci.shim_path(self.root)
        self.assertTrue(shim.is_file())
        self.assertTrue(stat.S_IMODE(shim.stat().st_mode) & 0o111)
        self.assertEqual(shim.read_text(), (self.bundle / "bin/material-boot").read_text())

    def test_the_shared_data_is_built_for_the_scheme(self):
        for f in ci.DATA_FILES:
            self.assertTrue((self.p / "data" / f).is_file(), f)
        self.assertEqual(ci.data_scheme(self.root), "dark")
        self.assertGreater(len(list((self.p / "data/glyphs").glob("*.png"))), 50)
        self.assertTrue((self.p / "data/fonts/GoogleSansFlex-VF.ttf").is_file())

    def test_verify_and_detect_say_it_is_healthy(self):
        self.assertEqual(ci.hook_verify(ctx(self.root, self.bundle)), [])
        d = ci.hook_detect(ctx(self.root, self.bundle))
        self.assertEqual((d["found"], d["version"], d["missing"]), (True, material_boot.__version__, []))

    def test_the_installed_library_runs_from_where_it_is(self):
        import subprocess

        r = subprocess.run(
            [sys.executable, "-c", "import material_boot; print(material_boot.__version__)"],
            env=dict(os.environ, PYTHONPATH=str(self.p / "lib")),
            capture_output=True,
            text=True,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(r.stdout.strip(), material_boot.__version__, r.stderr)

    def test_the_data_matches_what_a_checkout_builds(self):
        import subprocess

        out = Path(self.tmp.name) / "fresh"
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_data.py"), "--out", str(out)], check=True, capture_output=True
        )
        for f in ci.DATA_FILES:
            self.assertEqual((out / f).read_bytes(), (self.p / "data" / f).read_bytes(), f)


@unittest.skipUnless(CAN_BUILD, "needs Pillow and rsvg-convert (or ImageMagick)")
class Changes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = make_bundle(Path(self.tmp.name) / "bundle")
        self.root = Path(self.tmp.name) / "root"
        self.p = ci.prefix(self.root)
        ci.hook_install(ctx(self.root, self.bundle))

    def test_a_package_install_builds_the_data_and_copies_nothing(self):
        shutil.rmtree(self.p / "data")
        before = (self.p / "lib/material_boot/__init__.py").stat().st_mtime_ns
        r = ci.hook_install(
            ctx(self.root, self.bundle, how="package")
        )  # even with a bundle at hand, a package has laid its files itself
        self.assertTrue((self.p / "data/palettes.json").is_file())
        self.assertEqual((self.p / "lib/material_boot/__init__.py").stat().st_mtime_ns, before)
        self.assertEqual(r["notes"], ["built the shared data for the dark scheme"])

    def test_nothing_to_do_when_everything_is_there(self):
        r = ci.hook_install(ctx(self.root, None, how="package"))
        self.assertEqual((r["changed"], r["notes"]), (False, []))

    def test_a_new_scheme_rebuilds_the_data_only(self):
        r = ci.hook_install(ctx(self.root, None, how="package", scheme="light"))
        self.assertEqual(ci.data_scheme(self.root), "light")
        self.assertEqual(r["notes"], ["built the shared data for the light scheme"])
        self.assertEqual(ci.hook_verify(ctx(self.root, None, how="package", scheme="light")), [])
        self.assertTrue(
            any(
                "dark scheme, not" in x or "light" in x
                for x in ci.hook_verify(ctx(self.root, None, how="package", scheme="dark"))
            )
        )

    def test_refresh_data_follows_the_conf(self):
        self.assertIsNone(ci.refresh_data(self.root, "dark"))  # already dark
        self.assertIn("rebuilt the shared data for the light scheme", ci.refresh_data(self.root, "light"))
        self.assertEqual(ci.data_scheme(self.root), "light")
        self.assertIsNone(ci.refresh_data(self.root, "sepia"))  # not a scheme: ignored

    def test_a_failed_build_leaves_the_old_data_in_place(self):
        (self.p / "scripts/build_data.py").write_text("import sys\nsys.exit('boom: the glyphs cannot be drawn')\n")
        with self.assertRaises(RuntimeError) as e:
            ci.build_data(self.root, "light")
        self.assertIn("boom: the glyphs cannot be drawn", str(e.exception))
        self.assertEqual(ci.data_scheme(self.root), "dark")  # the old data, untouched
        self.assertTrue((self.p / "data/palettes.json").is_file())
        self.assertFalse((self.p / "data.new").exists())

    def test_a_lost_file_is_reported_by_detect_and_verify(self):
        (self.p / "data/rules.json").unlink()
        ci.shim_path(self.root).unlink()
        d = ci.hook_detect(ctx(self.root, self.bundle))
        self.assertIn("data/rules.json", d["missing"])
        self.assertIn("command", d["missing"])
        self.assertTrue(any("rules.json" in x for x in ci.hook_verify(ctx(self.root, self.bundle))))

    def test_uninstall_removes_what_was_installed_but_keeps_the_parts(self):
        (self.p / "plugins.d/plymouth.json").write_text("{}")  # a part's manifest is not the core's to remove
        ci.hook_uninstall(ctx(self.root, self.bundle))
        for d in (*ci.COPIED, "data"):
            self.assertFalse((self.p / d).exists(), d)
        self.assertFalse(ci.shim_path(self.root).exists())
        self.assertTrue((self.p / "plugins.d/plymouth.json").is_file())

    def test_a_package_removal_deletes_only_what_was_generated(self):
        # the package manager owns the files; a leftover data directory would stay behind if the hook did not remove it
        (self.p / "data.old").mkdir()
        r = ci.hook_uninstall(ctx(self.root, None, how="package"))
        self.assertTrue(r["changed"])
        for d in ("data", "data.old"):
            self.assertFalse((self.p / d).exists(), d)
        for d in ci.COPIED:
            self.assertTrue((self.p / d).is_dir(), f"{d} belongs to the package manager, not to the hook")
        self.assertTrue(ci.shim_path(self.root).is_file())

    def test_a_package_removal_also_removes_the_bytecode_caches_python_wrote(self):
        for d in ("lib/material_boot/__pycache__", "scripts/__pycache__"):
            (self.p / d).mkdir(exist_ok=True)  # the data build already left some, importing the installed library
            (self.p / d / "x.cpython-313.pyc").write_bytes(b"\0")
        ci.hook_uninstall(ctx(self.root, None, how="package"))
        self.assertFalse(list(self.p.rglob("__pycache__")))
        self.assertTrue((self.p / "lib/material_boot/__init__.py").is_file())  # the package's own files stay

    def test_uninstall_removes_the_prefix_when_nothing_else_is_left(self):
        ci.hook_uninstall(ctx(self.root, self.bundle))
        self.assertFalse(self.p.exists())


class NoBuild(unittest.TestCase):
    def test_missing_tools_stop_the_install_before_anything_is_touched(self):
        with (
            tempfile.TemporaryDirectory() as t,
            mock.patch.object(ci, "missing_tools", return_value=["Pillow (python3-pillow)"]),
        ):
            root = Path(t) / "root"
            with self.assertRaises(RuntimeError) as e:
                ci.hook_install(ctx(root, make_bundle(Path(t) / "b")))
            self.assertIn("missing: Pillow", str(e.exception))
            self.assertFalse(ci.prefix(root).exists())

    def test_the_plan_names_what_is_missing(self):
        with (
            tempfile.TemporaryDirectory() as t,
            mock.patch.object(ci, "missing_tools", return_value=["rsvg-convert (librsvg2-bin)"]),
        ):
            plan = ci.hook_plan(ctx(Path(t) / "root", Path(t)))
        self.assertTrue(any(x.startswith("MISSING") and "rsvg-convert" in x for x in plan))
        self.assertTrue(any("build the shared data for the dark scheme" in x for x in plan))

    def test_a_bundle_without_the_library_is_refused(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(ci, "missing_tools", return_value=[]):
            with self.assertRaises(RuntimeError) as e:
                ci.hook_install(ctx(Path(t) / "root", Path(t)))
            self.assertIn("no lib/material_boot", str(e.exception))

    def test_nothing_is_found_on_an_empty_root(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(ci.hook_detect(ctx(t)), {"found": False})

    def test_swap_dir_puts_the_old_one_back_when_the_rename_fails(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "dst").mkdir()
            (t / "dst/old.txt").write_text("old")
            (t / "new").mkdir()
            (t / "new/new.txt").write_text("new")
            real = os.replace
            calls = []

            def flaky(a, b):
                calls.append((str(a), str(b)))
                if len(calls) == 2:  # the rename of the new one
                    raise OSError("disk full")
                return real(a, b)

            with mock.patch("os.replace", flaky), self.assertRaises(OSError):
                ci.swap_dir(t / "new", t / "dst")
            self.assertEqual((t / "dst/old.txt").read_text(), "old")

    def test_the_part_record_is_a_part(self):
        p = ci.part()
        self.assertEqual(
            (p.name, p.version, p.problem, p.needs, p.default), ("core", material_boot.__version__, None, [], True)
        )
        from material_boot import plugins

        self.assertIs(plugins.load(p), ci)


if __name__ == "__main__":
    unittest.main()
