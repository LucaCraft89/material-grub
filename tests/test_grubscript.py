"""Tests for the GRUB script scanner and the annotation built on it: hostile titles, nesting, multi-line headers, and golden files
from real grub-mkconfig output (Debian, Ubuntu, Arch, Fedora/BLS). Needs a built package (dist/material-grub) for the tool runs.
usage: python3 tests/test_grubscript.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
BIN = ROOT / "install/bin"
GOLD = ROOT / "tests/golden"
sys.path.insert(0, str(BIN))
import grubscript  # noqa: E402


def titles(text):
    return [(e.word, e.title, e.level) for e in grubscript.scan(text).entries]


class Scanner(unittest.TestCase):
    def test_plain(self):
        t = "menuentry 'Fedora' --class fedora {\n\tlinux /vmlinuz\n}\n"
        e = grubscript.scan(t).entries
        self.assertEqual([(x.word, x.title, x.classes) for x in e], [("menuentry", "Fedora", ["fedora"])])
        self.assertEqual(t[e[0].title_end - 1], "'")
        self.assertEqual(t[e[0].open_brace], "{")
        self.assertEqual(t[e[0].close_brace], "}")

    def test_brace_and_quotes_inside_titles(self):
        for title in ("a } b", "a { b", "}", "{", "it's", 'say "hi"', "back\\slash", "x; y | z & w", "# not a comment"):
            for q in ("'", '"'):
                if q == "'" and "'" in title:
                    quoted = "'" + title.replace("'", "'\\''") + "'"
                elif q == '"':
                    quoted = '"' + title.replace("\\", "\\\\").replace('"', '\\"') + '"'
                else:
                    quoted = "'" + title + "'"
                t = f"menuentry {quoted} {{\n\techo x\n}}\nmenuentry 'next' {{\n}}\n"
                got = titles(t)
                self.assertEqual([g[1] for g in got], [title, "next"], quoted)

    def test_escaped_quote_in_double_quotes(self):
        self.assertEqual(titles('menuentry "A \\"B\\" C" {\n}\n')[0][1], 'A "B" C')

    def test_unicode_and_long(self):
        long = "Ubuntu " + "x" * 5000
        got = titles(f"menuentry 'Fedora Linux (6.1) — Ünï 日本語 🐧' {{\n}}\nmenuentry '{long}' {{\n}}\n")
        self.assertEqual([g[1] for g in got], ["Fedora Linux (6.1) — Ünï 日本語 🐧", long])

    def test_multiline_header(self):
        t = "menuentry 'A' \\\n  --class a \\\n  --id x {\n\techo\n}\n"
        e = grubscript.scan(t).entries
        self.assertEqual(len(e), 1)
        self.assertEqual((e[0].title, e[0].classes), ("A", ["a"]))

    def test_title_spanning_lines(self):
        t = "menuentry 'two\nlines' {\n\techo\n}\nmenuentry 'after' {\n}\n"
        self.assertEqual([g[1] for g in titles(t)], ["two\nlines", "after"])

    def test_nested_submenus(self):
        t = (
            "submenu 'Advanced' {\n"
            "\tmenuentry 'k1' {\n\t\techo '}'\n\t}\n"
            "\tsubmenu 'Deeper' {\n\t\tmenuentry 'k2' {\n\t\t}\n\t}\n"
            "\tmenuentry 'k3' {\n\t}\n"
            "}\n"
            "menuentry 'top' {\n}\n"
        )
        got = titles(t)
        self.assertEqual(
            got,
            [
                ("submenu", "Advanced", "top"),
                ("menuentry", "k1", "adv"),
                ("submenu", "Deeper", "adv"),
                ("menuentry", "k2", "adv"),
                ("menuentry", "k3", "adv"),
                ("menuentry", "top", "top"),
            ],
        )
        e = grubscript.scan(t).entries
        self.assertEqual(e[3].parent.title, "Deeper")
        self.assertEqual(e[1].parent.title, "Advanced")
        self.assertIsNone(e[0].parent)

    def test_comments_and_functions_are_not_entries(self):
        t = "# menuentry 'no' {\nfunction f {\n  echo menuentry\n}\nmenuentry_id_option=--id\nmenuentry 'yes' {\n}\n"
        self.assertEqual([g[1] for g in titles(t)], ["yes"])

    def test_entry_inside_if(self):
        t = "if [ x ]; then\n  menuentry 'in if' $opt 'id' {\n  }\nfi\n"
        self.assertEqual([g[1] for g in titles(t)], ["in if"])

    def test_variable_titles_and_extra_args(self):
        e = grubscript.scan("menuentry \"$title\" --class a --class b $opt 'id-1' {\n}\n").entries[0]
        self.assertEqual(e.classes, ["a", "b"])

    def test_not_a_block(self):
        self.assertEqual(titles("menuentry 'x'\n"), [])  # no `{`: GRUB rejects it, so it is no entry
        self.assertEqual(titles("echo menuentry 'x' {\n}\n"), [])  # not at command position

    def test_unclosed_block_does_not_crash(self):
        e = grubscript.scan("menuentry 'x' {\n echo\n").entries
        self.assertEqual(len(e), 1)
        self.assertIsNone(e[0].close_brace)

    def test_command_lines(self):
        t = "menuentry 'a\nblscfg\nb' {\n}\nblscfg\n# note\n"
        sc = grubscript.scan(t)
        self.assertIsNone(sc.command_at_line(1))  # inside the quoted title
        self.assertEqual(sc.command_at_line(4).value, "blscfg")
        self.assertEqual(sc.comment_at_line(5).text, "# note")

    def test_split_lines(self):
        self.assertEqual(grubscript.split_lines("a\nb"), ["a\n", "b"])
        self.assertEqual(grubscript.split_lines("a\n"), ["a\n"])
        self.assertEqual(grubscript.split_lines("a b\n"), ["a b\n"])  # only a line feed ends a line


@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class Tool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_classes(self, text, bls=None):
        cfg = self.d / "grub.cfg"
        cfg.write_text(text)
        ents = self.d / "entries"
        ents.mkdir(exist_ok=True)
        for f in bls or []:
            (ents / f.name).write_bytes(f.read_bytes())
        st = self.d / "state"
        st.mkdir(exist_ok=True)
        r = subprocess.run(
            [sys.executable, str(BIN / "material-grub-classes"), str(cfg), "--pkg", str(PKG), "--bls", str(ents)]
            + ["--loader", str(self.d), "--mirrors", str(self.d / "m"), "--mirrorbase", "/m", "--fallback-all"]
            + ["--state", str(st / "entries.json")],
            capture_output=True,
            text=True,
            env=dict(
                os.environ, OS_RELEASE=str(GOLD / "os-release")
            ),  # the name in the Advanced submenu must not depend on the host
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return cfg.read_text(), json.loads((st / "entries.json").read_text())

    def test_golden_files(self):
        for name in ("debian", "ubuntu", "arch", "fedora"):
            with self.subTest(name):
                bls = sorted((GOLD / "bls").glob("*.conf")) if name == "fedora" else []
                out, entries = self.run_classes((GOLD / f"{name}.cfg").read_text(), bls)
                self.assertEqual(out, (GOLD / f"{name}.annotated.cfg").read_text())
                self.assertGreaterEqual(len(entries), 3)

    def test_golden_distro_keys(self):
        out, entries = self.run_classes((GOLD / "arch.cfg").read_text())
        self.assertEqual({e["key"] for e in entries if e["kind"] in ("kernel", "rescue")}, {"arch"})
        self.assertEqual([e["level"] for e in entries][:2], ["top", "top"])
        self.assertIn("adv", {e["level"] for e in entries})

    def test_hostile_titles_each_get_one_class(self):
        names = [
            "Fedora } Linux",
            "Weird { one",
            "It's quoted",
            'Say "hi"',
            "Ünïcode 日本語 🐧",
            "L" + "o" * 3000 + "ng",
        ]

        def q(t):
            return "'" + t.replace("'", "'\\''") + "'"

        text = "".join(f"menuentry {q(n)} --class gnu-linux {{\n\techo '}}'\n}}\n" for n in names)
        text += "submenu 'Advanced options for X' {\n\tmenuentry 'inner } one' {\n\t}\n}\n"
        out, entries = self.run_classes(text)
        self.assertEqual(len(entries), len(names) + 2)
        self.assertEqual(out.count("--class mg_"), len(names) + 2)
        self.assertEqual([e["level"] for e in entries][-2:], ["adv", "adv"] if False else ["top", "adv"])
        self.assertEqual(entries[-1]["parent"], entries[-2]["class"])
        # every original line is still there, only the class options were added
        stripped = out.split("\n", 1)[1]
        import re

        self.assertEqual(
            re.sub(r" --class mg_[0-9a-f]{10}( --class \w+)?", "", stripped).replace(" --class gnu-linux", ""),
            text.replace(" --class gnu-linux", ""),
        )

    def test_multiline_header_and_title(self):
        text = "menuentry 'Multi' \\\n   --class debian \\\n   --id x {\n\techo\n}\nmenuentry 'a\nblscfg\nb' {\n}\n"
        out, entries = self.run_classes(text)
        self.assertEqual(len(entries), 2)
        self.assertIn("'Multi' --class mg_", out)
        self.assertNotIn("material-top", out)  # the `blscfg` line inside the title is not a command

    def test_idempotent(self):
        out1, _ = self.run_classes((GOLD / "ubuntu.cfg").read_text())
        cfg = self.d / "grub.cfg"
        before = cfg.read_text()
        subprocess.run(
            [
                sys.executable,
                str(BIN / "material-grub-classes"),
                str(cfg),
                "--pkg",
                str(PKG),
                "--state",
                str(self.d / "state/entries.json"),
                "--bls",
                str(self.d / "none"),
                "--loader",
                str(self.d),
            ],
            check=True,
            capture_output=True,
        )
        self.assertEqual(cfg.read_text(), before)

    def test_static_insertion_ignores_title_lines(self):
        text = "set timeout=5\nmenuentry 'two\nblscfg\nlines' {\n}\n"
        cfg = self.d / "grub.cfg"
        cfg.write_text(text)
        subprocess.run(
            [
                sys.executable,
                str(BIN / "material-grub-static"),
                str(cfg),
                "--mode",
                "1920x1080",
                "--pkg",
                str(PKG),
                "--backup",
                str(self.d / "bk"),
            ],
            check=True,
            capture_output=True,
        )
        out = cfg.read_text()
        self.assertLess(out.index("static theme begin"), out.index("menuentry 'two"))
        self.assertGreater(out.index("static theme begin"), out.index("set timeout=5"))


if __name__ == "__main__":
    unittest.main()
