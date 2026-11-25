"""material_boot.state: the state record of an install, the lenient version compare, and who owns a file. stdlib only."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from material_boot import state  # noqa: E402


class Versions(unittest.TestCase):
    def test_lenient(self):
        self.assertEqual(state.version_tuple("1.0.0"), (1, 0, 0))
        self.assertEqual(state.version_tuple("0.8.0-dev"), (0, 8, 0))
        for junk in (None, "", "?", "git-abc1234"):
            self.assertEqual(state.version_tuple(junk), (0,), junk)  # never raises, compares as the lowest version
        self.assertLess(state.version_tuple("0.7.1"), state.version_tuple("1.0.0"))
        self.assertLess(state.version_tuple("1.0.0"), state.version_tuple("1.0.1"))


class Record(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_where_it_lives(self):
        self.assertEqual(state.state_path(self.root), Path(self.root) / "var/lib/material-grub/state.json")
        old = os.environ.get("MATERIAL_STATE_DIR")
        try:
            os.environ["MATERIAL_STATE_DIR"] = self.root + "/elsewhere"
            self.assertEqual(state.state_path(""), Path(self.root) / "elsewhere/state.json")
        finally:
            if old is None:
                os.environ.pop("MATERIAL_STATE_DIR", None)
            else:
                os.environ["MATERIAL_STATE_DIR"] = old

    def test_first_record(self):
        d = state.record(self.root, "1.0.0", "source", "normal", parts={"core": "1.0.0"}, now="T1")
        self.assertEqual(state.read(self.root), d)
        self.assertEqual(
            (d["state"], d["version"], d["how"], d["layout"], d["installed_at"]), (1, "1.0.0", "source", "normal", "T1")
        )
        self.assertEqual(d["parts"], {"core": "1.0.0"})
        self.assertEqual(d["history"], [{"from": None, "to": "1.0.0", "at": "T1"}])

    def test_an_update_keeps_what_other_parts_wrote(self):
        state.record(self.root, "1.0.0", "source", "normal", parts={"core": "1.0.0"}, now="T1")
        p = state.state_path(self.root)
        d = json.loads(p.read_text())
        d["parts"]["plymouth"] = {"version": "1.0.0", "changes": ["cmdline"]}  # a part records its own changes here
        d["extra"] = "kept"
        state.write(self.root, d)
        d = state.record(self.root, "1.1.0", "package:rpm", "normal", parts={"core": "1.1.0"}, now="T2")
        self.assertEqual(d["parts"]["plymouth"]["changes"], ["cmdline"])
        self.assertEqual(d["parts"]["core"], "1.1.0")
        self.assertEqual(d["extra"], "kept")
        self.assertEqual(d["history"][-1], {"from": "1.0.0", "to": "1.1.0", "at": "T2"})

    def test_the_same_version_adds_no_history_and_the_history_is_capped(self):
        state.record(self.root, "1.0.0", "source", "normal", now="T1")
        d = state.record(self.root, "1.0.0", "source", "normal", now="T2")
        self.assertEqual(len(d["history"]), 1)
        for i in range(30):
            d = state.record(self.root, f"2.0.{i}", "source", "normal", now=f"T{i}")
        self.assertLessEqual(len(d["history"]), 20)
        self.assertEqual(d["history"][-1]["to"], "2.0.29")

    def test_a_record_that_cannot_be_read_is_none_never_an_error(self):
        self.assertIsNone(state.read(self.root))  # missing
        p = state.state_path(self.root)
        p.parent.mkdir(parents=True)
        for text in ("{nope", "[1]", json.dumps({"state": 99, "version": "1"})):
            p.write_text(text)
            self.assertIsNone(state.read(self.root), text)

    def test_write_is_atomic_and_readable_by_everyone(self):
        state.write(self.root, {"state": 1, "version": "1.0.0"})
        p = state.state_path(self.root)
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o644)
        self.assertEqual([f.name for f in p.parent.iterdir()], ["state.json"])  # no temp file left behind


class Owner(unittest.TestCase):
    def fake(self, tools):
        """A directory with fake package managers: {name: exit status}. PATH is set to it for the call."""
        d = Path(self.tmp.name)
        for name, rc in tools.items():
            f = d / name
            f.write_text(f"#!/bin/sh\nexit {rc}\n")
            f.chmod(0o755)
        return str(d)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ["PATH"]

    def tearDown(self):
        os.environ["PATH"] = self.old
        self.tmp.cleanup()

    def test_no_package_manager_means_unknown(self):
        os.environ["PATH"] = self.fake({})
        self.assertEqual(state.owner_of("/usr/share/x"), "unknown")

    def test_a_package_that_owns_it(self):
        os.environ["PATH"] = self.fake({"rpm": 0})
        self.assertEqual(state.owner_of("/usr/share/x"), "package:rpm")
        os.environ["PATH"] = self.fake({"dpkg": 0, "rpm": 1})
        self.assertEqual(state.owner_of("/usr/share/x"), "package:deb")

    def test_tools_exist_and_nobody_owns_it_means_source(self):
        os.environ["PATH"] = self.fake({"rpm": 1, "dpkg": 1})
        self.assertEqual(state.owner_of("/usr/local/x"), "source")


if __name__ == "__main__":
    unittest.main()
