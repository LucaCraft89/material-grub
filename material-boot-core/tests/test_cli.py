"""The `material-boot` dispatcher (material_boot.cli), its `core` commands and its menu, with fake parts. stdlib only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import material_boot  # noqa: E402
from material_boot import cli, menu  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.plug = self.d / "plugins.d"
        self.plug.mkdir()
        self.conf = self.d / "material-grub.conf"
        self.ov = self.d / "overrides.json"
        env = {
            "MATERIAL_PLUGIN_PATH": str(self.plug),
            "MATERIAL_CONF": str(self.conf),
            "MATERIAL_OVERRIDES": str(self.ov),
            "MATERIAL_STATE_DIR": str(self.d / "state"),
        }
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def part(self, name, src=None, **over):
        e = self.d / f"{name}_entry.py"
        e.write_text(src if src is not None else "def main(argv, core):\n    return 0\n")
        m = {
            "manifest": 2,
            "name": name,
            "title": name.title(),
            "version": "1.0.0",
            "core_api": 2,
            "entry": str(e),
            "summary": f"the {name}",
        }
        m.update(over)
        (self.plug / f"{name}.json").write_text(json.dumps(m))

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO("")):
            try:
                rc = cli.main(list(argv))
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue()


class TopLevel(Base):
    def test_only_help_version_and_menu_are_top_level(self):
        self.assertEqual(cli.TOP, ("help", "version", "menu"))

    def test_version_lists_the_usable_parts(self):
        self.part("plymouth", version="1.2.3")
        self.part("broken", core_api=1)
        rc, out, _ = self.call("version")
        self.assertEqual(rc, 0)
        self.assertIn(f"material-boot {material_boot.__version__} (plugin API 2)", out)
        self.assertIn("plymouth 1.2.3", out)
        self.assertNotIn("broken", out)

    def test_help_shows_core_commands_parts_their_commands_and_problems(self):
        self.part("plymouth", commands={"apply": "render the theme"})
        self.part("gui", install={"needs": ["grub"]})
        rc, out, _ = self.call("help")
        self.assertEqual(rc, 0)
        self.assertIn("material-boot core conf", out)
        self.assertIn("material-boot plymouth", out)
        self.assertIn("render the theme", out)
        self.assertIn("gui needs the grub part, which is not installed", out)

    def test_without_a_terminal_the_menu_is_the_help(self):
        rc, out, _ = self.call()
        self.assertEqual(rc, 0)
        self.assertIn("Core commands:", out)

    def test_unknown_command(self):
        rc, out, _ = self.call("frobnicate")
        self.assertEqual(rc, 2)
        self.assertIn("unknown command 'frobnicate'", out)

    def test_a_core_command_without_the_module_gets_a_hint(self):
        rc, out, _ = self.call("colour")
        self.assertEqual(rc, 2)
        self.assertIn("'colour' is a core command. Did you mean:  material-boot core colour", out)
        self.assertNotIn("unknown command", out)

    def test_a_known_part_that_is_not_installed_says_which_package(self):
        for name, pkg in (("grub", "material-grub"), ("plymouth", "material-plymouth"), ("gui", "material-grub-gui")):
            rc, out, _ = self.call(name)
            self.assertEqual(rc, 1, name)
            self.assertIn(f"package: {pkg}", out)

    def test_a_part_that_cannot_be_used_says_why(self):
        self.part("plymouth", core_min="99.0.0")
        rc, out, _ = self.call("plymouth", "apply")
        self.assertEqual(rc, 1)
        self.assertIn("cannot use 'plymouth'", out)
        self.assertIn("update the core", out)

    def test_a_part_runs_with_its_arguments_and_status(self):
        self.part(
            "plymouth", src="def main(argv, core):\n    print('args', argv, core.api, core.parts)\n    return 7\n"
        )
        rc, out, _ = self.call("plymouth", "apply", "--yes")
        self.assertEqual(rc, 7)
        self.assertIn("args ['apply', '--yes'] 2 ('plymouth',)", out)


class CoreCommands(Base):
    def test_core_help_and_unknown_and_aliases(self):
        self.assertIn("doctor", self.call("core")[1])
        rc, out, _ = self.call("core", "nope")
        self.assertEqual(rc, 2)
        self.assertIn("unknown core command", out)
        self.assertEqual(self.call("core", "config")[0], 0)  # alias of conf

    def test_conf_shows_and_sets(self):
        rc, out, _ = self.call("core", "conf")
        self.assertEqual(rc, 0)
        self.assertIn("STYLE=rail", out)
        rc, out, _ = self.call("core", "conf", "STYLE=list", "PLYMOUTH_MOTION=calm")
        self.assertEqual(rc, 0)
        self.assertIn("material-boot core apply", out)
        self.assertIn("STYLE=list", self.conf.read_text())
        self.assertIn("STYLE=list", self.call("core", "conf")[1])

    def test_conf_refuses_bad_input_without_writing(self):
        self.conf.write_text("STYLE=rail\n")
        self.assertEqual(self.call("core", "conf", "STYLE=neon")[0], 1)
        self.assertEqual(self.call("core", "conf", "notakeyvalue")[0], 2)
        self.assertEqual(self.conf.read_text(), "STYLE=rail\n")

    def test_colour(self):
        rc, out, _ = self.call("core", "colour")
        self.assertIn("every entry its own colour", out)
        rc, out, _ = self.call("core", "colour", "#7e57c2")
        self.assertEqual(rc, 0)
        self.assertIn("one seed colour #7E57C2", self.call("core", "colour")[1])
        self.assertIn("material-boot core apply", out)
        self.assertEqual(self.call("core", "colour", "forest")[0], 0)
        self.assertEqual(self.call("core", "colour", "multi")[0], 0)
        self.assertIn("every entry its own colour", self.call("core", "colour")[1])
        rc, out, _ = self.call("core", "colour", "notacolour")
        self.assertEqual(rc, 2)
        self.assertIn("neither #RRGGBB", out)

    def test_colour_with_apply_runs_the_parts(self):
        self.part(
            "plymouth", commands={"apply": "x"}, src="def main(argv, core):\n    print('APPLIED', argv)\n    return 0\n"
        )
        rc, out, _ = self.call("core", "colour", "#7E57C2", "--apply")
        self.assertEqual(rc, 0)
        self.assertIn("APPLIED ['apply']", out)

    def test_overrides(self):
        self.assertEqual(self.call("core", "overrides", "path")[1].strip(), str(self.ov))
        self.assertIn("nothing is customised", self.call("core", "overrides", "check")[1])
        self.assertIn('"seed"', self.call("core", "overrides", "show")[1])
        self.ov.write_text("{broken")
        rc, out, _ = self.call("core", "overrides", "check")
        self.assertEqual(rc, 1)
        self.assertIn("NOT valid", out)
        self.assertEqual(self.call("core", "overrides", "bogus")[0], 2)

    def test_parts(self):
        self.assertIn("no parts are installed", self.call("core", "parts")[1])
        self.part("plymouth")
        self.part("gui", install={"needs": ["grub"]})
        rc, out, _ = self.call("core", "parts")
        self.assertEqual(rc, 1)  # one part cannot be used
        self.assertIn("plymouth", out)
        self.assertIn("NOT USABLE", out)


class Presets(Base):
    def test_save_list_apply_delete_export_import(self):
        self.assertIn("no presets yet", self.call("core", "presets")[1])
        self.call("core", "colour", "#7E57C2")
        self.call("core", "conf", "STYLE=list")
        rc, out, _ = self.call("core", "presets", "save", "Gaming rig")
        self.assertEqual(rc, 0, out)
        self.assertIn("Gaming rig", self.call("core", "presets", "list")[1])
        self.call("core", "colour", "multi")
        self.call("core", "conf", "STYLE=rail")
        rc, out, _ = self.call("core", "presets", "apply", "Gaming rig")
        self.assertEqual(rc, 0, out)
        self.assertIn("material-boot core apply", out)
        self.assertIn("one seed colour #7E57C2", self.call("core", "colour")[1])
        self.assertIn("STYLE=list", self.call("core", "conf")[1])
        dest = self.d / "rig.json"
        self.assertEqual(self.call("core", "presets", "export", "Gaming rig", str(dest))[0], 0)
        self.assertEqual(self.call("core", "presets", "delete", "Gaming rig")[0], 0)
        self.assertIn("no presets yet", self.call("core", "presets", "list")[1])
        self.assertEqual(self.call("core", "presets", "import", str(dest))[0], 0)
        self.assertIn("Gaming rig", self.call("core", "presets", "list")[1])

    def test_bad_input(self):
        self.assertEqual(self.call("core", "presets", "bogus")[0], 2)
        self.assertEqual(self.call("core", "presets", "apply", "missing")[0], 1)
        bad = self.d / "bad.json"
        bad.write_text(json.dumps({"format": 99}))
        rc, out, _ = self.call("core", "presets", "import", str(bad))
        self.assertEqual(rc, 1)
        self.assertIn("not a valid preset", out)

    def test_apply_with_the_flag_runs_the_parts(self):
        self.part(
            "plymouth", commands={"apply": "x"}, src="def main(argv, core):\n    print('APPLIED')\n    return 0\n"
        )
        self.call("core", "presets", "save", "A")
        rc, out, _ = self.call("core", "presets", "apply", "A", "--apply")
        self.assertEqual(rc, 0)
        self.assertIn("APPLIED", out)

    def test_the_menu_has_a_presets_entry_that_asks_first(self):
        self.assertIn("Presets", [i[0] for i in menu.menu_items()])


class ApplyRefreshesTheData(Base):
    def test_a_changed_scheme_rebuilds_the_shared_data_before_the_parts_run(self):
        calls = []
        self.conf.write_text("SCHEME=light\n")
        with mock.patch(
            "material_boot.coreinstall.refresh_data",
            side_effect=lambda root, scheme: (
                calls.append((root, scheme)) or "rebuilt the shared data for the light scheme"
            ),
        ):
            rc, out, _ = self.call("core", "apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(calls, [("", "light")])
        self.assertIn("rebuilt the shared data for the light scheme", out)

    def test_a_failed_rebuild_stops_before_the_parts(self):
        self.part("plymouth", commands={"apply": "x"}, src="def main(argv, core):\n    print('RAN')\n    return 0\n")
        with mock.patch(
            "material_boot.coreinstall.refresh_data", side_effect=RuntimeError("building the shared data failed: boom")
        ):
            rc, out, _ = self.call("core", "apply")
        self.assertEqual(rc, 1)
        self.assertIn("boom", out)
        self.assertNotIn("RAN", out)

    def test_only_a_part_does_not_touch_the_data(self):
        self.part("plymouth", commands={"apply": "x"})
        with mock.patch("material_boot.coreinstall.refresh_data", side_effect=AssertionError("must not run")):
            self.assertEqual(self.call("core", "apply", "--only", "plymouth")[0], 0)


class Apply(Base):
    APPLY = "def main(argv, core):\n    print('apply {n}', argv)\n    return {rc}\n"

    def two(self, rc_b=0):
        self.part("aaa", commands={"apply": "x"}, src=self.APPLY.format(n="aaa", rc=0))
        self.part("bbb", commands={"apply": "x"}, src=self.APPLY.format(n="bbb", rc=rc_b))
        self.part("ccc", src=self.APPLY.format(n="ccc", rc=0))  # no apply command: never run

    def test_nothing_to_apply(self):
        rc, out, _ = self.call("core", "apply")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to apply", out)

    def test_every_part_with_an_apply_runs_in_name_order(self):
        self.two()
        rc, out, _ = self.call("core", "apply", "--yes")
        self.assertEqual(rc, 0)
        self.assertLess(out.index("apply aaa ['apply', '--yes']"), out.index("apply bbb ['apply', '--yes']"))
        self.assertNotIn("apply ccc", out)

    def test_one_part_failing_does_not_stop_the_others(self):
        self.two(rc_b=3)
        self.part("ddd", commands={"apply": "x"}, src=self.APPLY.format(n="ddd", rc=0))
        rc, out, _ = self.call("core", "apply")
        self.assertEqual(rc, 1)
        self.assertIn("apply ddd", out)
        self.assertIn("failed: bbb", out)

    def test_only(self):
        self.two()
        rc, out, _ = self.call("core", "apply", "--only", "bbb")
        self.assertEqual(rc, 0)
        self.assertIn("apply bbb", out)
        self.assertNotIn("apply aaa", out)
        self.assertEqual(self.call("core", "apply", "--only", "zzz")[0], 1)
        self.assertEqual(self.call("core", "apply", "--only")[0], 2)


class Doctor(Base):
    def test_a_healthy_core_alone(self):
        rc, out, _ = self.call("core", "doctor")
        self.assertEqual(rc, 0)
        self.assertIn("none installed", out)

    def test_parts_and_their_own_checks(self):
        self.part(
            "plymouth",
            hooks=["doctor"],
            src="def main(a, c):\n    return 0\ndef hook_doctor(ctx):\n    return [('ok', 'theme installed'), ('warn', 'no splash on the command line')]\n",
        )
        self.part("gui", install={"needs": ["grub"]})
        rc, out, _ = self.call("core", "doctor")
        self.assertEqual(rc, 1)  # the gui cannot be used
        self.assertIn("ok    plymouth", out)
        self.assertIn("FAIL  gui", out)
        self.assertIn("theme installed", out)
        self.assertIn("no splash on the command line", out)

    def test_a_failing_check_and_a_crashing_hook_fail_the_doctor(self):
        self.part(
            "plymouth",
            hooks=["doctor"],
            src="def main(a, c):\n    return 0\ndef hook_doctor(ctx):\n    return [('fail', 'initramfs has no theme')]\n",
        )
        self.assertEqual(self.call("core", "doctor")[0], 1)
        self.part(
            "plymouth",
            hooks=["doctor"],
            src="def main(a, c):\n    return 0\ndef hook_doctor(ctx):\n    raise RuntimeError('boom')\n",
        )
        rc, out, _ = self.call("core", "doctor")
        self.assertEqual(rc, 1)
        self.assertIn("the doctor hook failed: RuntimeError: boom", out)


class Menu(Base):
    def test_items_are_the_cores_then_the_parts_then_quit(self):
        self.part("plymouth", menu=[["Apply the splash", "render it", ["plymouth", "apply"]]])
        items = menu.menu_items()
        titles = [i[0] for i in items]
        self.assertEqual(titles[0], "Health check")
        self.assertIn("Apply the splash", titles)
        self.assertLess(titles.index("Parts"), titles.index("Apply the splash"))
        self.assertEqual(items[-1][2], None)

    def test_a_menu_choice_runs_through_the_dispatcher(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        seen = []
        with (
            mock.patch("sys.stdin", Tty()),
            mock.patch("sys.stdout", Tty()),
            mock.patch.object(menu, "pick_plain", side_effect=[0, None]),
            mock.patch.object(menu, "ask", return_value=""),
            mock.patch.dict(os.environ, {"TERM": "dumb"}),
        ):
            rc = menu.main(lambda argv: seen.append(argv) or 0)
        self.assertEqual(rc, 0)
        self.assertEqual(seen, [["core", "doctor"]])

    def test_a_sub_menu_asks_first(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        seen = []
        with (
            mock.patch("sys.stdin", Tty()),
            mock.patch("sys.stdout", Tty()),
            mock.patch.object(
                menu, "pick_plain", side_effect=[[i[0] for i in menu.menu_items()].index("Settings"), None]
            ),
            mock.patch.object(menu, "ask", side_effect=["STYLE=list", ""]),
            mock.patch.dict(os.environ, {"TERM": "dumb"}),
        ):
            menu.main(lambda argv: seen.append(argv) or 0)
        self.assertEqual(seen, [["core", "conf", "STYLE=list"]])


class Shim(Base):
    def run_shim(self, *argv):
        env = dict(os.environ, MB_CLI_SELF="", PATH=os.environ["PATH"])
        return subprocess.run(
            ["sh", str(ROOT / "bin/material-boot"), *argv], capture_output=True, text=True, env=env, cwd=self.d
        )

    def test_version_and_exit_status_through_the_shell_shim(self):
        r = self.run_shim("version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"material-boot {material_boot.__version__}", r.stdout)
        self.part("plymouth", src="def main(a, c):\n    return 5\n")
        self.assertEqual(self.run_shim("plymouth", "x").returncode, 5)
        self.assertEqual(self.run_shim("nope").returncode, 2)

    def test_a_python_that_is_too_old_gets_a_clear_message(self):
        old = self.d / "python-old"
        old.write_text("#!/bin/sh\nexit 1\n")  # what `python -c 'sys.exit(version >= 3.9 ...)'` does on a 3.8
        old.chmod(0o755)
        env = dict(os.environ, MATERIAL_PY=str(old))
        r = subprocess.run(
            ["sh", str(ROOT / "bin/material-boot"), "version"], capture_output=True, text=True, env=env, cwd=self.d
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("Python 3.9 or newer is needed", r.stderr)

    def test_python_dash_m_works_too(self):
        r = subprocess.run(
            [sys.executable, "-m", "material_boot", "version"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=dict(os.environ),
        )
        self.assertEqual(r.returncode, 0, r.stderr)


class Runtime(unittest.TestCase):
    def test_can_write(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(cli.can_write(Path(t) / "new/file"))  # the nearest directory that exists is ours
            self.assertTrue(cli.can_write(t))

    def test_the_real_core_object(self):
        c = cli.real_core(parts=["a"])
        self.assertEqual((c.api, c.parts), (2, ("a",)))
        self.assertIs(c.say, cli.say)
        self.assertIs(c.elevate, cli.elevate)


if __name__ == "__main__":
    unittest.main()
