"""overrides.json: schema, lenient loading, atomic saving, matching. stdlib only. usage: python3 -m unittest tests.test_overrides"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from material_boot import overrides as ov  # noqa: E402


class Validate(unittest.TestCase):
    def test_empty_object_is_the_defaults(self):
        c, e, w = ov.validate({})
        self.assertEqual((e, w), ([], []))
        self.assertEqual(c["seed"], {"mode": "multi", "color": "#0B3D2E"})

    def test_full_example(self):
        c, e, w = ov.validate(
            {
                "version": 1,
                "seed": {"mode": "single", "color": "#e95420"},
                "groups": ["windows", "linux"],
                "order": [{"key": "windows11"}, {"class": "mg_1a2b3c4d5e"}],
                "entries": [
                    {
                        "match": {"key": "fedora"},
                        "name": " Mine ",
                        "color": "#2e7d32",
                        "icon": "file:logo.png",
                        "hidden": False,
                    }
                ],
            }
        )
        self.assertEqual((e, w), ([], []))
        self.assertEqual(c["seed"]["color"], "#E95420")
        self.assertEqual(
            c["entries"][0],
            {"match": {"key": "fedora"}, "name": "Mine", "color": "#2E7D32", "icon": "file:logo.png", "hidden": False},
        )

    def test_bad_values_are_errors(self):
        bad = [
            {"version": 2},
            {"seed": {"mode": "rainbow"}},
            {"seed": {"color": "red"}},
            {"groups": ["linux", "linux"]},
            {"groups": ["bsd"]},
            {"order": [{"key": "a", "class": "b"}]},
            {"order": [{"nope": "a"}]},
            {"entries": [{"match": {"key": "x"}, "color": "#12345"}]},
            {"entries": [{"match": {"key": "x"}, "name": ""}]},
            {"entries": [{"match": {"key": "x"}, "name": "a\nb"}]},
            {"entries": [{"match": {"key": "x"}, "icon": "file:../etc/passwd"}]},
            {"entries": [{"match": {"key": "x"}, "icon": "file:a.exe"}]},
            {"entries": [{"match": {"key": "x"}, "icon": "Has Space"}]},
            {"entries": [{"match": {"key": "x"}, "hidden": "yes"}]},
            {"entries": [{"name": "no match"}]},
            {"entries": "nope"},
            [],
        ]
        for b in bad:
            self.assertTrue(ov.validate(b)[1], b)

    def test_unknown_keys_only_warn(self):
        c, e, w = ov.validate({"future": 1, "entries": [{"match": {"key": "x"}, "sparkle": True}]})
        self.assertEqual(e, [])
        self.assertEqual(len(w), 2)


class Files(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.p = Path(self.d.name) / "etc/overrides.json"

    def tearDown(self):
        self.d.cleanup()

    def test_missing_file_is_defaults(self):
        self.assertEqual(ov.load(self.p), (ov.DEFAULTS, []))

    def test_broken_file_never_raises(self):
        self.p.parent.mkdir()
        self.p.write_text("{not json")
        c, probs = ov.load(self.p)
        self.assertEqual(c, ov.DEFAULTS)
        self.assertTrue(probs)
        self.p.write_text(json.dumps({"seed": {"mode": "x"}}))
        c, probs = ov.load(self.p)
        self.assertEqual(c, ov.DEFAULTS)
        self.assertIn("seed.mode", probs[0])

    def test_save_roundtrip_and_refusal(self):
        ov.save(
            {
                "seed": {"mode": "single", "color": "#112233"},
                "entries": [{"match": {"title": "windows"}, "hidden": True}],
            },
            self.p,
        )
        c, probs = ov.load(self.p)
        self.assertEqual((probs, c["seed"]["mode"], c["entries"][0]["hidden"]), ([], "single", True))
        before = self.p.read_text()
        with self.assertRaises(ValueError):
            ov.save({"seed": {"mode": "no"}}, self.p)
        self.assertEqual(self.p.read_text(), before)
        self.assertEqual([f.name for f in self.p.parent.iterdir()], ["overrides.json"])
        self.assertEqual(self.p.stat().st_mode & 0o777, 0o644)


class Matching(unittest.TestCase):
    E = [
        {"key": "fedora", "class": "mg_a", "title": "Fedora Linux (6.1)"},
        {"key": "windows11", "class": "mg_b", "title": "Windows Boot Manager"},
        {"key": "tux", "class": "mg_c", "title": "Something else"},
    ]

    def test_rule_for_first_match_wins(self):
        o, _, _ = ov.validate(
            {
                "entries": [
                    {"match": {"title": "windows"}, "name": "Win"},
                    {"match": {"key": "windows11"}, "name": "Other"},
                ]
            }
        )
        self.assertEqual(ov.rule_for(o, self.E[1])["name"], "Win")
        self.assertEqual(ov.rule_for(o, self.E[0]), {})

    def test_sort_order(self):
        o, _, _ = ov.validate({"order": [{"key": "windows11"}, {"class": "mg_a"}]})
        self.assertEqual([e["class"] for e in ov.sort_order(o, self.E)], ["mg_b", "mg_a", "mg_c"])
        o, _, _ = ov.validate({})
        self.assertEqual(ov.sort_order(o, self.E), self.E)


if __name__ == "__main__":
    unittest.main()
