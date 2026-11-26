"""The unified installer (material_boot.installer, material_boot.detect) with fake parts in a temporary bundle. stdlib only."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import material_boot  # noqa: E402
from material_boot import cli, coreinstall, detect, installer, plugins, state  # noqa: E402

# One entry file for every fake part: what it does is in cfg.json next to it, and every hook logs the call to $FAKE_LOG.
ENTRY = """
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "cfg.json")) as f:
    CFG = json.load(f)

def _log(hook, **kw):
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps({"part": CFG["name"], "hook": hook, **kw}) + "\\n")

def main(argv, core):
    return 0

def hook_detect(ctx):
    _log("detect")
    return CFG.get("detect")

def hook_plan(ctx):
    _log("plan")
    return CFG.get("plan", ["would install " + CFG["name"]])

def hook_install(ctx):
    _log("install", style=ctx.conf.get("STYLE"), options=ctx.options, dry=ctx.dry_run, root=ctx.root, previous=ctx.previous)
    if CFG.get("fail"):
        raise RuntimeError(CFG["fail"])
    if CFG.get("state_entry"):
        from material_boot import state
        st = state.read(ctx.root) or {"state": 1, "parts": {}}
        st.setdefault("parts", {})[CFG["name"]] = CFG["state_entry"]
        state.write(ctx.root, st)
    return {"changed": True, "notes": ["did " + CFG["name"]]}

def hook_verify(ctx):
    _log("verify")
    return CFG.get("problems", [])

def hook_uninstall(ctx):
    _log("uninstall")
    return {"changed": True}

def hook_migrate(ctx):
    _log("migrate")
"""


class FakeCore:
    """What the core's part does for the framework tests: it logs the hooks like any other fake part (the real hooks are tested in test_coreinstall.py)."""

    @staticmethod
    def _log(hook, **kw):
        with open(os.environ["FAKE_LOG"], "a") as f:
            f.write(json.dumps({"part": "core", "hook": hook, **kw}) + "\n")

    @staticmethod
    def hook_detect(ctx):
        FakeCore._log("detect")

    @staticmethod
    def hook_plan(ctx):
        FakeCore._log("plan")
        return ["would install the core"]

    @staticmethod
    def hook_install(ctx):
        FakeCore._log("install", how=ctx.how, source=str(ctx.source))
        return {"changed": True, "notes": ["did core"]}

    @staticmethod
    def hook_verify(ctx):
        FakeCore._log("verify")
        return []

    @staticmethod
    def hook_uninstall(ctx):
        FakeCore._log("uninstall")
        return {"changed": True}


class Base(unittest.TestCase):
    def setUp(self):
        real = coreinstall.part

        def fake_part():
            p = real()
            p.module = FakeCore
            return p

        patch = mock.patch.object(coreinstall, "part", fake_part)
        patch.start()
        self.addCleanup(patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.bundle = self.d / "bundle"
        self.rootdir = self.d / "root"
        (self.rootdir / "etc").mkdir(parents=True)
        self.plug = self.d / "plugins.d"
        self.plug.mkdir()
        self.log = self.d / "calls.log"
        env = {
            "MATERIAL_PLUGIN_PATH": str(self.plug),
            "FAKE_LOG": str(self.log),
            "MATERIAL_CONF": str(self.rootdir / "etc/material-grub.conf"),
            "MATERIAL_OVERRIDES": str(self.rootdir / "etc/material-grub/overrides.json"),
        }
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def part(self, name, version="1.0.0", install=None, hooks=None, **cfg):
        """A part in the bundle: parts/<name>/{manifest.json, entry.py, cfg.json}; `entry` is relative, as in a real bundle."""
        d = self.bundle / "parts" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "entry.py").write_text(ENTRY)
        (d / "cfg.json").write_text(json.dumps({"name": name, **cfg}))
        m = {
            "manifest": 2,
            "name": name,
            "title": name.title(),
            "version": version,
            "core_api": 2,
            "entry": "entry.py",
            "hooks": ["detect", "plan", "install", "verify", "uninstall", "migrate"] if hooks is None else hooks,
            "install": install or {},
        }
        (d / "manifest.json").write_text(json.dumps(m))

    def calls(self):
        try:
            return [json.loads(x) for x in self.log.read_text().splitlines()]
        except OSError:
            return []

    def hooks_of(self, hook, core=False):
        """The parts a hook was called for, in order. The core (which is always first) is left out unless asked for."""
        return [c["part"] for c in self.calls() if c["hook"] == hook and (core or c["part"] != "core")]

    def recorded(self):
        """The parts in the state record, without the core."""
        return {k: v for k, v in (state.read(str(self.rootdir)) or {}).get("parts", {}).items() if k != "core"}

    def run_cli(self, *argv, answers=()):
        """The whole command through the dispatcher; returns (status, output)."""
        out = io.StringIO()
        with (
            redirect_stdout(out),
            mock.patch("builtins.input", side_effect=list(answers) or EOFError),
        ):
            rc = cli.main(["core", "install", "--bundle", str(self.bundle), "--root", str(self.rootdir), *argv])
        return rc, out.getvalue()


