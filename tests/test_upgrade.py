"""Existing installs: detection, the notice, the policy (downgrade, package vs source), the state record, migration steps with backup and rollback,
and the installer's glue. Everything runs on scratch roots; nothing touches this machine. stdlib only. usage: python3 tests/test_upgrade.py"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
sys.path.insert(0, str(ROOT / "install"))
import mgdetect  # noqa: E402
import mgmigrate  # noqa: E402


def make_install(
    root,
    version="0.7.1",
    layout="normal",
    state=None,
    drop=(),
    conf="STYLE=list\nSCHEME=dark\n",
    overrides=None,
    gui=False,
):
    """A plausible installed system under `root`, the way 0.7.x leaves it."""
    files = mgdetect.IMMUTABLE_FILES if layout == "immutable" else mgdetect.FILES
    for key, rel in files.items():
        if key in drop:
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(version + "\n" if key == "package" else "#!/bin/sh\n")
    if layout == "immutable":
        (root / "var/lib/material-grub").mkdir(parents=True, exist_ok=True)
        (root / "var/lib/material-grub/env").write_text("MG_IMMUTABLE=1\n")
    if "theme" not in drop:
        (root / "boot/grub2/themes/material").mkdir(parents=True, exist_ok=True)
    if conf is not None:
        (root / "etc").mkdir(parents=True, exist_ok=True)
        (root / "etc/material-grub.conf").write_text(conf)
    if overrides is not None:
        (root / "etc/material-grub").mkdir(parents=True, exist_ok=True)
        (root / "etc/material-grub/overrides.json").write_text(json.dumps(overrides))
    if gui:
        (root / "usr/share/material-grub-gui").mkdir(parents=True, exist_ok=True)
    if state:
        mgdetect.write(str(root), state)
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        for name, val in (
            ("MATERIAL_PLUGIN_PATH", str(self.r / "none")),
            ("MATERIAL_OVERRIDES", "/nonexistent/overrides.json"),
        ):
            patch = unittest.mock.patch.dict(os.environ, {name: val})
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def detect(self, target="1.0.0", **kw):
        return mgdetect.detect(str(self.r), target, **kw)


class Detection(Base):
    def test_nothing_installed(self):
        self.assertEqual(self.detect().kind, "none")

    def test_settings_left_behind_by_an_uninstall_are_not_an_install(self):
        (self.r / "etc").mkdir()
        (self.r / "etc/material-grub.conf").write_text("STYLE=list\n")
        self.assertEqual(self.detect().kind, "none")

    def test_versions_are_compared(self):
        make_install(self.r, "0.7.1")
        for target, kind in (
            ("1.0.0", "older"),
            ("0.7.1", "same"),
            ("0.7.0", "newer"),
            ("0.10.0", "older"),
            ("0.7.1.1", "older"),
        ):
            self.assertEqual(self.detect(target).kind, kind, target)

    def test_version_tuple_is_forgiving(self):
        self.assertEqual(mgdetect.version_tuple("1.0.0"), (1, 0, 0))
        self.assertLess(mgdetect.version_tuple("0.9.0"), mgdetect.version_tuple("0.10.0"))
        self.assertEqual(mgdetect.version_tuple("?"), (0,))
        self.assertEqual(mgdetect.version_tuple(None), (0,))
        self.assertEqual(mgdetect.version_tuple("1.0.0-rc1"), (1, 0, 0))

    def test_an_install_whose_version_cannot_be_read(self):
        make_install(self.r, drop=("package",))
        f = self.detect()
        self.assertEqual(f.kind, "unknown")
        self.assertIn("package", f.missing)

    def test_missing_pieces_are_named_and_the_kind_stays(self):
        make_install(self.r, drop=("hook15", "postprocess"))
        f = self.detect()
        self.assertEqual(f.kind, "older")
        self.assertEqual(sorted(f.missing), ["hook15", "postprocess"])

    def test_a_missing_theme_counts_as_missing(self):
        make_install(self.r, drop=("theme",))
        self.assertEqual(self.detect().missing, ["theme"])

    def test_an_install_from_before_the_state_record_is_legacy(self):
        make_install(self.r)
        f = self.detect()
        self.assertTrue(f.legacy)
        self.assertIsNone(f.state)

    def test_state_record_wins_for_how_and_parts(self):
        make_install(
            self.r,
            state={
                "state": 1,
                "version": "0.7.1",
                "how": "package:rpm",
                "layout": "normal",
                "parts": {"core": "0.7.1", "plymouth": "0.1.0"},
            },
        )
        f = self.detect()
        self.assertFalse(f.legacy)
        self.assertEqual((f.how, f.parts["plymouth"]), ("package:rpm", "0.1.0"))

    def test_who_owns_the_files(self):
        make_install(self.r)
        asked = []

        def owner(p):
            asked.append(p)
            return "package:deb"

        f = self.detect(owner=owner)
        self.assertEqual(f.how, "package:deb")
        self.assertEqual(asked, [self.r / "usr/share/material-grub/VERSION"])

    def test_immutable_layout(self):
        make_install(self.r, layout="immutable")
        f = self.detect()
        self.assertEqual((f.layout, f.how, f.version), ("immutable", "immutable", "0.7.1"))

    def test_old_command_names_are_noticed(self):
        make_install(self.r)
        (self.r / "usr/local/bin/material-grub-apply").write_text("#!/bin/sh\n")
        self.assertEqual(self.detect().old_names, ["usr/local/bin/material-grub-apply"])

    def test_what_the_user_has_is_summarised(self):
        make_install(
            self.r,
            gui=True,
            overrides={
                "version": 1,
                "seed": {"mode": "single", "color": "#7E57C2"},
                "entries": [{"match": {"key": "fedora"}, "name": "x"}],
            },
        )
        f = self.detect()
        text = " ".join(f.details)
        self.assertIn("style list", text)
        self.assertIn("one seed colour", text)
        self.assertIn("1 customised entry", text)
        self.assertIn("GUI installed", text)
        self.assertEqual(f.parts["gui"], "0.7.1")

    def test_plugins_are_listed_as_parts(self):
        make_install(self.r)
        d = self.r / "usr/share/material-boot/plugins.d"
        d.mkdir(parents=True)
        entry = self.r / "e.py"
        entry.write_text("def main(a, c): return 0\n")
        (d / "plymouth.json").write_text(
            json.dumps({"manifest": 1, "name": "plymouth", "version": "0.1.0", "core_api": 1, "entry": str(entry)})
        )
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("MATERIAL_PLUGIN_PATH")
            f = self.detect()
        self.assertEqual(f.parts["plymouth"], "0.1.0")


class Notice(Base):
    def test_no_install_no_notice(self):
        self.assertEqual(mgdetect.notice(self.detect(), "1.0.0"), [])

    def test_the_notice_says_what_happens(self):
        make_install(self.r, drop=("hook15",), gui=True)
        (self.r / "usr/local/bin/material-grub-apply").write_text("x")
        text = "\n".join(mgdetect.notice(self.detect(), "1.0.0"))
        for word in (
            "0.7.1",
            "style list",
            "update it to 1.0.0",
            "settings",
            "hook15",
            "no state record",
            "material-grub-apply",
            "GUI",
        ):
            self.assertIn(word, text)

    def test_same_and_newer_and_unknown(self):
        make_install(self.r)
        self.assertIn("same version", "\n".join(mgdetect.notice(self.detect("0.7.1"), "0.7.1")))
        self.assertIn("NEWER", "\n".join(mgdetect.notice(self.detect("0.7.0"), "0.7.0")))
        make_install(self.r, drop=("package",))
        os.unlink(self.r / "usr/share/material-grub/VERSION") if (
            self.r / "usr/share/material-grub/VERSION"
        ).exists() else None
        self.assertIn("cannot be read", "\n".join(mgdetect.notice(self.detect(), "1.0.0")))


class Policy(Base):
    def found(self, version="0.7.1", how="source", **kw):
        make_install(
            self.r, version, state={"state": 1, "version": version, "how": how, "layout": "normal", "parts": {}}, **kw
        )
        return self.detect()

    def test_nothing_to_refuse_on_a_fresh_system(self):
        self.assertEqual(mgdetect.policy(self.detect(), "1.0.0", "source"), (True, ""))

    def test_an_update_is_fine(self):
        self.assertTrue(mgdetect.policy(self.found(), "1.0.0", "source")[0])

    def test_a_downgrade_is_refused_unless_forced(self):
        f = self.found("1.1.0")
        ok, msg = mgdetect.policy(f, "1.0.0", "source")
        self.assertFalse(ok)
        self.assertIn("1.1.0", msg)
        self.assertIn("--force", msg)
        self.assertTrue(mgdetect.policy(f, "1.0.0", "source", force=True)[0])

    def test_a_downgrade_by_a_package_is_refused_too(self):
        self.assertFalse(mgdetect.policy(self.found("1.1.0"), "1.0.0", "package")[0])

    def test_a_source_install_over_a_package_is_refused_with_the_right_command(self):
        for how, word in (
            ("package:rpm", "dnf"),
            ("package:deb", "apt"),
            ("package:pacman", "pacman"),
            ("package:unknown", "package manager"),
        ):
            ok, msg = mgdetect.policy(self.found(how=how), "1.0.0", "source")
            self.assertFalse(ok, how)
            self.assertIn(word, msg)
        self.assertTrue(mgdetect.policy(self.found(how="package:rpm"), "1.0.0", "source", force=True)[0])

    def test_a_package_over_a_package_or_a_source_install_goes_on(self):
        self.assertTrue(mgdetect.policy(self.found(how="package:rpm"), "1.0.0", "package")[0])
        f = self.found(how="source")
        self.assertTrue(mgdetect.policy(f, "1.0.0", "package")[0])
        self.assertTrue(mgdetect.adopting(f, "package"))
        self.assertFalse(mgdetect.adopting(f, "source"))
        self.assertFalse(mgdetect.adopting(self.found(how="package:deb"), "package"))


class State(Base):
    def test_roundtrip_history_and_merge(self):
        root = str(self.r)
        self.assertIsNone(mgdetect.read(root))
        mgdetect.record(root, "0.7.1", "source", "normal", {"core": "0.7.1"}, now="t1")
        d = mgdetect.record(
            root,
            "1.0.0",
            "package:rpm",
            "normal",
            {"core": "1.0.0", "plymouth": {"version": "0.1.0", "changes": ["cmdline"]}},
            now="t2",
        )
        self.assertEqual((d["version"], d["how"]), ("1.0.0", "package:rpm"))
        self.assertEqual([(h["from"], h["to"]) for h in d["history"]], [(None, "0.7.1"), ("0.7.1", "1.0.0")])
        d = mgdetect.record(root, "1.0.0", "package:rpm", "normal", {"core": "1.0.0"}, now="t3")
        self.assertEqual(d["parts"]["plymouth"]["changes"], ["cmdline"], "a part's own record is kept")
        self.assertEqual(len(d["history"]), 2, "an install of the same version adds no history")
        self.assertEqual(mgdetect.read(root), d)

    def test_unreadable_records_are_ignored(self):
        p = mgdetect.state_path(str(self.r))
        p.parent.mkdir(parents=True)
        for text in ("{not json", "[1]", json.dumps({"state": 99})):
            p.write_text(text)
            self.assertIsNone(mgdetect.read(str(self.r)))

    def test_history_is_bounded(self):
        for i in range(40):
            mgdetect.record(str(self.r), f"0.{i}.0", "source", "normal", now=str(i))
        self.assertLessEqual(len(mgdetect.read(str(self.r))["history"]), 20)

    def test_no_temp_files_are_left(self):
        mgdetect.record(str(self.r), "1.0.0", "source", "normal")
        self.assertEqual([p.name for p in mgdetect.state_path(str(self.r)).parent.iterdir()], ["state.json"])


class Boom(mgmigrate.Step):
    id, since, title = "boom", "1.0.0", "fail"

    def __init__(self, path):
        self.path = path

    def touches(self, ctx):
        return [self.path]

    def plan(self, ctx):
        return ["break it"]

    def apply(self, ctx):
        self.path.write_text("half done")
        raise RuntimeError("nope")


class Edit(mgmigrate.Step):
    id, since, title = "edit", "1.0.0", "edit a file"

    def __init__(self, path, text="edited\n"):
        self.path, self.text = path, text

    def touches(self, ctx):
        return [self.path]

    def plan(self, ctx):
        return [] if self.path.exists() and self.path.read_text() == self.text else ["write " + self.text.strip()]

    def apply(self, ctx):
        self.path.write_text(self.text)


class Migrations(Base):
    def ctx(self):
        return mgmigrate.context(str(self.r), mgmigrate.backup_dir(str(self.r), "0.7.1", "1.0.0", now="T"))

    def test_steps_run_only_for_versions_they_are_new_in(self):
        a, b = Edit(self.r / "a"), Edit(self.r / "b")
        a.since, b.since = "1.0.0", "1.1.0"
        self.assertEqual(mgmigrate.steps_for("0.7.1", "1.0.0", [a, b]), [a])
        self.assertEqual(mgmigrate.steps_for("0.7.1", "1.1.0", [a, b]), [a, b])
        self.assertEqual(mgmigrate.steps_for("1.0.0", "1.1.0", [a, b]), [b])
        self.assertEqual(mgmigrate.steps_for("1.1.0", "1.1.0", [a, b]), [])
        self.assertEqual(
            mgmigrate.steps_for(None, "1.0.0", [a, b]), [a], "an unknown version checks every step up to the target"
        )

    def test_plan_lists_only_what_would_change(self):
        a = Edit(self.r / "a")
        (self.r / "b").write_text("edited\n")
        b = Edit(self.r / "b")
        self.assertEqual([s for s, _ in mgmigrate.plan(self.ctx(), [a, b])], [a])

    def test_run_is_idempotent_and_backs_up(self):
        f = self.r / "a"
        f.write_text("mine\n")
        steps = [Edit(f)]
        res = mgmigrate.run(self.ctx(), steps)
        self.assertEqual([r[1] for r in res], ["done"])
        self.assertEqual(f.read_text(), "edited\n")
        self.assertEqual((self.ctx().backup / "a").read_text(), "mine\n")
        self.assertEqual([r[1] for r in mgmigrate.run(self.ctx(), steps)], ["skipped"])

    def test_a_failing_step_puts_every_touched_file_back_and_stops(self):
        a, b, c = self.r / "a", self.r / "b", self.r / "c"
        a.write_text("mine\n")
        b.write_text("keep\n")
        res = mgmigrate.run(self.ctx(), [Edit(a), Boom(b), Edit(c)])
        self.assertEqual([r[1] for r in res], ["done", "failed"], "the step after the failure is not run")
        self.assertEqual(a.read_text(), "mine\n", "an earlier step's change is undone too")
        self.assertEqual(b.read_text(), "keep\n")
        self.assertFalse(c.exists())
        self.assertIn("put back", res[-1][2])

    def test_a_file_a_failed_run_created_is_removed(self):
        new = self.r / "new"
        mgmigrate.run(self.ctx(), [Boom(new)])
        self.assertFalse(new.exists())

    def test_backup_directory_name(self):
        self.assertEqual(
            mgmigrate.backup_dir("", "0.7.1", "1.0.0", "T").as_posix(),
            "/var/backups/material-grub/upgrade-0.7.1-to-1.0.0-T",
        )
        self.assertIn("upgrade-unknown-to-1.0.0", mgmigrate.backup_dir("", None, "1.0.0", "T").name)


class ConfSamples(Base):
    def step(self):
        return mgmigrate.ConfSamples()

    def conf(self, text):
        (self.r / "etc").mkdir(exist_ok=True)
        (self.r / "etc/material-grub.conf").write_text(text)
        return mgmigrate.context(str(self.r), self.r / "bk")

    def test_adds_the_new_options_and_keeps_everything_else(self):
        old = "# my comment\nSTYLE=list\nHINTS=off   # no hints\n\n#TIMEOUT=\n"
        ctx = self.conf(old)
        mgmigrate.run(ctx, [self.step()])
        text = (self.r / "etc/material-grub.conf").read_text()
        self.assertTrue(text.startswith(old), "the user's lines are untouched and first")
        for k in ("PLYMOUTH", "PLYMOUTH_BAR", "PLYMOUTH_MOTION"):
            self.assertIn(f"#{k}=", text)
        import mgrub

        c = mgrub.load_conf(str(self.r / "etc/material-grub.conf"))
        self.assertEqual(
            (c["STYLE"], c["HINTS"], c["PLYMOUTH_MOTION"]),
            ("list", "off", "full"),
            "samples are comments: defaults apply",
        )

    def test_idempotent(self):
        ctx = self.conf("STYLE=list\n")
        mgmigrate.run(ctx, [self.step()])
        once = (self.r / "etc/material-grub.conf").read_text()
        res = mgmigrate.run(ctx, [self.step()])
        self.assertEqual(res[0][1], "skipped")
        self.assertEqual((self.r / "etc/material-grub.conf").read_text(), once)

    def test_never_touches_a_value_the_user_set(self):
        ctx = self.conf("PLYMOUTH=off\nPLYMOUTH_MOTION=calm\n")
        self.assertEqual([k for k, _, _ in self.step().missing(ctx)], ["PLYMOUTH_BAR"])
        mgmigrate.run(ctx, [self.step()])
        text = (self.r / "etc/material-grub.conf").read_text()
        self.assertIn("PLYMOUTH=off\nPLYMOUTH_MOTION=calm\n", text)

    def test_a_commented_sample_counts_as_present(self):
        ctx = self.conf("#PLYMOUTH=on\n#PLYMOUTH_BAR=progress\n# PLYMOUTH_MOTION=off\n")
        self.assertEqual(self.step().plan(ctx), [])

    def test_no_file_nothing_to_do_and_a_file_without_a_final_newline(self):
        self.assertEqual(self.step().plan(mgmigrate.context(str(self.r))), [])
        ctx = self.conf("STYLE=list")
        mgmigrate.run(ctx, [self.step()])
        self.assertTrue((self.r / "etc/material-grub.conf").read_text().startswith("STYLE=list\n"))

    def test_the_file_mode_is_kept(self):
        ctx = self.conf("STYLE=list\n")
        os.chmod(self.r / "etc/material-grub.conf", 0o600)
        mgmigrate.run(ctx, [self.step()])
        self.assertEqual((self.r / "etc/material-grub.conf").stat().st_mode & 0o777, 0o600)


class InstallerGlue(Base):
    def installer(self, *argv, from_package=False):
        import installer

        inst = installer.Installer(list(argv))
        inst.yes, inst.tuimode, inst.from_package = True, "no", from_package
        self.mod = installer
        return inst

    def run_glue(self, inst, fn, *a, tty=False, **kw):
        class Out(io.StringIO):
            def isatty(self):
                return tty

        out = Out()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), unittest.mock.patch.object(
            self.mod, "VERSION_TEXT", return_value="1.0.0"
        ):
            try:
                return fn(*a, **kw), out.getvalue()
            except SystemExit as e:
                return e.code, out.getvalue()

    def test_a_fresh_system_prints_nothing_and_goes_on(self):
        inst = self.installer()
        f, out = self.run_glue(inst, inst.existing_install, str(self.r))
        self.assertEqual(f.kind, "none")
        self.assertNotIn("existing install", out)

    def test_an_old_install_gets_the_notice_and_the_plan(self):
        make_install(self.r, conf="STYLE=list\n")
        inst = self.installer()
        f, out = self.run_glue(inst, inst.existing_install, str(self.r))
        self.assertEqual(f.kind, "older")
        for word in (
            "An existing install was found",
            "0.7.1",
            "update it to 1.0.0",
            "Will change in your files",
            "#PLYMOUTH=on",
            "upgrade-0.7.1-to-1.0.0",
        ):
            self.assertIn(word, out)

    def test_a_downgrade_stops_the_installer(self):
        make_install(self.r, "1.1.0")
        inst = self.installer()
        code, out = self.run_glue(inst, inst.existing_install, str(self.r))
        self.assertEqual(code, 1)
        self.assertIn("--force", out)
        inst = self.installer("--force")
        inst.force = True
        f, _ = self.run_glue(inst, inst.existing_install, str(self.r))
        self.assertEqual(f.kind, "newer")

    def test_a_source_install_over_a_package_stops_but_a_package_does_not(self):
        make_install(
            self.r, state={"state": 1, "version": "0.7.1", "how": "package:rpm", "layout": "normal", "parts": {}}
        )
        code, out = self.run_glue(self.installer(), self.installer().existing_install, str(self.r))
        self.assertEqual(code, 1)
        self.assertIn("dnf", out)
        inst = self.installer(from_package=True)
        f, _ = self.run_glue(inst, inst.existing_install, str(self.r))
        self.assertEqual(f.kind, "older")

    def test_an_interactive_no_changes_nothing(self):
        make_install(self.r)
        inst = self.installer()
        inst.yes, inst.tuimode = False, "auto"
        with unittest.mock.patch("sys.stdin.isatty", return_value=True), unittest.mock.patch(
            "sys.stdout.isatty", return_value=True
        ), unittest.mock.patch("builtins.input", return_value="n"):
            code, out = self.run_glue(inst, inst.existing_install, str(self.r), tty=True)
        self.assertEqual(code, 0)
        self.assertIn("Nothing was changed", out)

    def test_the_json_mode_emits_one_event_with_the_finding(self):
        make_install(self.r)
        inst = self.installer()
        events = []
        inst.json = True
        inst.emit = lambda ev, **kw: events.append((ev, kw))
        self.run_glue(inst, inst.existing_install, str(self.r))
        ev = [kw for name, kw in events if name == "existing_install"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["found"]["version"], "0.7.1")
        self.assertTrue(ev[0]["notice"])

    def test_after_install_migrates_backs_up_and_records(self):
        make_install(self.r, conf="STYLE=list\n")
        inst = self.installer()
        self.run_glue(inst, inst.existing_install, str(self.r))
        _, out = self.run_glue(inst, inst.after_install, str(self.r))
        self.assertIn("#PLYMOUTH=on", (self.r / "etc/material-grub.conf").read_text())
        backups = list((self.r / "var/backups/material-grub").glob("upgrade-0.7.1-to-1.0.0-*/etc/material-grub.conf"))
        self.assertEqual([b.read_text() for b in backups], ["STYLE=list\n"])
        st = mgdetect.read(str(self.r))
        self.assertEqual((st["version"], st["how"], st["layout"]), ("1.0.0", "source", "normal"))
        self.assertEqual(st["history"][-1]["from"], "0.7.1")
        self.assertEqual(st["parts"]["grub"], "1.0.0")
        (self.r / "usr/share/material-grub/VERSION").write_text("1.0.0\n")  # what the file copy of a real install does
        f = mgdetect.detect(str(self.r), "1.0.0")
        self.assertFalse(f.legacy)
        self.assertEqual(f.kind, "same")

    def test_after_install_on_a_fresh_system_just_records(self):
        (self.r / "etc").mkdir()
        (self.r / "etc/material-grub.conf").write_text(
            "#PLYMOUTH=on\n#PLYMOUTH_BAR=indeterminate\n#PLYMOUTH_MOTION=full\n"
        )
        inst = self.installer()
        self.run_glue(inst, inst.existing_install, str(self.r))
        self.run_glue(inst, inst.after_install, str(self.r))
        self.assertEqual(
            mgdetect.read(str(self.r))["history"][-1],
            {"from": None, "to": "1.0.0", "at": mgdetect.read(str(self.r))["installed_at"]},
        )
        self.assertFalse((self.r / "var/backups/material-grub").exists(), "no file changed, so no backup directory")

    def test_a_failing_migration_is_a_warning_not_a_failed_install(self):
        make_install(self.r)
        inst = self.installer()
        self.run_glue(inst, inst.existing_install, str(self.r))
        with unittest.mock.patch.object(mgmigrate.ConfSamples, "apply", side_effect=RuntimeError("disk full")):
            _, out = self.run_glue(inst, inst.after_install, str(self.r))
        self.assertIn("failed", out)
        self.assertNotIn("#PLYMOUTH", (self.r / "etc/material-grub.conf").read_text())
        self.assertEqual(mgdetect.read(str(self.r))["version"], "1.0.0", "the install is still recorded")


PKG = ROOT / "dist/material-grub"


@unittest.skipUnless((PKG / "res/1920x1080").is_dir(), "no built package")
class RealStagedInstall(Base):
    """The fingerprints are checked against what install.sh really puts on disk, then an older install is updated through the installer's glue."""

    def stage(self):
        import subprocess

        subprocess.run(
            [
                "sh",
                str(ROOT / "install/install.sh"),
                "--dest",
                str(self.r),
                "--no-run",
                "--pkg",
                str(PKG),
                "--res",
                "1920x1080",
            ],
            check=True,
            capture_output=True,
        )
        # the theme directory GRUB loads from (--no-run does not build it): an empty one is what the fingerprint looks for
        (self.r / "boot/grub2/themes/material").mkdir(parents=True)

    def test_the_fingerprints_match_the_real_install(self):
        self.stage()
        f = self.detect(target=(PKG / "VERSION").read_text().strip())
        self.assertEqual((f.kind, f.missing, f.legacy), ("same", [], True))

    def test_an_install_without_the_new_options_is_updated_and_recorded(self):
        self.stage()
        conf = self.r / "etc/material-grub.conf"
        kept = [ln for ln in conf.read_text().splitlines() if "PLYMOUTH" not in ln] + ["STYLE=split"]
        conf.write_text("\n".join(kept) + "\n")  # what 0.7.x wrote
        (self.r / "usr/share/material-grub/VERSION").write_text("0.7.1\n")
        import installer

        inst = installer.Installer([])
        inst.yes, inst.tuimode = True, "no"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), unittest.mock.patch.object(
            installer, "VERSION_TEXT", return_value="1.0.0"
        ):
            f = inst.existing_install(str(self.r))
            (self.r / "usr/share/material-grub/VERSION").write_text("1.0.0\n")
            inst.after_install(str(self.r))
        self.assertEqual((f.kind, f.version), ("older", "0.7.1"))
        text = conf.read_text()
        self.assertIn("STYLE=split", text)
        self.assertIn("#PLYMOUTH_MOTION=full", text)
        self.assertEqual(mgdetect.read(str(self.r))["history"][-1]["from"], "0.7.1")
        self.assertFalse(mgdetect.detect(str(self.r), "1.0.0").legacy)


if __name__ == "__main__":
    unittest.main()
