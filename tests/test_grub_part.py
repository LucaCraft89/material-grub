"""material-grub as a part of Material Boot (install/part_grub.py, material-boot-part.json). Needs the core: next to the checkout, or MATERIAL_LIB.
The last class builds the theme twice (about a minute each) to show that the unified installer and `install.sh` produce the same files. usage: python3 tests/test_grub_part.py"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import mgcore  # noqa: E402,F401  (puts the core on sys.path: it must come first)

# isort: split
import material_boot  # noqa: E402
from material_boot import cli, plugins  # noqa: E402

sys.path.insert(0, str(ROOT / "install"))
import part_grub  # noqa: E402
from material_boot.conf import CONF_DEFAULTS as DEFAULTS  # noqa: E402

MANIFEST = ROOT / "material-boot-part.json"


def ctx(**kw):
    kw.setdefault("conf", {"STYLE": "rail", "SCHEME": "dark", "COOKIE": "on", "LOGO": "on", "HINTS": "off"})
    return plugins.make_ctx(**kw)


class Manifest(unittest.TestCase):
    def setUp(self):
        self.m = json.loads(MANIFEST.read_text())
        self.p = plugins.read_manifest(MANIFEST)

    def test_it_is_a_usable_part_and_follows_the_version_file(self):
        self.assertIsNone(self.p.problem, self.p.problem)
        self.assertEqual(self.p.name, "grub")
        self.assertEqual(
            self.p.version, (ROOT / "VERSION").read_text().strip(), "bump material-boot-part.json with VERSION"
        )
        self.assertEqual(self.p.warnings, [])

    def test_the_questions_of_the_installer_screen_are_valid_and_their_targets_exist(self):
        # the core reads install.questions (material-boot-core 1.1.0; an older core ignores the field): none may be dropped, and every target is real
        if not hasattr(self.p, "questions"):
            self.skipTest("this core is older than install.questions")
        asked = json.loads(MANIFEST.read_text())["install"]["questions"]
        self.assertEqual(
            [q["id"] for q in self.p.questions], [q["id"] for q in asked], "a question was dropped as malformed"
        )
        options = {o["name"] for o in self.p.options}
        for q in self.p.questions:
            t = q["target"]
            if "option" in t:
                self.assertIn(t["option"], options, q["id"])
            else:
                self.assertIn(t["conf"], DEFAULTS, q["id"])  # a settings key the core knows
        by = {q["id"]: q for q in self.p.questions}
        self.assertEqual(by["res"]["options"][0]["value"], "")  # automatic is the first choice and passes nothing
        self.assertTrue(all(o["value"] == "" or o["value"].count("x") == 1 for o in by["res"]["options"]))
        self.assertIn("1920x1080", [o["value"] for o in by["res"]["options"]])

    def test_the_entry_file_defines_what_the_manifest_lists(self):
        entry = (MANIFEST.parent / self.m["entry"]).resolve()
        self.assertEqual(entry, (ROOT / "install/part_grub.py"))
        for h in self.m["hooks"]:
            self.assertTrue(callable(getattr(part_grub, "hook_" + h, None)), h)
        self.assertTrue(callable(part_grub.main))

    def test_every_declared_option_is_one_the_hook_passes_on(self):
        for o in self.p.options:
            table = part_grub.FLAGS if o["takes"] == "flag" else part_grub.VALUES
            self.assertIn(o["name"], table, o)
        self.assertEqual(
            {o["name"] for o in self.p.options},
            set(part_grub.FLAGS) | set(part_grub.VALUES),
            "an option the hook knows is not declared",
        )

    def test_it_is_the_default_and_needs_nothing_but_the_core(self):
        self.assertTrue(self.p.default)
        self.assertEqual(self.p.needs, [])


class Arguments(unittest.TestCase):
    def test_the_installers_options_and_the_shared_look_become_the_engines_options(self):
        a = part_grub.engine_args(
            ctx(
                options={"res": "1920x1080", "stage-only": True, "with-gui": True},
                conf={"STYLE": "list", "SCHEME": "light", "COOKIE": "off", "LOGO": "on", "HINTS": "off"},
            )
        )
        self.assertEqual(a[:2], ["--yes", "--no-tui"])
        for want in (["--res", "1920x1080"], ["--style", "list"], ["--scheme", "light"]):
            i = a.index(want[0])
            self.assertEqual(a[i : i + 2], want)
        for flag in ("--stage-only", "--with-gui", "--no-cookie", "--no-hints"):
            self.assertIn(flag, a)
        for flag in ("--cookie", "--logo", "--no-logo", "--hints", "--immutable", "--from-package", "--progress"):
            self.assertNotIn(flag, a)

    def test_what_is_the_default_is_not_passed(self):
        """install.sh leaves what was not chosen as a commented sample; the files of the two entry points must be the same."""
        a = part_grub.engine_args(ctx(conf=dict(DEFAULTS)))
        for flag in ("--style", "--scheme", "--cookie", "--no-cookie", "--logo", "--no-logo", "--hints", "--no-hints"):
            self.assertNotIn(flag, a)

    def test_how_and_json_are_passed_on(self):
        a = part_grub.engine_args(ctx(how="package", json=True))
        self.assertIn("--from-package", a)
        self.assertEqual(a[a.index("--progress") + 1], "json")
        self.assertIn("--immutable", part_grub.engine_args(ctx(how="immutable")))

    def test_a_staged_root_is_refused_with_a_sentence(self):
        with self.assertRaisesRegex(RuntimeError, "cannot work in a staged tree"):
            part_grub.run_engine(ctx(root="/tmp/x"), ["--yes"])


class Detect(unittest.TestCase):
    def test_nothing_installed_in_an_empty_root(self):
        with tempfile.TemporaryDirectory() as t:
            d = part_grub.hook_detect(ctx(root=t, target_version="1.0.0"))
        self.assertFalse(d["found"])

    def test_the_core_reads_what_the_hook_returned(self):
        from material_boot import detect

        with tempfile.TemporaryDirectory() as t:
            f = detect.finding(part_grub.hook_detect(ctx(root=t, target_version="1.0.0")), "1.0.0")
        self.assertEqual(f.kind, "none")

    def test_verify_reports_a_missing_install(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(
                part_grub.hook_verify(ctx(root=t, target_version="1.0.0")),
                ["Material GRUB is not installed after the install"],
            )

    def test_verify_has_nothing_to_say_about_what_was_only_built(self):
        self.assertEqual(part_grub.hook_verify(ctx(options={"stage-only": True})), [])


class Events(unittest.TestCase):
    """In a json run the engine's events go through ctx.progress and stdout carries nothing of its own."""

    def test_events_are_relayed_and_done_is_left_to_the_core(self):
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t) / "installer.py"
            fake.write_text(
                "import json, os\nprint(json.dumps({'event': 'step', 'msg': os.environ.get('MATERIAL_BOOT_UNIFIED')}))\nprint('not json')\nprint(json.dumps({'event': 'done', 'rc': 0}))\n"
            )
            got = []
            c = ctx(json=True, progress=got.append)
            with mock.patch.object(part_grub, "ENGINE", fake):
                rc, lines = part_grub.run_engine(c, [])
        self.assertEqual(rc, 0)
        self.assertEqual([e["event"] for e in got], ["step", "log"])
        self.assertEqual(got[0]["msg"], "1", "the engine must be told that the unified installer runs it")
        self.assertEqual(got[1]["text"], "not json")
        self.assertEqual(len(lines), 3)