class Parsing(Base):
    def parts(self):
        self.part(
            "grub",
            install={
                "default": True,
                "options": [{"name": "res", "takes": "value"}, {"name": "ventoy", "takes": "flag"}],
            },
        )
        self.part("gui", install={"needs": ["grub"], "options": [{"name": "res", "takes": "value"}]})
        self.part("plymouth", install={"options": [{"name": "no-cmdline", "takes": "flag", "summary": "x"}]})
        return plugins.discover_bundle(self.bundle)

    def test_generic_options(self):
        o, errs = installer.parse_args(
            [
                "--with",
                "a,b",
                "--with=c",
                "--without",
                "d",
                "--yes",
                "--dry-run",
                "--force",
                "--root",
                "/r",
                "--progress",
                "json",
            ]
        )
        self.assertEqual(errs, [])
        self.assertEqual(
            (o.with_, o.without, o.yes, o.dry_run, o.force, o.root, o.json),
            (["a", "b", "c"], ["d"], True, True, True, "/r", True),
        )

    def test_the_shared_look(self):
        o, errs = installer.parse_args(
            ["--style", "list", "--scheme=light", "--seed", "#7e57c2", "--no-cookie", "--hints"]
        )
        self.assertEqual(errs, [])
        self.assertEqual(o.look, {"STYLE": "list", "SCHEME": "light", "COOKIE": "off", "HINTS": "on"})
        self.assertEqual((o.seed, o.seed_mode), ("#7E57C2", "single"))  # a seed colour means one colour for everything

    def test_bad_values_are_errors(self):
        for argv, text in (
            (["--style", "neon"], "--style must be"),
            (["--scheme", "sepia"], "--scheme must be"),
            (["--seed", "red"], "--seed must look like"),
            (["--seed-mode", "both"], "--seed-mode must be"),
            (["--with"], "--with needs a value"),
            (["--progress", "xml"], "only knows json"),
            (["--frobnicate"], "unknown option --frobnicate"),
        ):
            with self.subTest(argv):
                _, errs = installer.parse_args(argv)
                self.assertTrue(any(text in e for e in errs), errs)

    def test_part_options_prefixed_always_and_bare_when_unambiguous(self):
        parts = self.parts()
        o, errs = installer.parse_args(["--grub-res", "1920x1080", "--plymouth-no-cmdline", "--ventoy"], parts)
        self.assertEqual(errs, [])
        chosen = [p for p in parts if p.name in ("grub", "plymouth")]
        self.assertEqual(installer.route_part_options(o, chosen), [])
        self.assertEqual(o.part_opts, {"grub": {"res": "1920x1080", "ventoy": True}, "plymouth": {"no-cmdline": True}})

    def test_an_ambiguous_bare_option_names_the_prefix(self):
        parts = self.parts()
        o, errs = installer.parse_args(["--res", "1280x720"], parts)
        self.assertEqual(errs, [])
        both = [p for p in parts if p.name in ("grub", "gui")]
        e = installer.route_part_options(o, both)
        self.assertEqual(len(e), 1)
        self.assertIn("--grub-res", e[0])
        # but with only one of them chosen it is fine
        o, _ = installer.parse_args(["--res", "1280x720"], parts)
        self.assertEqual(installer.route_part_options(o, [p for p in parts if p.name == "grub"]), [])
        self.assertEqual(o.part_opts["grub"], {"res": "1280x720"})

    def test_an_option_of_a_part_that_is_not_chosen_is_an_error(self):
        parts = self.parts()
        o, _ = installer.parse_args(["--ventoy"], parts)
        e = installer.route_part_options(o, [p for p in parts if p.name == "plymouth"])
        self.assertIn("not being installed", e[0])


