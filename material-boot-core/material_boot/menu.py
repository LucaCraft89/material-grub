"""The menu of `material-boot` when it is run alone in a terminal: the core's entries, then the entries of every installed part (their manifests), then Quit.
The pickers (curses, with a plain numbered fallback) are material-grub's, moved as they were. stdlib only."""

import os
import sys

from . import __version__, plugins
from . import conf as mgconf
from . import overrides as mgoverrides
from . import presets as mgpresets
from . import seeds as mgseeds
from .cli import say

# title, description, command words (None quits). A word starting with @ is a sub-menu asked in the terminal first.
CORE_MENU = [
    ("Health check", "Is everything installed and valid?", ["core", "doctor"]),
    ("Apply changes", "Apply the look through every installed part", ["core", "apply"]),
    ("One colour for everything", "Pick a seed colour (or a colour per entry)", ["@colour"]),
    ("Presets", "Save, apply and delete looks", ["@presets"]),
    ("Settings", "Style, cookie, hints, timeout ...", ["@conf"]),
    ("Parts", "Which parts are installed", ["core", "parts"]),
]
QUIT = ("Quit", "", None)


def pick(items, title):
    """Curses list menu. Returns the chosen index or None."""
    import curses

    def ui(scr):
        curses.curs_set(0)
        scr.keypad(True)
        cur = 0
        while True:
            scr.erase()
            h, w = scr.getmaxyx()
            scr.addstr(0, 2, title[: w - 4], curses.A_BOLD)
            scr.addstr(1, 2, "Up/Down choose   Enter run   q quit"[: w - 4], curses.A_DIM)
            for i, (label, desc, _) in enumerate(items):
                y = 3 + i
                if y >= h - 1:
                    break
                line = f" {label:<28} {desc}"
                scr.addstr(y, 2, line[: w - 4], curses.A_REVERSE if i == cur else 0)
            k = scr.getch()
            if k in (curses.KEY_UP, ord("k")):
                cur = (cur - 1) % len(items)
            elif k in (curses.KEY_DOWN, ord("j")):
                cur = (cur + 1) % len(items)
            elif k in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT):
                return cur
            elif k in (ord("q"), 27):
                return None

    return curses.wrapper(ui)


def pick_plain(items, title):
    say(title)
    for i, (label, desc, _) in enumerate(items, 1):
        say(f"  {i:>2}) {label:<28} {desc}")
    try:
        r = input("choice (Enter quits): ").strip()
    except EOFError:
        return None
    return int(r) - 1 if r.isdigit() and 1 <= int(r) <= len(items) else None


def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def sub_colour():
    from .commands import seed_from

    ov, _ = mgoverrides.load()
    say(
        f"now: {'one seed colour ' + ov['seed']['color'] if ov['seed']['mode'] == 'single' else 'every entry its own colour'}"
    )
    say("  0) every entry its own colour")
    for i, (n, h) in enumerate(mgseeds.SEEDS, 1):
        say(f"  {i:>2}) {n:<10} {h}")
    r = ask("pick a number, a name, or any #RRGGBB (Enter cancels): ")
    if not r:
        return None
    if r == "0":
        return ["core", "colour", "multi", "--apply"]
    if r.isdigit() and 1 <= int(r) <= len(mgseeds.SEEDS):
        return ["core", "colour", mgseeds.SEEDS[int(r) - 1][1], "--apply"]
    return ["core", "colour", r, "--apply"] if seed_from(r) else (say("not a colour") or None)


def sub_presets():
    from .commands import presets_path

    rows = mgpresets.listing(presets_path())
    say("presets: " + (", ".join(n for n, _ in rows) if rows else "none yet"))
    r = ask("[s]ave current as..., [a]pply one, [d]elete one, Enter cancels: ").lower()
    if r.startswith("s"):
        n = ask("name: ")
        return ["core", "presets", "save", n] if n else None
    if r.startswith(("a", "d")):
        n = ask("which one: ")
        return (
            [
                "core",
                "presets",
                "apply" if r.startswith("a") else "delete",
                n,
                *(["--apply"] if r.startswith("a") else []),
            ]
            if n
            else None
        )
    return None


def sub_conf():
    c = mgconf.load_conf()
    for k, v in c.items():
        say(f"  {k}={v}")
    r = ask("change one, like STYLE=list (Enter cancels): ")
    return ["core", "conf", r] if "=" in r else None


SUBMENUS = {"@colour": sub_colour, "@presets": sub_presets, "@conf": sub_conf}


def menu_items():
    """The core's entries, then those of the installed parts, then Quit."""
    return CORE_MENU + [m for p in plugins.usable() for m in p.menu] + [QUIT]


def main(dispatch):
    """Run the menu; `dispatch(argv)` runs one command (cli.main). Without a terminal there is nothing to pick from: print the help."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return dispatch(["help"])
    items = menu_items()
    title = f"Material Boot {__version__}"
    use_curses = os.environ.get("TERM", "dumb") not in ("dumb", "")
    while True:
        try:
            i = pick(items, title) if use_curses else pick_plain(items, title)
        except Exception:  # no usable curses: fall back to prompts
            use_curses = False
            continue
        if i is None or items[i][2] is None:
            return 0
        args = items[i][2]
        if args[0] in SUBMENUS:
            args = SUBMENUS[args[0]]()
        if args:
            try:
                rc = dispatch(args)
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
            say(f"\n(finished{'' if not rc else ', status ' + str(rc)})")
        ask("Press Enter to return to the menu ")
