"""TUI tests: answer logic, shell-safe output, plain prompts, and the real curses UI driven through a pty at 80x24. python3 tests/test_tui.py"""
import fcntl, json, os, pty, select, struct, subprocess, sys, tempfile, termios, time, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install")); import tui
TUI = str(ROOT / "install/tui.py")
MONS = [{"name": "DP-2", "w": 2560, "h": 1440, "primary": True, "source": "xrandr"}, {"name": "eDP-1", "w": 1920, "h": 1080, "primary": False, "source": "xrandr"}]

class Logic(unittest.TestCase):
    def test_snap(self):
        self.assertEqual(tui.snap("2560x1440"), "2560x1440"); self.assertEqual(tui.snap("1600x1000"), "1920x1200"); self.assertEqual(tui.snap("2000x1125"), "1920x1080")
    def test_presets_skip_steps(self):
        steps = tui.build_steps({"RES": "1920x1080", "STYLE": "list", "SCHEME": "dark"}, MONS, False)
        self.assertEqual([s["id"] for s in steps], ["LOGO", "HINTS", "EXTRAS"])
        a = tui.answers(steps, {"RES": "1920x1080", "STYLE": "list", "SCHEME": "dark"}); self.assertEqual((a["RES"], a["STYLE"], a["COOKIE"], a["LOGO"]), ("1920x1080", "list", "on", "on"))
    def test_cookie_off_implies_no_logo(self):
        steps = tui.build_steps({}, MONS, True); [s for s in steps if s["id"] == "LOGO"][0]["cur"] = 2
        a = tui.answers(steps, {}); self.assertEqual((a["COOKIE"], a["LOGO"]), ("off", "off")); self.assertEqual([s["id"] for s in steps][-1:], ["IMMUTABLE"])
    def test_output_is_validated(self):
        with tempfile.NamedTemporaryFile() as f:
            for bad in ({"RES": "1920x1080; rm -rf /"}, {"STYLE": "list'"}, {"TIMEOUT": "12a"}, {"NOPE": "x"}):
                with self.assertRaises(ValueError): tui.write_out(f.name, bad)
            tui.write_out(f.name, {"RES": "1920x1080", "TIMEOUT": ""}); self.assertEqual(Path(f.name).read_text(), "RES='1920x1080'\nTIMEOUT=''\n")

class Plain(unittest.TestCase):
    def test_plain_prompts(self):
        with tempfile.TemporaryDirectory() as d:
            mon = Path(d) / "m.json"; mon.write_text(json.dumps(MONS)); out = Path(d) / "o"
            r = subprocess.run([sys.executable, TUI, "--out", out, "--plain", "--monitors", mon], input="2\n3\n2\n\n2\n\n\n12\ny\n", capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr); t = out.read_text(); self.assertIn("RES='1920x1080'", t); self.assertIn("STYLE='list'", t); self.assertIn("SCHEME='light'", t); self.assertIn("TIMEOUT='12'", t)
            r = subprocess.run([sys.executable, TUI, "--out", out, "--plain", "--monitors", mon], input="\n\n\n\n\n\n\n\nn\n", capture_output=True, text=True); self.assertEqual(r.returncode, 1)

def drive(keys, env_extra=None, size=(24, 80), cmd=None):
    """Run tui.py on a pty of the given size, send keys, return (exit status, screen text)."""
    d = tempfile.mkdtemp(); mon = Path(d) / "m.json"; mon.write_text(json.dumps(MONS)); out = Path(d) / "o"
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update({"TERM": "xterm", "LINES": str(size[0]), "COLUMNS": str(size[1])}); os.execv(*(cmd or (sys.executable, [sys.executable, TUI, "--out", str(out), "--monitors", str(mon)])))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", size[0], size[1], 0, 0)); buf = b""
    def pump(t):
        nonlocal buf; end = time.time() + t
        while time.time() < end:
            if select.select([fd], [], [], 0.05)[0]:
                try: buf += os.read(fd, 65536)
                except OSError: return
    pump(0.8)
    for k in keys: os.write(fd, k); pump(0.25)
    pump(0.5)
    st = 0; reaped = False
    for _ in range(40 if cmd else 1):       # install.sh keeps running after the questions: wait for it to finish
        try: p, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError: break
        if p: st, reaped = status, True; break
        pump(0.25)
    if reaped: return os.waitstatus_to_exitcode(st), buf.decode(errors="replace"), out
    if st == 0 and not out.exists():
        try: os.kill(pid, 9); os.waitpid(pid, 0)
        except Exception: pass
        return None, buf.decode(errors="replace"), out
    return os.waitstatus_to_exitcode(st), buf.decode(errors="replace"), out

ENTER, DOWN, LEFT = b"\r", b"\x1bOB", b"\x1bOD"   # xterm application-keypad sequences (what curses enables)
class Curses(unittest.TestCase):
    def test_full_flow(self):
        keys = [DOWN, ENTER,                      # resolution: second monitor (1920x1080)
                DOWN, DOWN, ENTER,                # style: list
                DOWN, ENTER,                      # scheme: light
                DOWN, DOWN, ENTER,                # logo: neither
                DOWN, ENTER,                      # hints: off
                ENTER,                            # extras: keep
                ENTER]                            # summary: install
        code, screen, out = drive(keys); self.assertEqual(code, 0, screen[-600:]); t = out.read_text()
        for want in ("RES='1920x1080'", "STYLE='list'", "SCHEME='light'", "COOKIE='off'", "LOGO='off'", "HINTS='off'"): self.assertIn(want, t)
        for text in ("Material GRUB installer", "Resolution", "(primary)", "Summary"): self.assertIn(text, screen)
    def test_quit_and_back(self):
        code, screen, out = drive([ENTER, ENTER, LEFT, b"q"]); self.assertEqual(code, 1); self.assertFalse(out.exists())
    def test_too_small_message(self):
        code, screen, out = drive([b"q"], size=(20, 60)); self.assertIn("enlarge the terminal", screen)

class Installer(unittest.TestCase):     # install.sh itself: TUI -> answers -> settings line (stage-only on the built package, no root, nothing installed)
    CMD = ("/bin/sh", ["sh", str(ROOT / "install.sh"), "--tui", "--stage-only", "--no-deps", "--res", "1920x1080", "--pkg", str(ROOT / "dist/material-grub")])
    @unittest.skipUnless((ROOT / "dist/material-grub/res").is_dir(), "no built package")
    def test_tui_to_settings(self):
        code, screen, _ = drive([DOWN, DOWN, ENTER, ENTER, ENTER, DOWN, ENTER, ENTER, ENTER], cmd=self.CMD)    # style list, scheme dark, logo both, hints off, extras keep, summary ok
        self.assertEqual(code, 0, screen[-400:]); flat = " ".join(screen.split())
        self.assertIn("settings for /etc/material-grub.conf: STYLE=list COOKIE=on LOGO=on HINTS=off SCHEME=dark", flat)
    @unittest.skipUnless((ROOT / "dist/material-grub/res").is_dir(), "no built package")
    def test_cancel_changes_nothing(self):
        code, screen, _ = drive([b"q"], cmd=self.CMD); self.assertNotEqual(code, 0); self.assertIn("cancelled", " ".join(screen.split()))

if __name__ == "__main__": unittest.main()