class Selection(Base):
    def setUp(self):
        super().setUp()
        self.part("grub", install={"default": True})
        self.part("gui", install={"needs": ["grub"]})
        self.part("plymouth")
        self.parts = plugins.discover_bundle(self.bundle)

    def sel(self, *argv, installed=()):
        o, errs = installer.parse_args(argv, self.parts)
        self.assertEqual(errs, [])
        chosen, notes, errors = installer.select(self.parts, set(installed), o)
        return [p.name for p in chosen], notes, errors

    def test_a_fresh_system_gets_the_defaults(self):
        self.assertEqual(self.sel()[0], ["grub"])

    def test_choosing_a_part_on_a_fresh_system_means_only_that_one(self):
        self.assertEqual(
            self.sel("--with", "plymouth")[0], ["plymouth"]
        )  # Plymouth without GRUB is the point of the split

    def test_an_update_keeps_what_is_installed(self):
        self.assertEqual(self.sel(installed=["grub", "plymouth"])[0], ["grub", "plymouth"])
        self.assertEqual(self.sel("--without", "plymouth", installed=["grub", "plymouth"])[0], ["grub"])
        self.assertEqual(self.sel("--with", "gui", installed=["grub"])[0], ["grub", "gui"])

    def test_only(self):
        self.assertEqual(self.sel("--only", "plymouth", installed=["grub"])[0], ["plymouth"])

    def test_needs_are_added_with_a_note_and_ordered_first(self):
        names, notes, errors = self.sel("--with", "gui")
        self.assertEqual((names, errors), (["grub", "gui"], []))
        self.assertIn("grub is added because gui needs it", notes)

    def test_a_need_that_is_installed_is_not_added(self):
        self.assertEqual(self.sel("--only", "gui", installed=["grub"])[0], ["gui"])

    def test_a_need_that_was_excluded_is_an_error(self):
        _, _, errors = self.sel("--with", "gui", "--without", "grub")
        self.assertIn("which you excluded", errors[0])

    def test_unknown_and_unusable_parts(self):
        self.assertIn("there is no part called 'nope'", self.sel("--with", "nope")[2][0])
        d = self.bundle / "parts/broken"
        d.mkdir()
        (d / "entry.py").write_text("def main(a, c):\n    return 0\n")
        (d / "manifest.json").write_text(
            json.dumps({"manifest": 2, "name": "broken", "version": "1", "core_api": 1, "entry": "entry.py"})
        )
        self.parts = plugins.discover_bundle(self.bundle)
        self.assertIn("cannot use 'broken'", self.sel("--with", "broken")[2][0])


