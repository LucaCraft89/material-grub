"""The bundle (scripts/build_bundle.py, packaging/bundle/install.sh): a tarball with the core and the parts, checksums, a reproducible build, a release only
from tags, and an installer that works from the unpacked tree on a staged root. Fake parts are real git repositories."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_bundle  # noqa: E402

import material_boot  # noqa: E402
from material_boot import coreinstall, plugins, state  # noqa: E402

ENTRY = """
import json, os
def main(argv, core):
    return 0
def hook_detect(ctx):
    return None
def hook_plan(ctx):
    return ["would install {name}"]
def hook_install(ctx):
    d = os.path.join(ctx.root or "/", "var/lib/fake-{name}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "installed"), "w") as f:
        json.dump({{"style": ctx.conf.get("STYLE"), "how": ctx.how, "source": str(ctx.source)}}, f)
    return {{"changed": True, "notes": ["fake {name} installed"]}}
def hook_uninstall(ctx):
    return {{"changed": True}}
"""
SH = shutil.which("sh")  # by path: one test runs it with a PATH that has almost nothing in it
GIT = [
    "git",
    "-c",
    "user.name=t",
    "-c",
    "user.email=t@example.invalid",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "init.defaultBranch=main",
]


def fake_part(dest, name, version="1.0.0", manifest=True, **over):
    """A git repository with a part's manifest, its entry file and one untracked file (which must not end up in a bundle)."""
    dest = Path(dest)
    dest.mkdir(parents=True)
    (dest / "entry.py").write_text(ENTRY.format(name=name))
    (dest / "README.md").write_text(f"{name}\n")
    m = {
        "manifest": 2,
        "name": name,
        "title": name.title(),
        "version": version,
        "core_api": 2,
        "entry": "entry.py",
        "hooks": ["detect", "plan", "install", "uninstall"],
        "install": {"default": name == "grub"},
    }
    m.update(over)
    if manifest:
        (dest / "material-boot-part.json").write_text(json.dumps(m))
    subprocess.run([*GIT, "init", "-q"], cwd=dest, check=True)
    subprocess.run([*GIT, "add", "."], cwd=dest, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "x"], cwd=dest, check=True)
    (dest / "untracked.txt").write_text("not committed")
    return dest


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.grub = fake_part(self.d / "grub-repo", "grub")
        self.ply = fake_part(self.d / "ply-repo", "plymouth")
        self.cfg = self.d / "bundle.json"
        self.cfg.write_text(
            json.dumps(
                {
                    "format": 1,
                    "parts": {
                        "grub": {"repo": "x/grub", "ref": "release/0.8.0"},
                        "plymouth": {"repo": "x/plymouth", "ref": "main"},
                    },
                }
            )
        )
        self.local = {"grub": str(self.grub), "plymouth": str(self.ply)}

    def build(self, out="out", release=False, config=None, local=None, epoch=1700000000):
        return build_bundle.build(
            self.d / out, config or self.cfg, self.local if local is None else local, release, epoch
        )


