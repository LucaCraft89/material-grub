"""The package definitions (rpm, deb, Arch) agree with each other and with the repository: one version, one layout, the same scriptlets. stdlib only.
(That they BUILD and INSTALL is checked in distro containers: tests/containers/, the `package` job of the CI.)"""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = (ROOT / "VERSION").read_text().strip()
SPEC = (ROOT / "packaging/rpm/material-boot-core.spec").read_text()
PKGBUILD = (ROOT / "packaging/arch/PKGBUILD").read_text()
ARCH_INSTALL = (ROOT / "packaging/arch/material-boot-core.install").read_text()
DEB = ROOT / "packaging/debian/debian"
POST = "/usr/bin/material-boot core install --from-package --only core --yes"
REMOVE = "/usr/bin/material-boot core install --from-package --uninstall --only core --yes"


class Versions(unittest.TestCase):
    def test_one_version_everywhere(self):
        self.assertEqual(re.search(r"^Version:\s+(\S+)", SPEC, re.M).group(1), VERSION)
        self.assertEqual(re.search(r"^pkgver=(\S+)", PKGBUILD, re.M).group(1), VERSION)
        self.assertEqual(re.match(r"material-boot-core \(([^)]+)\)", (DEB / "changelog").read_text()).group(1), VERSION)
        self.assertIn(f"- {VERSION}-1", SPEC.split("%changelog")[1])

    def test_the_names_agree(self):
        self.assertIn("Name:           material-boot-core", SPEC)
        self.assertIn("pkgname=material-boot-core", PKGBUILD)
        self.assertIn("Source: material-boot-core", (DEB / "control").read_text())
        self.assertIn("Package: material-boot-core", (DEB / "control").read_text())


class Scriptlets(unittest.TestCase):
    def test_every_format_builds_the_data_after_an_install_and_an_upgrade(self):
        self.assertRegex(SPEC, rf"%posttrans\n{re.escape(POST)} \|\| :")
        self.assertIn(f"{POST} || true", ARCH_INSTALL)
        self.assertIn("post_install() { _run; }", ARCH_INSTALL)
        self.assertIn("post_upgrade() { _run; }", ARCH_INSTALL)
        postinst = (DEB / "postinst").read_text()
        self.assertIn(f"configure) {POST} || true", postinst)

    def test_every_format_cleans_up_what_it_generated_on_removal_only(self):
        self.assertIn(f"if [ $1 -eq 0 ]; then {REMOVE} || :; fi", SPEC)  # an upgrade is not a removal
        self.assertIn(f"pre_remove() {{ {REMOVE} || true; }}", ARCH_INSTALL)
        self.assertIn(f"remove) {REMOVE} || true", (DEB / "prerm").read_text())

    def test_a_failing_scriptlet_never_fails_the_transaction(self):
        for text in (SPEC, ARCH_INSTALL, (DEB / "postinst").read_text(), (DEB / "prerm").read_text()):
            for line in text.splitlines():
                if "material-boot core install" in line and not line.lstrip().startswith("#"):
                    self.assertTrue("|| :" in line or "|| true" in line, line)


class Requirements(unittest.TestCase):
    def test_python_pillow_and_rsvg_everywhere(self):
        control = (DEB / "control").read_text()
        for need in ("python3 (>= 3.9)", "python3-pil", "librsvg2-bin"):
            self.assertIn(need, control)
        for need in ("python3", "python3-pillow", "librsvg2-tools"):
            self.assertRegex(
                SPEC,
                rf"(?m)^Requires:\s+{need}$",
            )
        for need in ("python>=3.9", "python-pillow", "librsvg"):
            self.assertIn(f"'{need}'", PKGBUILD)


class Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest = Path(cls.tmp.name)
        subprocess.run(
            ["sh", str(ROOT / "packaging/common/install-tree.sh"), str(ROOT), str(cls.dest)],
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_files(self):
        p = self.dest / "usr/share/material-boot"
        for f in (
            "lib/material_boot/__init__.py",
            "lib/material_boot/VERSION",
            "scripts/build_data.py",
            "assets/fonts/GoogleSansFlex-VF.ttf",
        ):
            self.assertTrue((p / f).is_file(), f)
        self.assertEqual((p / "lib/material_boot/VERSION").read_text().strip(), VERSION)
        self.assertTrue((p / "plugins.d").is_dir())
        self.assertEqual(list((p / "plugins.d").iterdir()), [])  # the package owns the directory; the parts fill it

    def test_the_command_is_the_repositorys_shim_and_executable(self):
        f = self.dest / "usr/bin/material-boot"
        self.assertTrue(os.access(f, os.X_OK))
        self.assertEqual(f.read_text(), (ROOT / "bin/material-boot").read_text())

    def test_no_bytecode_and_no_generated_data_in_the_package(self):
        self.assertFalse(list(self.dest.rglob("__pycache__")))
        self.assertFalse((self.dest / "usr/share/material-boot/data").exists())  # built on the machine, for the scheme

    def test_everything_the_spec_lists_exists_and_nothing_else_is_shipped(self):
        listed = re.findall(r"^(%dir )?%\{_(bindir|datadir)\}/?(\S*)$", SPEC, re.M)
        roots = {"bindir": "usr/bin", "datadir": "usr/share"}
        paths = [self.dest / roots[kind] / rest for _dir, kind, rest in listed]
        self.assertTrue(paths)
        for p in paths:
            self.assertTrue(p.exists(), p)
        top = {p.relative_to(self.dest).as_posix() for p in self.dest.glob("usr/*/*")}
        covered = {p.relative_to(self.dest).as_posix() for p in paths}
        for t in top:
            self.assertTrue(
                any(t == c or t.startswith(c + "/") or c.startswith(t + "/") for c in covered),
                f"{t} would be shipped by dpkg and pacman but is not in the spec",
            )

    def test_the_debian_rules_use_the_same_script(self):
        self.assertIn("packaging/common/install-tree.sh . debian/material-boot-core", (DEB / "rules").read_text())
        self.assertIn('packaging/common/install-tree.sh . "$pkgdir"', PKGBUILD)
        self.assertIn("packaging/common/install-tree.sh . %{buildroot}", SPEC)


if __name__ == "__main__":
    unittest.main()