class InstalledCopy(unittest.TestCase):
    """The copy install.sh leaves in /usr/share/material-grub/bin has no engine: it can detect, verify, doctor and uninstall, and says so for the rest."""

    def test_it_refuses_to_install_and_names_the_way(self):
        with mock.patch.object(part_grub, "ENGINE", Path("/nonexistent/installer.py")):
            with self.assertRaisesRegex(RuntimeError, "installed copy of the part"):
                part_grub.run_engine(ctx(), ["--yes"])
            with self.assertRaisesRegex(RuntimeError, "installed copy of the part"):
                part_grub.hook_plan(ctx())

    def test_uninstall_runs_the_script_next_to_it(self):
        calls = []
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "uninstall.sh").write_text("#!/bin/sh\n")
            with mock.patch.object(part_grub, "ENGINE", Path("/nonexistent/installer.py")):
                with mock.patch.object(part_grub, "HERE", Path(t)):
                    with mock.patch.object(part_grub, "run_cmd", lambda c, cmd: calls.append(cmd) or (0, [])):
                        self.assertEqual(part_grub.hook_uninstall(ctx()), {"changed": True})
        self.assertEqual(calls, [["sh", str(Path(t) / "uninstall.sh")]])

    def test_uninstall_without_the_script_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(part_grub, "ENGINE", Path("/nonexistent/installer.py")):
                with mock.patch.object(part_grub, "HERE", Path(t)):
                    with self.assertRaisesRegex(RuntimeError, "material-grub uninstall"):
                        part_grub.hook_uninstall(ctx())