class Build(Base):
    def test_the_tree(self):
        tar, stage = self.build()
        for f in (
            "install.sh",
            "VERSION",
            "LICENSE",
            "BUNDLE.json",
            "SHA256SUMS",
            "bin/material-boot",
            "scripts/build_data.py",
            "lib/material_boot/__init__.py",
            "lib/material_boot/VERSION",
            "assets/fonts/GoogleSansFlex-VF.ttf",
            "parts/grub/manifest.json",
            "parts/grub/entry.py",
            "parts/plymouth/material-boot-part.json",
        ):
            self.assertTrue((stage / f).is_file(), f)
        self.assertTrue(os.access(stage / "install.sh", os.X_OK))
        self.assertEqual(tar.name, f"material-boot-{material_boot.__version__}.tar.gz")
        self.assertFalse(list(stage.rglob("__pycache__")))

    def test_only_committed_files_of_a_part_are_taken(self):
        _, stage = self.build()
        self.assertFalse((stage / "parts/grub/untracked.txt").exists())

    def test_bundle_json_says_what_is_in_it(self):
        _, stage = self.build()
        b = json.loads((stage / "BUNDLE.json").read_text())
        self.assertEqual((b["core"], b["plugin_api"]), (material_boot.__version__, 2))
        self.assertEqual(sorted(b["parts"]), ["grub", "plymouth"])
        commit = subprocess.run(
            ["git", "-C", str(self.grub), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(b["parts"]["grub"]["commit"], commit)
        self.assertEqual(b["parts"]["grub"]["version"], "1.0.0")
        self.assertIn("local checkout", b["parts"]["grub"]["ref"])

    def test_the_checksums_cover_every_file_and_are_right(self):
        _, stage = self.build()
        lines = (stage / "SHA256SUMS").read_text().splitlines()
        listed = {ln.split("  ", 1)[1]: ln.split("  ", 1)[0] for ln in lines}
        files = {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
        self.assertEqual(set(listed), files)
        for name, digest in listed.items():
            self.assertEqual(hashlib.sha256((stage / name).read_bytes()).hexdigest(), digest, name)

    def test_the_parts_are_found_as_a_bundle(self):
        _, stage = self.build()
        found = plugins.discover_bundle(stage)
        self.assertEqual([p.name for p in found], ["grub", "plymouth"])
        self.assertTrue(all(p.problem is None for p in found), [p.problem for p in found])
        self.assertTrue(all(p.source == stage / "parts" / p.name for p in found))

    def test_the_same_inputs_give_the_same_bytes(self):
        a, _ = self.build("one")
        b, _ = self.build("two")
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(
            (self.d / "one" / (a.name + ".sha256")).read_text(), (self.d / "two" / (b.name + ".sha256")).read_text()
        )
        c, _ = self.build("three", epoch=1700000001)
        self.assertNotEqual(a.read_bytes(), c.read_bytes())  # the time is the only input that differs

    def test_the_archive_unpacks_to_one_directory_with_the_modes_kept(self):
        tar, _ = self.build()
        with tarfile.open(tar) as t:
            names = t.getnames()
            self.assertEqual(
                names, sorted(names), "the entries must be in sorted order, whatever order the filesystem lists them in"
            )
            self.assertTrue(all(n.split("/")[0] == f"material-boot-{material_boot.__version__}" for n in names))
            modes = {m.name.split("/", 1)[1]: m.mode for m in t.getmembers() if "/" in m.name}
            owners = {(m.uid, m.gid) for m in t.getmembers()}
        self.assertTrue(modes["install.sh"] & 0o111)
        self.assertTrue(modes["bin/material-boot"] & 0o111)
        self.assertEqual(owners, {(0, 0)})

    def test_the_sidecar_checksum_matches_the_archive(self):
        tar, _ = self.build()
        side = (tar.parent / (tar.name + ".sha256")).read_text().split()
        self.assertEqual(side, [hashlib.sha256(tar.read_bytes()).hexdigest(), tar.name])


class Refusals(Base):
    def test_a_release_is_never_built_from_a_branch(self):
        with self.assertRaises(SystemExit) as e:
            self.build(release=True)
        self.assertIn("not a tag", str(e.exception))
        self.assertIn("release/0.8.0", str(e.exception))

    def test_a_release_from_tags_is_fine(self):
        self.cfg.write_text(
            json.dumps(
                {
                    "format": 1,
                    "parts": {
                        "grub": {"repo": "x/grub", "ref": "v1.0.0"},
                        "plymouth": {"repo": "x/ply", "ref": "v1.0.0"},
                    },
                }
            )
        )
        tar, _ = self.build(release=True)
        self.assertTrue(tar.is_file())

    def test_a_part_without_a_manifest(self):
        shutil.rmtree(self.ply)
        self.local["plymouth"] = str(fake_part(self.d / "ply2", "plymouth", manifest=False))
        with self.assertRaises(SystemExit) as e:
            self.build()
        self.assertIn("has no material-boot-part.json", str(e.exception))

    def test_a_part_that_cannot_be_used(self):
        self.local["plymouth"] = str(fake_part(self.d / "ply3", "plymouth", core_api=1))
        with self.assertRaises(SystemExit) as e:
            self.build()
        self.assertIn("cannot be used", str(e.exception))
        self.assertIn("API 1", str(e.exception))

    def test_a_part_that_needs_a_newer_core(self):
        self.local["plymouth"] = str(fake_part(self.d / "ply4", "plymouth", core_min="99.0.0"))
        with self.assertRaises(SystemExit) as e:
            self.build()
        self.assertIn("update the core", str(e.exception))

    def test_a_name_that_does_not_match(self):
        self.local["plymouth"] = str(fake_part(self.d / "ply5", "splash"))
        with self.assertRaises(SystemExit) as e:
            self.build()
        self.assertIn("calls the part 'plymouth' but its manifest says 'splash'", str(e.exception))

    def test_an_unknown_format(self):
        self.cfg.write_text(json.dumps({"format": 9, "parts": {}}))
        with self.assertRaises(SystemExit) as e:
            self.build()
        self.assertIn("unknown format", str(e.exception))

    def test_the_real_bundle_json_is_valid_and_pins_branches_until_the_tags_exist(self):
        cfg = json.loads((ROOT / "bundle.json").read_text())
        self.assertEqual(cfg["format"], 1)
        self.assertEqual(sorted(cfg["parts"]), ["grub", "plymouth"])
        self.assertTrue(all("/" in p["repo"] and p["ref"] for p in cfg["parts"].values()))


class Installer(Base):
    """install.sh from the unpacked bundle, on a staged root."""

    def setUp(self):
        super().setUp()
        _, self.stage = self.build()
        self.root = self.d / "root"
        (self.root / "etc").mkdir(parents=True)

    def sh(self, *argv, env=None, path=None):
        e = dict(os.environ, **(env or {}))
        if path is not None:
            e["PATH"] = path
        return subprocess.run(
            [SH, str(self.stage / "install.sh"), *argv], capture_output=True, text=True, env=e, cwd=self.d
        )

    def test_a_dry_run_lists_every_part_and_changes_nothing(self):
        r = self.sh("--dry-run", "--root", str(self.root), "--with", "plymouth")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("would install plymouth", r.stdout)
        self.assertIn("build the shared data for the dark scheme", r.stdout)  # the core's plan
        self.assertIn("Dry run: nothing was changed.", r.stdout)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["etc"])

    def test_help_lists_the_parts(self):
        r = self.sh("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("parts: core, grub, plymouth", r.stdout)

    def test_a_changed_file_stops_the_install(self):
        (self.stage / "LICENSE").write_text("tampered\n")
        r = self.sh("--dry-run", "--root", str(self.root))
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match its SHA256SUMS", r.stderr)

    def test_no_verify_skips_the_check(self):
        (self.stage / "LICENSE").write_text("tampered\n")
        r = self.sh("--no-verify", "--dry-run", "--root", str(self.root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_python_is_a_clear_message(self):
        bin_ = self.d / "bin"
        bin_.mkdir()
        for tool in ("dirname", "id", "cat"):
            shutil.copy(shutil.which(tool), bin_ / tool)
        r = self.sh("--no-verify", "--dry-run", path=str(bin_))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Python 3.9 or newer is needed", r.stderr)

    @unittest.skipIf(coreinstall.missing_tools(), "needs Pillow and rsvg-convert (or ImageMagick)")
    def test_a_real_install_on_a_staged_root(self):
        r = self.sh("--yes", "--root", str(self.root), "--style", "list", "--with", "plymouth")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p = coreinstall.prefix(self.root)
        # the core: library, shim, the shared data built here
        self.assertTrue((p / "lib/material_boot/__init__.py").is_file())
        self.assertTrue((self.root / "usr/local/bin/material-boot").is_file())
        self.assertTrue((p / "data/palettes.json").is_file())
        # the parts: grub because it is the default? no: --with plymouth chose only that one, so grub stays out
        self.assertTrue((self.root / "var/lib/fake-plymouth/installed").is_file())
        self.assertFalse((self.root / "var/lib/fake-grub").exists())
        got = json.loads((self.root / "var/lib/fake-plymouth/installed").read_text())
        self.assertEqual((got["style"], got["how"]), ("list", "source"))
        self.assertEqual(Path(got["source"]), self.stage)  # the part was run from the bundle
        st = state.read(str(self.root))
        self.assertEqual(st["parts"], {"core": material_boot.__version__, "plymouth": "1.0.0"})
        self.assertIn("STYLE=list", (self.root / "etc/material-grub.conf").read_text())

    @unittest.skipIf(coreinstall.missing_tools(), "needs Pillow and rsvg-convert (or ImageMagick)")
    def test_a_fresh_install_with_no_choice_is_the_core_and_the_defaults(self):
        r = self.sh("--yes", "--root", str(self.root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            sorted(state.read(str(self.root))["parts"]), ["core", "grub"]
        )  # grub is install.default, plymouth is not
        self.assertFalse((self.root / "var/lib/fake-plymouth").exists())

    @unittest.skipIf(coreinstall.missing_tools(), "needs Pillow and rsvg-convert (or ImageMagick)")
    def test_a_second_run_is_an_update_and_uninstall_takes_a_part_out(self):
        self.sh("--yes", "--root", str(self.root), "--with", "grub", "--with", "plymouth")
        r = self.sh("--yes", "--root", str(self.root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Found", r.stdout)  # the existing install is announced
        r = self.sh("--yes", "--root", str(self.root), "--uninstall", "--only", "plymouth")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(state.read(str(self.root))["parts"]), ["core", "grub"])


if __name__ == "__main__":
    unittest.main()