class Run(Base):
    def test_parts_install_in_dependency_order_and_are_recorded(self):
        # the names sort the other way round from the dependency: "alpha" needs "omega", so omega must come first
        self.part("alpha", install={"needs": ["omega"]})
        self.part("omega", install={"default": True})
        rc, out = self.run_cli("--yes", "--with", "alpha")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.hooks_of("install"), ["omega", "alpha"])
        self.assertEqual(self.hooks_of("verify"), ["omega", "alpha"])
        self.assertEqual(
            self.hooks_of("install", core=True)[0], "core"
        )  # every part needs the core, which is installed first
        st = state.read(str(self.rootdir))
        self.assertEqual(st["parts"], {"core": "1.0.0", "alpha": "1.0.0", "omega": "1.0.0"})
        self.assertEqual(st["version"], material_boot.__version__)
        self.assertIn("Installed: core, omega, alpha.", out)

    def test_options_reach_the_part_and_the_look_is_written_before_any_part_runs(self):
        self.part("grub", install={"default": True, "options": [{"name": "res", "takes": "value"}]})
        rc, out = self.run_cli("--yes", "--style", "list", "--res", "1280x720")
        self.assertEqual(rc, 0, out)
        (call,) = [c for c in self.calls() if c["hook"] == "install" and c["part"] != "core"]
        self.assertEqual(call["options"], {"res": "1280x720"})
        self.assertEqual(call["style"], "list")  # the part saw the look that was asked for
        self.assertIn("STYLE=list", (self.rootdir / "etc/material-grub.conf").read_text())

    def test_the_seed_colour_is_written_to_the_overrides(self):
        self.part("grub", install={"default": True})
        rc, _ = self.run_cli("--yes", "--seed", "#7E57C2")
        self.assertEqual(rc, 0)
        ov = json.loads((self.rootdir / "etc/material-grub/overrides.json").read_text())
        self.assertEqual(ov["seed"], {"mode": "single", "color": "#7E57C2"})

    def test_dry_run_changes_nothing(self):
        self.part("grub", install={"default": True}, plan=["write grub.cfg", "build the scenes"])
        rc, out = self.run_cli("--dry-run", "--style", "list")
        self.assertEqual(rc, 0, out)
        self.assertIn("write grub.cfg", out)
        self.assertIn("Dry run: nothing was changed.", out)
        self.assertEqual(self.hooks_of("install"), [])
        self.assertIsNone(state.read(str(self.rootdir)))
        self.assertFalse((self.rootdir / "etc/material-grub.conf").exists())

    def test_a_failure_in_the_middle_keeps_the_first_part_and_skips_the_third(self):
        self.part("aaa", install={"default": True})
        self.part("bbb", install={"default": True}, fail="disk full")
        self.part("ccc", install={"default": True})
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 1)
        self.assertEqual(self.hooks_of("install"), ["aaa", "bbb"])  # ccc was never started
        self.assertEqual(self.recorded(), {"aaa": "1.0.0"})  # only the one that succeeded is recorded
        self.assertIn("Installed: core, aaa. Failed: bbb. Not run: ccc.", out)
        self.assertIn("RuntimeError: disk full", out)
        self.assertIn("Run again to retry the rest.", out)

    def test_a_part_that_fails_its_verify_is_a_failure(self):
        self.part("aaa", install={"default": True}, problems=["the theme is missing"])
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 1)
        self.assertIn("the theme is missing", out)
        self.assertEqual(self.recorded(), {})  # the part that failed its verify is not recorded

    def test_a_state_entry_a_part_wrote_survives_the_record(self):
        self.part("plymouth", install={"default": True}, state_entry={"version": "0.9", "changes": ["cmdline"]})
        rc, _ = self.run_cli("--yes")
        self.assertEqual(rc, 0)
        self.assertEqual(
            state.read(str(self.rootdir))["parts"]["plymouth"], {"version": "1.0.0", "changes": ["cmdline"]}
        )

    def test_a_part_that_does_not_support_this_layout_is_refused(self):
        self.part("plymouth", install={"default": True, "layouts": ["normal"]})
        (self.rootdir / "run").mkdir()
        (self.rootdir / "run/ostree-booted").write_text("")
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 1)
        self.assertIn("not available on a system with the immutable layout", out)
        self.assertEqual(self.hooks_of("install"), [])

    def test_unknown_option_and_part_exit_with_usage(self):
        self.part("grub", install={"default": True})
        rc, out = self.run_cli("--bogus")
        self.assertEqual(rc, 2)
        self.assertIn("unknown option --bogus", out)
        self.assertEqual(self.run_cli("--with", "nope")[0], 2)

    def test_the_older_install_is_migrated_before_the_parts_run(self):
        self.part("grub", install={"default": True})
        state.record(str(self.rootdir), "0.7.1", "source", "normal", parts={"grub": "0.7.1"})
        (self.rootdir / "etc/material-grub.conf").write_text("STYLE=rail\n")
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn(
            "#PLYMOUTH=on", (self.rootdir / "etc/material-grub.conf").read_text()
        )  # the core's ConfSamples step
        self.assertEqual(self.hooks_of("migrate"), ["grub"])
        self.assertTrue(any((self.rootdir / "var/backups/material-grub").glob("upgrade-0.7.1-to-*")))