def tree(d):
    out = {}
    for p in sorted(Path(d).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[str(p.relative_to(d))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@unittest.skipUnless(
    os.environ.get("MG_SLOW", "1") == "1" and shutil.which("rsvg-convert"),
    "slow: builds the theme twice (needs rsvg-convert)",
)
class SameThing(unittest.TestCase):
    """`install.sh --stage-only` and the unified installer's GRUB part (`material-boot core install --only grub --grub-stage-only`) build the same theme."""

    def test_both_entry_points_build_identical_files(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            common = ["--yes", "--no-tui", "--no-deps", "--scheme", "dark", "--style", "rail", "--res", "1920x1080"]
            legacy = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "install/installer.py"),
                    *common,
                    "--stage-only",
                    "--dist-out",
                    str(t / "a"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(legacy.returncode, 0, legacy.stdout[-800:] + legacy.stderr[-800:])
            part = ctx(
                options={"stage-only": True, "no-deps": True, "res": "1920x1080", "dist-out": str(t / "b")},
                conf={"STYLE": "rail", "SCHEME": "dark"},
            )
            out = io.StringIO()
            with redirect_stdout(out):
                res = part_grub.hook_install(part)
            self.assertEqual((res["changed"], res["record"]), (False, False))
            self.unified(t)
            a, b, c = tree(t / "a"), tree(t / "b"), tree(t / "c")
            self.assertTrue(a, "the legacy build is empty")
            self.assertEqual(sorted(a), sorted(b))
            self.assertEqual([k for k in a if a[k] != b[k]], [])
            self.assertEqual(sorted(a), sorted(c))
            self.assertEqual(
                [k for k in a if a[k] != c[k]],
                [],
                "the real `material-boot core install --only grub` builds something else",
            )
            self.assertEqual(
                self.recorded,
                {"core": material_boot.__version__},
                "a theme that was only built must not be recorded as installed",
            )

    def unified(self, t):
        """The real command, in a bundle made of this checkout and the running core, on a staged root."""
        core = (
            Path(material_boot.__file__).resolve().parent.parent
        )  # the checkout of the core (or /usr/share/material-boot)
        bundle, root = t / "bundle", t / "root"
        (bundle / "parts/grub").mkdir(parents=True)
        (bundle / "lib").mkdir()
        (bundle / "lib/material_boot").symlink_to(
            core / "material_boot" if (core / "material_boot").is_dir() else core / "lib/material_boot"
        )
        for d in ("scripts", "assets", "bin"):
            if not (core / d).exists():
                self.skipTest(f"the core at {core} has no {d}/ to make a bundle of")
            (bundle / d).symlink_to(core / d)
        shutil.copy(MANIFEST, bundle / "parts/grub/manifest.json")
        (bundle / "parts/grub/install").symlink_to(ROOT / "install")
        argv = [
            "core", "install", "--bundle", str(bundle), "--root", str(root), "--only", "grub", "--yes", "--scheme", "dark", "--style", "rail",
            "--grub-stage-only", "--grub-no-deps", "--grub-res", "1920x1080", "--grub-dist-out", str(t / "c"),
        ]  # fmt: skip
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.main(argv)
        self.assertEqual(rc, 0, out.getvalue()[-1500:])
        self.recorded = {
            k: v for k, v in json.loads((root / "var/lib/material-grub/state.json").read_text())["parts"].items()
        }


if __name__ == "__main__":
    unittest.main()
