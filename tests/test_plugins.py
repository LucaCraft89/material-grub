"""Optional parts (plugins, plugin API 2: the loader is the core's, tested there): discovery by this front end, dispatch through `material-grub <part>`, the names it
reserves, the menu, help, version and doctor. Needs material-boot-core (next to the checkout, or MATERIAL_LIB).
usage: python3 tests/test_plugins.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "install/bin/cmd_cli.py"
sys.path.insert(0, str(ROOT / "install/bin"))
import mgplugins  # noqa: E402

ENTRY = """import sys
def main(argv, core):
    core.say(f"called {argv} api={core.api} version={core.version}")
    if argv[:1] == ["crash"]:
        raise RuntimeError("boom")
    if argv[:1] == ["exit"]:
        sys.exit(7)
    return 3 if argv[:1] == ["three"] else None
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.plug = self.d / "plugins.d"
        self.plug.mkdir()
        self.entry = self.d / "mgplugin.py"
        self.entry.write_text(ENTRY)
        self.env = dict(
            os.environ,
            MATERIAL_PLUGIN_PATH=str(self.plug),
            MATERIAL_OVERRIDES=str(self.d / "etc/material-grub/overrides.json"),
            MATERIAL_CONF=str(self.d / "mg.conf"),
            MATERIAL_PKG=str(self.d / "nopkg"),
        )
        patch = unittest.mock.patch.dict(os.environ, {"MATERIAL_PLUGIN_PATH": str(self.plug)})
        patch.start()
        self.addCleanup(
            patch.stop
        )  # in-process calls (discover, menu_items) see the same plugin directory as the subprocesses

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self, name="plymouth", **kw):
        m = {
            "manifest": 2,
            "name": name,
            "title": "Plymouth boot splash",
            "version": "0.1.0",
            "core_api": mgplugins.CORE_API,
            "entry": str(self.entry),
            "summary": "a test part",
            "menu": [["Plymouth status", "Is it applied?", ["plymouth", "status"]]],
        }
        m.update(kw)
        m = {k: v for k, v in m.items() if v is not None}
        (self.plug / f"{name}.json").write_text(json.dumps(m))

    def mg(self, *a):
        r = subprocess.run(
            [sys.executable, str(CLI), *a], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL
        )
        return r.returncode, r.stdout + r.stderr


class Manifests(Base):
    def read(self, **kw):
        self.manifest(**kw)
        return mgplugins.read_manifest(self.plug / f"{kw.get('name', 'plymouth')}.json")

    def test_a_good_manifest(self):
        p = self.read()
        self.assertIsNone(p.problem)
        self.assertEqual((p.name, p.version), ("plymouth", "0.1.0"))

    def test_a_plugin_of_the_old_api_is_refused_with_the_reason(self):
        p = self.read(core_api=1)
        self.assertIn("update whichever of the two is older", p.problem)

    def test_discovery(self):
        self.assertEqual(mgplugins.discover(), [])
        self.manifest()
        self.manifest("zeta", core_api=5)
        (self.plug / "notes.txt").write_text("ignored")
        found = mgplugins.discover()
        self.assertEqual([p.name for p in found], ["plymouth", "zeta"])
        self.assertEqual([p.name for p in mgplugins.usable()], ["plymouth"])
        self.manifest("apply")
        self.assertEqual(
            [p.name for p in mgplugins.usable(("apply",))], ["plymouth"], "a part cannot take a built-in name"
        )

    def test_first_directory_wins_and_no_dirs_means_none(self):
        other = self.d / "other"
        other.mkdir()
        self.manifest(version="1.0")
        (other / "plymouth.json").write_text((self.plug / "plymouth.json").read_text().replace("1.0", "2.0"))
        found = mgplugins.discover(dirs=[self.plug, other])
        self.assertEqual([p.version for p in found], ["1.0"])
        self.assertEqual(mgplugins.discover(dirs=[self.d / "missing"]), [])


