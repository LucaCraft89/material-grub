"""material_boot.titles: which distro a title is, and what kind of entry it is. stdlib only. (Moved with the code from material-grub's tests/test_mgrub.py.)"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from material_boot import catalog as C  # noqa: E402

# the names in the tests below are kept as they were in material-grub
from material_boot import titles as mgrub  # noqa: E402


class Parse(unittest.TestCase):
    def test_bls(self):
        d = mgrub.parse_title("Fedora Linux (7.3.3-200.fc44.x86_64) 44 (Workstation Edition)")
        self.assertEqual(
            (d["os"], d["kver"], d["osver"], d["edition"]),
            ("Fedora Linux", "7.3.3-200.fc44.x86_64", "44", "Workstation Edition"),
        )

    def test_ostree(self):
        d = mgrub.parse_title("Fedora Linux 44.20260301.0 (Silverblue) (ostree:0)")
        self.assertEqual(
            (d["os"], d["osver"], d["edition"], d["kver"]), ("Fedora Linux", "44.20260301.0", "Silverblue", "ostree:0")
        )

    def test_classic(self):
        d = mgrub.parse_title("Ubuntu, with Linux 6.8.0-45-generic (recovery mode)")
        self.assertEqual((d["os"], d["kver"], d["edition"]), ("Ubuntu", "6.8.0-45-generic", "recovery mode"))

    def test_osprober(self):
        d = mgrub.parse_title("Ubuntu 24.04.1 LTS (on /dev/sda5)")
        self.assertEqual((d["os"], d["osver"], d["where"]), ("Ubuntu", "24.04.1 LTS", "/dev/sda5"))


class Kind(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(mgrub.kind_of("Advanced options for Debian", "debian", True), "advanced")
        self.assertEqual(mgrub.kind_of("Fedora Linux (0-rescue-abc) 44", "fedora"), "rescue")
        self.assertEqual(mgrub.kind_of("Windows Boot Manager", "windows11"), "plain")
        self.assertEqual(mgrub.kind_of("Arch Linux", "arch"), "kernel")


def _rules():  # generated from the catalog exactly as the package build does it
    rules = []
    for k, title, _, _, _, _, al in C.D:
        for p in {title, k, *[a for a in al if a not in C.GENERIC]}:
            toks = re.findall(r"[a-z0-9]+", p.lower())
            if toks:
                rules.append({"key": k, "tokens": toks})
    return sorted(rules, key=lambda r: -len("".join(r["tokens"])))


class Match(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = _rules()

    def test_known(self):
        for title, key in [
            ("CachyOS Linux", "cachyos"),
            ("Linux Mint 22", "linuxmint"),
            ("Pop!_OS 24.04", "pop"),
            ("openSUSE Tumbleweed", "opensuse"),
            ("Fedora Linux (6.8) 44", "fedora"),
            ("KALI GNU/LINUX", "kali"),
            ("EndeavourOS", "endeavouros"),
            ("Kubuntu 24.04", "kubuntu"),
        ]:
            self.assertEqual(mgrub.key_for(title, self.rules), key, title)

    def test_unknown_and_windows(self):
        self.assertIsNone(mgrub.key_for("Some Unknown OS", self.rules))
        self.assertIsNone(
            mgrub.key_for("Windows Boot Manager", self.rules)
        )  # Windows is resolved separately (10 vs 11)


class Uid(unittest.TestCase):
    def test_distinct_classes_per_drive(self):
        self.assertNotEqual(mgrub.uid("top", "Ubuntu (on /dev/sda5)"), mgrub.uid("top", "Ubuntu (on /dev/sdb5)"))
        self.assertRegex(mgrub.uid("top", "x"), r"^mg_[0-9a-f]{10}$")


if __name__ == "__main__":
    unittest.main()
