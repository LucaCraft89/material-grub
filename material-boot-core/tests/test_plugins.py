"""Plugin API 2 (material_boot.plugins): manifests, discovery, dependencies, loading, running, hooks. stdlib only."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import material_boot  # noqa: E402
from material_boot import plugins as P  # noqa: E402

ENTRY = "def main(argv, core):\n    return {rc}\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.plug = self.d / "plugins.d"
        self.plug.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def part(self, pname="demo", src=None, plug=None, raw=None, **over):
        """Write <name>_entry.py (with the source `src`) and <name>.json; returns the manifest path. `over` overrides (or, with None, removes) manifest keys."""
        e = self.d / f"{pname}_entry.py"
        e.write_text(src if src is not None else ENTRY.format(rc=0))
        m = {
            "manifest": 2,
            "name": pname,
            "title": pname.title(),
            "version": "1.0.0",
            "core_api": 2,
            "entry": str(e),
            "summary": "a test part",
        }
        for k, v in over.items():
            if v is None:
                m.pop(k, None)
            else:
                m[k] = v
        f = (plug or self.plug) / f"{pname}.json"
        f.write_text(raw if raw is not None else json.dumps(m))
        return f


class Manifest(Base):
    def test_a_full_manifest(self):
        f = self.part(
            "plymouth",
            commands={"apply": "render it", "status": "what is installed"},
            menu=[["Apply", "Render", ["plymouth", "apply"]]],
            conf=["PLYMOUTH", "PLYMOUTH_BAR"],
            install={"default": False, "needs": ["grub", "core"]},
            hooks=["install", "doctor"],
            core_min="1.0.0",
        )
        p = P.read_manifest(f)
        self.assertIsNone(p.problem, p.problem)
        self.assertEqual((p.name, p.version, p.core_min), ("plymouth", "1.0.0", "1.0.0"))
        self.assertEqual(list(p.commands), ["apply", "status"])
        self.assertEqual(p.menu, [("Apply", "Render", ["plymouth", "apply"])])
        self.assertEqual(p.conf, ["PLYMOUTH", "PLYMOUTH_BAR"])
        self.assertEqual(p.hooks, ("install", "doctor"))
        self.assertEqual(p.needs, ["grub"])  # the core is always there
        self.assertFalse(p.default)
        self.assertEqual(p.warnings, [])

    def test_the_minimum_is_enough(self):
        p = P.read_manifest(self.part())
        self.assertIsNone(p.problem)
        self.assertEqual((p.commands, p.menu, p.conf, p.hooks, p.needs), ({}, [], [], (), []))

    def test_problems_are_sentences_never_exceptions(self):
        bad = {
            "not json": dict(raw="{nope"),
            "not an object": dict(raw="[1]"),
            "no name": dict(name=None),
            "bad name": dict(name="Bad Name"),
            "old manifest": dict(manifest=1),
            "api 1 draft": dict(core_api=1),
            "no api": dict(core_api=None),
            "entry missing": dict(entry="/nonexistent/entry.py"),
            "entry relative": dict(entry="entry.py"),
            "core too old": dict(core_min="99.0.0"),
            "core_min junk": dict(core_min="soon"),
            "needs junk": dict(install={"needs": "grub"}),
        }
        for label, kw in bad.items():
            with self.subTest(label):
                p = P.read_manifest(self.part("demo", **kw))
                self.assertTrue(p.problem, label)
                self.assertIsNone(p.entry if label.startswith("entry") else None)

    def test_the_api_message_says_which_side_to_update(self):
        p = P.read_manifest(self.part(core_api=3))
        self.assertIn("API 3", p.problem)
        self.assertIn(f"has {material_boot.CORE_API}", p.problem)
        self.assertIn("update whichever", p.problem)
        p = P.read_manifest(self.part(core_min="99.0.0"))
        self.assertIn("update the core", p.problem)

    def test_core_min_is_compared_with_the_core_version(self):
        f = self.part(core_min="1.2.0")
        self.assertIsNotNone(P.read_manifest(f, core_version="1.1.9").problem)
        self.assertIsNone(P.read_manifest(f, core_version="1.2.0").problem)
        self.assertIsNone(P.read_manifest(f, core_version="2.0.0").problem)

    def test_the_cores_words_cannot_be_taken_over(self):
        for name in P.RESERVED:
            with self.subTest(name):
                p = P.read_manifest(self.part(name))
                self.assertIn("belongs to the core", p.problem)

    def test_oversized_manifest(self):
        f = self.part()
        f.write_text(" " * (P.MAX_MANIFEST + 1))
        self.assertIn("too large", P.read_manifest(f).problem)

    def test_things_that_are_ignored_are_warned_about(self):
        p = P.read_manifest(
            self.part(
                commands={"ok": "fine", "Bad Name": "x", "worse": 3},
                menu=[["Mine", "d", ["demo", "ok"]], ["Theirs", "d", ["grub", "apply"]], ["broken"], "nope"],
                hooks=["install", "launch-missiles"],
            )
        )
        self.assertIsNone(p.problem)
        self.assertEqual(list(p.commands), ["ok"])
        self.assertEqual([m[0] for m in p.menu], ["Mine"])  # a part's menu can only run that part
        self.assertEqual(p.hooks, ("install",))
        self.assertEqual(len(p.warnings), 6)
        self.assertTrue(any("runs 'grub', not this part" in w for w in p.warnings))


class Discovery(Base):
    def test_ordered_by_name_and_first_directory_wins(self):
        other = self.d / "other.d"
        other.mkdir()
        self.part("zeta")
        self.part("alpha")
        shadow = self.part("alpha", plug=other, version="9.9.9")
        found = P.discover([self.plug, other])
        self.assertEqual([p.name for p in found], ["alpha", "zeta"])
        self.assertEqual(found[0].version, "1.0.0")
        self.assertEqual(found[0].shadows, [shadow])

    def test_missing_and_empty_directories_are_fine(self):
        self.assertEqual(P.discover([self.d / "nope", self.plug]), [])

    def test_the_environment_variable_replaces_the_system_directories(self):
        self.part("demo")
        old = os.environ.get("MATERIAL_PLUGIN_PATH")
        try:
            os.environ["MATERIAL_PLUGIN_PATH"] = str(self.plug)
            self.assertEqual([p.name for p in P.usable()], ["demo"])
            os.environ["MATERIAL_PLUGIN_PATH"] = ""
            self.assertEqual(P.usable(), [])
        finally:
            if old is None:
                os.environ.pop("MATERIAL_PLUGIN_PATH", None)
            else:
                os.environ["MATERIAL_PLUGIN_PATH"] = old

    def test_usable_and_find_keep_broken_parts_findable(self):
        self.part("good")
        self.part("broken", core_api=1)
        d = [self.plug]
        self.assertEqual([p.name for p in P.usable(d)], ["good"])
        self.assertIn("API 1", P.find("broken", d).problem)
        self.assertIsNone(P.find("absent", d))


class Needs(Base):
    def test_a_part_whose_need_is_missing_is_unusable(self):
        self.part("gui", install={"needs": ["grub"]})
        (g,) = P.discover([self.plug])
        self.assertEqual(g.problem, "gui needs the grub part, which is not installed")

    def test_plymouth_does_not_need_grub_and_the_gui_does(self):
        self.part("plymouth")
        self.part("gui", install={"needs": ["grub"]})
        self.assertEqual([p.name for p in P.usable([self.plug])], ["plymouth"])
        self.part("grub")
        self.assertEqual([p.name for p in P.usable([self.plug])], ["grub", "gui", "plymouth"])

    def test_a_need_that_is_itself_broken_and_a_chain(self):
        self.part("aa", install={"needs": ["bb"]})
        self.part("bb", install={"needs": ["cc"]})
        self.part("cc", core_api=1)
        found = {p.name: p for p in P.discover([self.plug])}
        self.assertIn("API 1", found["cc"].problem)
        self.assertIn("needs the cc part, which cannot be used", found["bb"].problem)
        self.assertIn("needs the bb part, which cannot be used", found["aa"].problem)


class Running(Base):
    def run_part(self, entry, argv=("x",)):
        p = P.read_manifest(self.part("demo", src=entry))
        err = io.StringIO()
        with redirect_stderr(err):
            rc = P.run(p, list(argv), P.make_core())
        return rc, err.getvalue()

    def test_exit_statuses(self):
        self.assertEqual(self.run_part(ENTRY.format(rc=3))[0], 3)
        self.assertEqual(self.run_part(ENTRY.format(rc="None"))[0], 0)
        self.assertEqual(self.run_part(ENTRY.format(rc="'text'"))[0], 0)
        self.assertEqual(self.run_part("import sys\ndef main(a, c):\n    sys.exit(7)\n")[0], 7)
        self.assertEqual(self.run_part("import sys\ndef main(a, c):\n    sys.exit('boom')\n")[0], 1)
        self.assertEqual(self.run_part("def main(a, c):\n    raise KeyboardInterrupt\n")[0], 130)

    def test_argv_and_core_reach_main(self):
        rc, _ = self.run_part(
            "def main(argv, core):\n    return 0 if argv == ['apply', '--yes'] and core.api == 2 and core.parts == () else 9\n",
            argv=("apply", "--yes"),
        )
        self.assertEqual(rc, 0)

    def test_a_crash_is_reported_not_raised(self):
        rc, err = self.run_part("def main(a, c):\n    raise ValueError('bad thing')\n")
        self.assertEqual(rc, 1)
        self.assertIn("the demo part failed: ValueError: bad thing", err)

    def test_load_failures_are_readable(self):
        for label, src, text in (
            ("syntax", "def main(:\n", "cannot load"),
            ("no main", "x = 1\n", "defines no main"),
        ):
            with self.subTest(label):
                rc, err = self.run_part(src)
                self.assertEqual(rc, 1)
                self.assertIn(text, err)

    def test_the_part_can_import_its_own_modules_and_leaves_sys_path_clean(self):
        (self.d / "helper_mod.py").write_text("VALUE = 5\n")
        before = list(sys.path)
        rc, _ = self.run_part("import helper_mod\ndef main(a, c):\n    return helper_mod.VALUE\n")
        self.assertEqual(rc, 5)
        self.assertEqual(sys.path, before)
        sys.modules.pop("helper_mod", None)


class Hooks(Base):
    def test_a_hook_runs_and_returns_its_value(self):
        f = self.part(
            "demo",
            src=ENTRY.format(rc=0) + "def hook_install(ctx):\n    return {'changed': ctx.dry_run is False}\n",
            hooks=["install"],
        )
        p = P.read_manifest(f)
        r = P.call_hook(p, "install", __import__("types").SimpleNamespace(dry_run=False))
        self.assertTrue(r.ok)
        self.assertEqual(r.value, {"changed": True})

    def test_the_manifest_cannot_promise_a_hook_the_file_lacks(self):
        p = P.read_manifest(self.part("demo", hooks=["verify"]))
        r = P.call_hook(p, "verify", None)
        self.assertFalse(r.ok)
        self.assertIn("does not define them", r.error)

    def test_an_undeclared_hook_is_not_called(self):
        p = P.read_manifest(self.part("demo", src=ENTRY.format(rc=0) + "def hook_install(ctx):\n    return 1\n"))
        r = P.call_hook(p, "install", None)
        self.assertFalse(r.ok)
        self.assertIn("has no install hook", r.error)

    def test_a_crashing_hook_is_a_failed_step(self):
        f = self.part(
            "demo",
            src=ENTRY.format(rc=0) + "def hook_doctor(ctx):\n    raise RuntimeError('disk full')\n",
            hooks=["doctor"],
        )
        r = P.call_hook(P.read_manifest(f), "doctor", None)
        self.assertFalse(r.ok)
        self.assertIn("the doctor hook failed: RuntimeError: disk full", r.error)


class CoreObject(unittest.TestCase):
    def test_what_a_part_gets(self):
        c = P.make_core(data="/usr/share/material-boot/data", parts=["plymouth", "grub"])
        self.assertEqual((c.api, c.version), (2, material_boot.__version__))
        self.assertEqual(c.data, Path("/usr/share/material-boot/data"))
        self.assertEqual(c.parts, ("plymouth", "grub"))
        self.assertTrue((c.lib / "material_boot" / "plugins.py").is_file())
        self.assertEqual(str(c.conf_path()), os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf"))
        self.assertEqual(str(c.state_dir()), os.environ.get("MATERIAL_STATE_DIR", "/var/lib/material-grub"))
        c.say("")  # callable


if __name__ == "__main__":
    unittest.main()