class Existing(Base):
    def setUp(self):
        super().setUp()
        self.part(
            "grub",
            version="1.0.0",
            install={"default": True, "package": "material-grub"},
            detect={"found": True, "version": "0.7.1", "how": "source", "details": ["style list"]},
        )

    def test_the_notice_names_the_old_version_and_asks(self):
        rc, out = self.run_cli(answers=["y"])
        self.assertEqual(rc, 0, out)
        self.assertIn("Found Grub 0.7.1, a source install: style list.", out)
        self.assertIn("This will update it to 1.0.0.", out)

    def test_answering_no_changes_nothing(self):
        rc, out = self.run_cli(answers=["n"])
        self.assertEqual(rc, 1)
        self.assertIn("nothing changed", out)
        self.assertEqual(self.hooks_of("install"), [])

    def test_a_downgrade_is_refused_unless_forced(self):
        self.part(
            "grub",
            version="0.9.0",
            install={"default": True},
            detect={"found": True, "version": "1.0.0", "how": "source"},
        )
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 1)
        self.assertIn("is installed and this is 0.9.0", out)
        self.assertEqual(self.hooks_of("install"), [])
        self.assertEqual(self.run_cli("--yes", "--force")[0], 0)

    def test_a_source_install_over_a_package_is_refused_with_the_right_command(self):
        self.part(
            "grub",
            install={"default": True, "package": "material-grub"},
            detect={"found": True, "version": "1.0.0", "how": "package:rpm"},
        )
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 1)
        self.assertIn("sudo dnf upgrade material-grub", out)
        rc, out = self.run_cli("--yes", "--from-package")  # the package's own scriptlet is how it is updated
        self.assertEqual(rc, 0, out)

    def test_the_state_record_finds_a_part_without_a_detect_hook(self):
        self.part("grub", install={"default": True}, hooks=["install"])
        state.record(str(self.rootdir), "0.7.1", "source", "normal", parts={"grub": "0.7.1"})
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 0, out)
        self.assertIn("Found Grub 0.7.1", out)


class Uninstall(Base):
    def test_reverse_order_and_the_state_forgets_the_parts(self):
        self.part("alpha", install={"needs": ["omega"]})
        self.part("omega", install={"default": True})
        self.run_cli("--yes", "--with", "alpha")
        self.assertEqual(sorted(self.recorded()), ["alpha", "omega"])
        rc, out = self.run_cli("--yes", "--uninstall")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.hooks_of("uninstall"), ["alpha", "omega"])  # what needs omega goes first
        self.assertEqual(self.recorded(), {})
        self.assertEqual(
            self.hooks_of("uninstall", core=True), ["alpha", "omega"]
        )  # the core stays: it goes last and only on request
        self.assertIn("core", state.read(str(self.rootdir))["parts"])
        self.assertIn("Removed: alpha, omega.", out)

    def test_uninstall_never_falls_back_to_the_defaults(self):
        self.part("grub", install={"default": True})
        self.part("plymouth")
        state.record(
            str(self.rootdir), "1.0.0", "source", "normal", parts={"plymouth": "1.0.0"}
        )  # only Plymouth is there
        rc, out = self.run_cli("--yes", "--uninstall")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.hooks_of("uninstall"), ["plymouth"])  # not grub, which was never installed

    def test_uninstall_on_a_system_with_nothing_installed_does_nothing(self):
        self.part(
            "grub", install={"default": True}
        )  # the default part must not be "removed" by an uninstall that was asked for nothing
        rc, out = self.run_cli("--yes", "--uninstall")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.hooks_of("uninstall"), [])

    def test_only(self):
        self.part("grub", install={"default": True})
        self.part("plymouth")
        self.run_cli("--yes", "--with", "grub", "--with", "plymouth")
        self.run_cli("--yes", "--uninstall", "--only", "plymouth")
        self.assertEqual(self.recorded(), {"grub": "1.0.0"})