class Dispatch(Base):
    def test_not_installed_says_so(self):
        rc, out = self.mg("plymouth", "apply")
        self.assertEqual(rc, 1)
        self.assertIn("optional part", out)
        self.assertIn("material-plymouth", out)
        self.assertNotIn("Traceback", out)

    def test_unknown_commands_are_still_unknown(self):
        rc, out = self.mg("nonsense")
        self.assertEqual(rc, 2)
        self.assertIn("unknown command", out)

    def test_runs_the_plugin_with_the_rest_of_the_arguments(self):
        self.manifest()
        rc, out = self.mg("plymouth", "apply", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("called ['apply', '--yes'] api=2", out)

    def test_exit_status_comes_from_the_plugin(self):
        self.manifest()
        self.assertEqual(self.mg("plymouth", "three")[0], 3)
        self.assertEqual(self.mg("plymouth", "exit")[0], 7)

    def test_a_crashing_plugin_is_reported_as_the_plugins(self):
        self.manifest()
        rc, out = self.mg("plymouth", "crash")
        self.assertEqual(rc, 1)
        self.assertIn("the plymouth part failed", out)
        self.assertNotIn("Traceback", out)

    def test_a_plugin_that_cannot_be_imported(self):
        self.manifest()
        self.entry.write_text("raise SyntaxError('nope')\n")
        rc, out = self.mg("plymouth", "apply")
        self.assertEqual(rc, 1)
        self.assertIn("cannot load", out)
        self.entry.write_text("x = 1\n")
        rc, out = self.mg("plymouth", "apply")
        self.assertEqual(rc, 1)
        self.assertIn("no main", out)

    def test_an_incompatible_plugin_is_refused_with_the_reason(self):
        self.manifest(core_api=1)
        rc, out = self.mg("plymouth", "apply")
        self.assertEqual(rc, 1)
        self.assertIn("plugin API", out)

    def test_a_plugin_cannot_take_over_a_builtin_command(self):
        self.manifest("apply")
        rc, out = self.mg("apply", "--status")
        self.assertNotIn("called", out)

    def test_help_and_version_list_installed_parts_only(self):
        self.assertNotIn("Optional parts installed", self.mg("help")[1])
        self.assertEqual(self.mg("version")[1].strip().count("\n"), 0)
        self.manifest()
        self.assertIn("material-grub plymouth", self.mg("help")[1])
        self.assertIn("plymouth 0.1.0", self.mg("version")[1])
        self.manifest(core_api=9)
        self.assertIn("update whichever", self.mg("help")[1])
        self.assertNotIn("plymouth 0.1.0", self.mg("version")[1])

    def test_menu_items(self):
        import cmd_cli

        base = [m[0] for m in cmd_cli.menu_items()]
        self.assertEqual(base[-1], "Quit")
        self.assertNotIn("Plymouth status", base)
        self.manifest()
        items = [m[0] for m in cmd_cli.menu_items()]
        self.assertEqual(items[-2:], ["Plymouth status", "Quit"])


class Doctor(Base):
    def rows(self):
        rc, out = self.mg("doctor", "--json")
        return [r for r in json.loads(out) if r["check"].startswith("plugin")]

    def test_no_plugin_no_row(self):
        self.assertEqual(self.rows(), [])

    def test_plugin_rows(self):
        self.manifest()
        self.assertEqual([(r["status"], r["check"]) for r in self.rows()], [("ok", "plugin plymouth")])
        self.manifest(core_api=9)
        self.assertEqual([(r["status"], r["check"]) for r in self.rows()], [("warn", "plugin plymouth")])

    def test_conf_keys_of_the_plugin_are_known_to_doctor(self):
        (self.d / "etc").mkdir()  # a staged installation: doctor --root reads <root>/etc/material-grub.conf

        def config(text):
            (self.d / "etc/material-grub.conf").write_text(text)
            rc, out = self.mg("doctor", "--root", str(self.d), "--json")
            return [r for r in json.loads(out) if r["check"] == "config"][0]

        cfg = config("PLYMOUTH=off\nPLYMOUTH_BAR=progress\nPLYMOUTH_MOTION=calm\n")
        self.assertEqual(cfg["status"], "ok", cfg)
        cfg = config("PLYMOUTH_MOTION=frantic\n")
        self.assertEqual(cfg["status"], "warn")
        self.assertIn("PLYMOUTH_MOTION", cfg["detail"])


if __name__ == "__main__":
    unittest.main()
