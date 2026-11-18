"""Windows 10/11 detection: the partition is mounted read-only, bootmgfw.efi is read, and the answer is recomputed every time grub.cfg is
regenerated, so an upgrade from 10 to 11 shows the new icon after the next regeneration. No root: `mount` is replaced by a fake.
usage: python3 tests/test_windows.py"""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import cmd_classes  # noqa: E402


def fake_run_factory(build):
    def fake_run(cmd, *a, **kw):
        if cmd[0] == "mount":
            assert "ro" in cmd, "the Windows partition must be mounted read-only"
            mp = Path(cmd[-1])
            efi = mp / "EFI/Microsoft/Boot"
            efi.mkdir(parents=True)
            (efi / "bootmgfw.efi").write_bytes(f"10.0.{build}.1".encode("utf-16le"))
        return mock.Mock(returncode=0)

    return fake_run


class Windows(unittest.TestCase):
    def key(self, build, device="/dev/nvme0n1p1"):
        with mock.patch.object(cmd_classes.subprocess, "run", fake_run_factory(build)):
            return cmd_classes.windows_key(device)

    def test_builds(self):
        self.assertEqual(self.key(19045), "windows10")
        self.assertEqual(self.key(22000), "windows11")
        self.assertEqual(self.key(26100), "windows11")

    def test_upgrade_is_seen_on_the_next_regeneration(self):
        before, after = self.key(19045), self.key(22631)  # nothing is cached between runs
        self.assertEqual((before, after), ("windows10", "windows11"))

    def test_unreadable_partition_defaults_to_11(self):
        with mock.patch.object(cmd_classes.subprocess, "run", side_effect=OSError("no mount")):
            self.assertEqual(cmd_classes.windows_key("/dev/sdz9"), "windows11")


if __name__ == "__main__":
    unittest.main()