class TheCore(Base):
    def test_it_is_installed_first_and_by_default(self):
        self.part("grub", install={"default": True})
        rc, out = self.run_cli("--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.hooks_of("install", core=True), ["core", "grub"])
        self.assertEqual([c["how"] for c in self.calls() if c["part"] == "core" and c["hook"] == "install"], ["source"])

    def test_the_bundle_is_handed_to_it(self):
        self.part("grub", install={"default": True})
        self.run_cli("--yes")
        (c,) = [c for c in self.calls() if c["part"] == "core" and c["hook"] == "install"]
        self.assertEqual(c["source"], str(self.bundle))

    def test_a_package_install_says_so(self):
        self.part("grub", install={"default": True})
        self.run_cli("--yes", "--from-package")
        (c,) = [c for c in self.calls() if c["part"] == "core" and c["hook"] == "install"]
        self.assertEqual(c["how"], "package")

    def test_it_cannot_be_left_out(self):
        self.part("grub", install={"default": True})
        rc, out = self.run_cli("--yes", "--without", "core")
        self.assertEqual(rc, 2)
        self.assertIn("the core cannot be left out", out)

    def test_only_another_part_does_not_touch_it(self):
        self.part("grub", install={"default": True})
        state.record(str(self.rootdir), "1.0.0", "source", "normal", parts={"core": "1.0.0"})
        rc, _ = self.run_cli("--yes", "--only", "grub")
        self.assertEqual(rc, 0)
        self.assertEqual(self.hooks_of("install", core=True), ["grub"])

    def test_it_is_removed_only_on_request(self):
        self.part("grub", install={"default": True})
        self.run_cli("--yes")
        self.assertEqual(self.run_cli("--yes", "--uninstall")[0], 0)
        self.assertEqual(self.hooks_of("uninstall", core=True), ["grub"])
        self.assertEqual(self.run_cli("--yes", "--uninstall", "--only", "core")[0], 0)
        self.assertEqual(self.hooks_of("uninstall", core=True), ["grub", "core"])
        self.assertNotIn("core", state.read(str(self.rootdir))["parts"])


class Removal(Base):
    def test_an_uninstall_stops_python_writing_new_bytecode(self):
        self.part("grub", install={"default": True})
        before = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = False
            self.run_cli("--yes", "--uninstall")
            self.assertTrue(sys.dont_write_bytecode)
        finally:
            sys.dont_write_bytecode = before


class Events(Base):
    def test_the_progress_stream_has_the_names_the_gui_parses(self):
        self.part("grub", install={"default": True}, detect={"found": True, "version": "0.7.1", "how": "source"})
        lines = []
        with (
            mock.patch.object(sys.__stdout__, "write", side_effect=lambda s: lines.append(s) or len(s)),
            mock.patch.object(sys.__stdout__, "flush"),
        ):
            rc = cli.main(
                ["core", "install", "--bundle", str(self.bundle), "--root", str(self.rootdir), "--progress", "json"]
            )
        self.assertEqual(rc, 0)
        events = [json.loads(x) for x in lines if x.strip()]
        names = [e["event"] for e in events]
        for n in ("step", "existing_install", "ok", "done"):
            self.assertIn(n, names)
        self.assertEqual(events[-1]["event"], "done")
        self.assertTrue(events[-1]["ok"])
        self.assertTrue(all(isinstance(e["t"], float) or isinstance(e["t"], int) for e in events))


class Findings(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(detect.finding(None, "1.0.0").kind, "none")
        self.assertEqual(detect.finding({"found": False}, "1.0.0").kind, "none")
        k = lambda v: detect.finding({"found": True, "version": v}, "1.0.0").kind  # noqa: E731
        self.assertEqual(
            (k("0.7.1"), k("1.0.0"), k("1.2.0"), k(None), k("git-abc")), ("older", "same", "newer", "unknown", "older")
        )

    def test_notice_wording(self):
        f = detect.finding(
            {
                "found": True,
                "version": "0.7.1",
                "how": "package:deb",
                "missing": ["theme"],
                "legacy": True,
                "old_names": ["usr/local/bin/x"],
            },
            "1.0.0",
        )
        text = "\n".join(detect.notice(f, "1.0.0", "Material GRUB"))
        self.assertIn("Found Material GRUB 0.7.1, a deb package.", text)
        self.assertIn("Pieces that are missing and will be put back: theme.", text)
        self.assertIn("no state record yet", text)
        self.assertIn("Old command names will be removed: /usr/local/bin/x.", text)

    def test_policy_commands_per_package_manager(self):
        for how, cmd in (
            ("package:rpm", "sudo dnf upgrade p"),
            ("package:deb", "sudo apt install --only-upgrade p"),
            ("package:pacman", "sudo pacman -Syu p"),
        ):
            f = detect.finding({"found": True, "version": "1.0.0", "how": how}, "1.0.0")
            ok, msg = detect.policy(f, "1.0.0", "source", "P", "p")
            self.assertFalse(ok)
            self.assertIn(cmd, msg)
        self.assertTrue(detect.policy(f, "1.0.0", "source", "P", "p", force=True)[0])
        self.assertTrue(detect.policy(f, "1.0.0", "package", "P", "p")[0])

    def test_adopting(self):
        src = detect.finding({"found": True, "version": "1.0.0", "how": "source"}, "1.0.0")
        pkg = detect.finding({"found": True, "version": "1.0.0", "how": "package:rpm"}, "1.0.0")
        self.assertTrue(detect.adopting(src, "package"))
        self.assertFalse(detect.adopting(src, "source"))
        self.assertFalse(detect.adopting(pkg, "package"))
        self.assertFalse(detect.adopting(detect.finding(None), "package"))


class ManifestAdditions(Base):
    def test_relative_entry_options_layouts_package(self):
        self.part(
            "plymouth",
            install={
                "package": "material-plymouth",
                "layouts": ["normal", "bogus"],
                "options": [{"name": "no-cmdline", "takes": "flag", "summary": "s"}, {"name": "Bad Name"}],
            },
        )
        (p,) = plugins.discover_bundle(self.bundle)
        self.assertIsNone(p.problem)
        self.assertTrue(Path(p.entry).is_absolute() and Path(p.entry).is_file())
        self.assertEqual(
            (p.package, p.layouts, p.source), ("material-plymouth", ["normal"], self.bundle / "parts/plymouth")
        )
        self.assertEqual(p.options, [{"name": "no-cmdline", "takes": "flag", "summary": "s"}])
        self.assertTrue(any("install option is malformed" in w for w in p.warnings))

    def test_a_relative_entry_that_does_not_exist_is_still_a_problem(self):
        self.part("plymouth")
        (self.bundle / "parts/plymouth/entry.py").unlink()
        (p,) = plugins.discover_bundle(self.bundle)
        self.assertIn("entry file", p.problem)

    def test_an_empty_or_missing_bundle(self):
        self.assertEqual(plugins.discover_bundle(self.d / "nothing"), [])


if __name__ == "__main__":
    unittest.main()
