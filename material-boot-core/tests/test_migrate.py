"""material_boot.migrate: ordered, idempotent migration steps with a backup and a rollback. stdlib only."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from material_boot import migrate  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "etc").mkdir()
        self.conf = self.root / "etc/material-grub.conf"
        self.backup = self.root / "backup"

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self):
        return migrate.context(root=str(self.root), backup=self.backup)


class Planning(unittest.TestCase):
    def test_steps_for_a_version_range(self):
        ids = lambda a, b: [s.id for s in migrate.steps_for(a, b)]  # noqa: E731
        self.assertEqual(ids("0.7.1", "1.0.0"), ["conf-samples"])
        self.assertEqual(
            ids(None, "1.0.0"), ["conf-samples"]
        )  # unknown version: every step up to the target is checked
        self.assertEqual(ids("1.0.0", "1.0.0"), [])  # already there
        self.assertEqual(ids("1.0.0", "1.1.0"), [])
        self.assertEqual(ids("0.7.1", "0.9.0"), [])  # the step belongs to 1.0.0

    def test_backup_dir_names_the_upgrade(self):
        p = migrate.backup_dir(str(Path("/r")), "0.7.1", "1.0.0", now="T")
        self.assertEqual(p, Path("/r/var/backups/material-grub/upgrade-0.7.1-to-1.0.0-T"))
        self.assertIn("unknown", str(migrate.backup_dir("", None, "1.0.0", now="T")))


class ConfSamples(Base):
    def test_adds_commented_samples_and_never_touches_the_rest(self):
        self.conf.write_text("# mine\nSTYLE=list\nPLYMOUTH_BAR=progress\n")
        self.conf.chmod(0o600)
        step = migrate.ConfSamples()
        self.assertEqual(len(step.plan(self.ctx())), 2)  # PLYMOUTH and PLYMOUTH_MOTION; the bar is set already
        step.apply(self.ctx())
        text = self.conf.read_text()
        self.assertTrue(text.startswith("# mine\nSTYLE=list\nPLYMOUTH_BAR=progress\n"))
        self.assertIn("#PLYMOUTH=on", text)
        self.assertIn("#PLYMOUTH_MOTION=full", text)
        self.assertNotIn("#PLYMOUTH_BAR", text)
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o600)

    def test_idempotent(self):
        self.conf.write_text("STYLE=rail\n")
        step = migrate.ConfSamples()
        step.apply(self.ctx())
        once = self.conf.read_text()
        self.assertEqual(step.plan(self.ctx()), [])
        step.apply(self.ctx())
        self.assertEqual(self.conf.read_text(), once)

    def test_no_conf_file_means_nothing_to_do(self):
        self.assertEqual(migrate.ConfSamples().plan(self.ctx()), [])


class Boom(migrate.Step):
    id, since, title = "boom", "1.0.0", "damage the file, then fail"

    def __init__(self, path):
        self.path = path

    def touches(self, ctx):
        return [self.path]

    def plan(self, ctx):
        return ["break it"]

    def apply(self, ctx):
        Path(self.path).write_text("DAMAGED\n")
        raise RuntimeError("half way")


class Running(Base):
    def test_a_good_run_backs_up_what_it_touches(self):
        self.conf.write_text("STYLE=rail\n")
        res = migrate.run(self.ctx(), [migrate.ConfSamples()])
        self.assertEqual([(r[0].id, r[1]) for r in res], [("conf-samples", "done")])
        self.assertEqual(
            (self.backup / "etc/material-grub.conf").read_text(), "STYLE=rail\n"
        )  # the original, before the step

    def test_a_step_with_nothing_to_do_is_skipped(self):
        res = migrate.run(self.ctx(), [migrate.ConfSamples()])
        self.assertEqual(res[0][1], "skipped")

    def test_a_failing_step_restores_everything_and_stops(self):
        self.conf.write_text("STYLE=rail\n")
        after = migrate.ConfSamples()
        res = migrate.run(self.ctx(), [migrate.ConfSamples(), Boom(self.conf), after])
        self.assertEqual([r[1] for r in res], ["done", "failed"])  # the step after the failure was not run
        self.assertEqual(self.conf.read_text(), "STYLE=rail\n")  # the earlier step's change was undone too
        self.assertIn("RuntimeError: half way", res[1][2])
        self.assertIn("put back", res[1][2])

    def test_a_file_the_step_created_is_removed_on_failure(self):
        new = self.root / "etc/created.conf"
        res = migrate.run(self.ctx(), [Boom(new)])
        self.assertEqual(res[0][1], "failed")
        self.assertFalse(new.exists())

    def test_progress_is_reported(self):
        self.conf.write_text("STYLE=rail\n")
        seen = []
        migrate.run(self.ctx(), [migrate.ConfSamples()], emit=seen.append)
        self.assertEqual(seen, [migrate.ConfSamples.title])


if __name__ == "__main__":
    os.environ.setdefault("TZ", "UTC")
    unittest.main()
