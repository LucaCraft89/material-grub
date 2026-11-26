"""material-grub: the one command for everything. stdlib only (Python 3.8+).

    material-grub                     a menu of everything below (a terminal UI)
    material-grub doctor [--json]     check the installation (alias: status)
    material-grub apply               regenerate grub.cfg and re-apply the theme (root)
    material-grub gui                 the optional graphical editor
    material-grub preview             render your boot entries as a web page, nothing is installed
    material-grub colour [WHAT]       one seed colour for the whole theme (#RRGGBB or a name), or `multi`
    material-grub presets ...         list | save NAME | apply NAME | delete NAME | export NAME FILE | import FILE
    material-grub overrides ...       show | check | path | edit
    material-grub conf [KEY=VALUE]    show or change the runtime options of /etc/material-grub.conf
    material-grub ventoy [STICK] ...  theme a Ventoy stick (without STICK: finds it)
    material-grub update [--check]    version and how to update
    material-grub uninstall           remove Material GRUB (root)
    material-grub version | help
    material-grub <part> ...          an optional part from another package, when it is installed (material-grub plymouth ...; docs/plugins.md)

Commands that write system files ask for root themselves (through sudo, when you are in a terminal).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(
    1, str(HERE.parent)
)  # a checkout keeps ventoy_sticks.py in install/; the installed package has it in bin/

import mgoverrides  # noqa: E402
import mgplugins  # noqa: E402
import mgrub  # noqa: E402
import mgseeds  # noqa: E402

PKG = Path(os.environ.get("MATERIAL_PKG") or HERE.parent)
RELEASES = "https://api.github.com/repos/LucaCraft89/material-grub/releases/latest"


def version():
    for c in (PKG / "VERSION", HERE.parent.parent / "VERSION"):  # installed package, then a checkout
        try:
            return c.read_text().strip()
        except OSError:
            continue
    return "unknown"


def say(msg=""):
    print(msg, flush=True)


def can_write(path):
    p = Path(path)
    if p.exists():
        return os.access(p, os.W_OK)
    d = p.parent
    while not d.exists() and d != d.parent:
        d = d.parent
    return os.access(d, os.W_OK)


def elevate(argv, paths=()):
    """Re-run this command as root through sudo when something it writes is not writable by us. Returns normally when no elevation is needed."""
    if os.geteuid() == 0 or all(can_write(p) for p in paths) and paths:
        return
    sudo = shutil.which("sudo")
    me = os.environ.get("MG_CLI_SELF") or shutil.which("material-grub") or sys.argv[0]
    if sudo and sys.stdin.isatty():
        say("(this needs root: asking sudo)")
        os.execv(sudo, [sudo, me, *argv])
    sys.exit("material-grub: this needs root: run sudo material-grub " + " ".join(argv))


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], **kw).returncode


def tool(name, *args):
    return (
        run([sys.executable, PKG / "bin" / name, *args])
        if (PKG / "bin" / name).is_file()
        else run([sys.executable, HERE / name, *args])
    )


# ---------------------------------------------------------------- commands
def boot_root_only():
    """True when a GRUB directory exists but we may not look inside it (Fedora makes /boot/grub2 0700)."""
    return any(os.path.isdir(d) and not os.access(d, os.R_OK | os.X_OK) for d in ("/boot/grub2", "/boot/grub"))


def c_doctor(argv):
    import cmd_doctor

    # the theme and grub.cfg cannot be checked without root: ask sudo in a terminal, like apply (scripts and the GUI get the warning)
    if "--root" not in argv and boot_root_only() and sys.stdin.isatty() and shutil.which("sudo"):
        elevate(["doctor", *argv])

    return cmd_doctor.main(argv)


def env_file():
    """/var/lib/material-grub/env: shell-style KEY=VALUE lines written by the installer (MG_IMMUTABLE, MATERIAL_PY, ...)."""
    out = {}
    try:
        for line in Path("/var/lib/material-grub/env").read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip().isidentifier():
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def c_apply(argv):
    """Regenerate grub.cfg and re-apply the theme: grub-mkconfig, then the post-processing (validate, roll back on error), under the same lock as the path unit."""
    if argv[:1] == ["--status"]:
        return c_doctor([])
    elevate(["apply", *argv], ["/boot"])
    env = dict(os.environ, MG_FORCE="1")
    if env_file().get("MG_IMMUTABLE") == "1":
        return run(["sh", "/var/lib/material-grub/postprocess"], env=env)
    mk = shutil.which("grub2-mkconfig") or shutil.which("grub-mkconfig")
    if not mk:
        sys.exit("material-grub: grub-mkconfig not found")
    cfg = "/boot/grub2/grub.cfg" if Path("/boot/grub2/grub.cfg").is_file() else "/boot/grub/grub.cfg"
    post = "/usr/libexec/material-grub-postprocess"
    if not Path(post).is_file():
        sys.exit("material-grub: not installed (" + post + " is missing)")
    script = '"$1" -o "$2" && ' + post
    if shutil.which(
        "flock"
    ):  # the same lock as the path unit: no run may restore an old snapshot over the file written here
        return run(
            ["flock", "/run/material-grub.lock", "sh", "-c", script, "sh", mk, cfg], env=dict(env, MG_LOCKED="1")
        )
    return run(["sh", "-c", script, "sh", mk, cfg], env=env)


def c_preview(argv):
    return tool("material-grub-preview", *argv)


def gui_launcher():
    """The optional GUI's launcher: installed under /usr/share/material-grub-gui (it is not a command of its own), or the checkout's gui/ folder."""
    for c in (Path("/usr/share/material-grub-gui/material-grub-gui"), HERE.parent.parent / "gui/material-grub-gui"):
        if c.is_file():
            return c
    return None


def c_gui(argv):
    gui = gui_launcher()
    if gui is None:
        say("The GUI is not installed. It is optional: install the package `material-grub-gui`,")
        say("or from a checkout of the repository:  sudo ./install.sh --with-gui")
        return 1
    os.execv(sys.executable, [sys.executable, str(gui), *argv])


def seed_from(word):
    w = word.strip()
    if mgseeds.HEX.match(w):
        return w.upper()
    for name, h in mgseeds.SEEDS:
        if name.lower() == w.lower():
            return h
    return None


def c_colour(argv):
    elevate(["colour", *argv], [mgoverrides.path()])
    apply_now = "--apply" in argv
    argv = [a for a in argv if a != "--apply"]
    ov, _ = mgoverrides.load()
    if not argv:
        s = ov["seed"]
        name = mgseeds.name_of(s["color"])
        say(
            f"colours: {'one seed colour ' + s['color'] + (' (' + name + ')' if name else '') if s['mode'] == 'single' else 'every entry its own colour'}"
        )
        say(
            "change it:  material-grub colour #7E57C2 | forest | multi   (names: "
            + ", ".join(n.lower() for n, _ in mgseeds.SEEDS)
            + ")"
        )
        return 0
    if argv[0].lower() == "multi":
        ov["seed"]["mode"] = "multi"
    elif argv[0].lower() == "single":
        ov["seed"]["mode"] = "single"
    else:
        h = seed_from(argv[0])
        if h is None:
            say(f"material-grub: '{argv[0]}' is neither #RRGGBB nor one of the preset names")
            return 2
        ov["seed"] = {"mode": "single", "color": h}
    mgoverrides.save(ov)
    say(f"saved {mgoverrides.path()}")
    return c_apply([]) if apply_now else say("apply it with:  sudo material-grub apply") or 0


def presets_path():
    return mgoverrides.path()


def c_presets(argv):
    import mgpresets

    sub = argv[0] if argv else "list"
    arg = argv[1] if len(argv) > 1 else ""
    p = presets_path()
    if sub == "list":
        rows = mgpresets.listing(p)
        for n, info in rows:
            say(f"  {n:<24} style {info['style']}, {info['entries']} customised")
        if not rows:
            say("no presets yet: material-grub presets save NAME")
        return 0
    try:
        if sub == "save":
            elevate(["presets", *argv], [mgpresets.preset_dir(p) / "x"])
            say(f"saved {mgpresets.save(arg, p, os.environ.get('MATERIAL_CONF'))}")
        elif sub == "apply":
            elevate(["presets", *argv], [p, os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf")])
            mgpresets.apply(mgpresets.load(arg, p), p, os.environ.get("MATERIAL_CONF"))
            say(f"preset '{arg}' written. Apply it with: sudo material-grub apply")
            if "--apply" in argv:
                return c_apply([])
        elif sub == "delete":
            elevate(["presets", *argv], [mgpresets.preset_dir(p) / f"{arg}.json"])
            mgpresets.delete(arg, p)
            say("deleted")
        elif sub == "export":
            Path(argv[2]).write_text(json.dumps(mgpresets.load(arg, p), indent=1) + "\n")
            say(f"wrote {argv[2]}")
        elif sub == "import":
            data = json.loads(Path(arg).read_text())
            clean, errs = mgpresets.validate(data)
            if clean is None:
                say("not a valid preset: " + "; ".join(errs))
                return 1
            elevate(["presets", *argv], [mgpresets.preset_dir(p) / "x"])
            say(f"saved {mgpresets.save(clean['name'], p, data=data)}")
        else:
            say(
                "usage: material-grub presets list | save NAME | apply NAME [--apply] | delete NAME | export NAME FILE | import FILE"
            )
            return 2
    except (ValueError, OSError, IndexError) as e:
        say(f"material-grub: {e}")
        return 1
    return 0


def c_overrides(argv):
    sub = argv[0] if argv else "show"
    p = mgoverrides.path()
    if sub == "path":
        say(str(p))
        return 0
    if sub == "show":
        ov, problems = mgoverrides.load()
        say(json.dumps(ov, indent=1))
        for pr in problems:
            print(pr, file=sys.stderr)
        return 0
    if sub == "check":
        if not p.is_file():
            say(f"{p} does not exist: nothing is customised")
            return 0
        _, errs, warns = (
            mgoverrides.validate(json.loads(p.read_text() or "{}")) if _readable(p) else (None, ["not valid JSON"], [])
        )
        for e in errs:
            say("error: " + e)
        for w in warns:
            say("warning: " + w)
        say("valid" if not errs else "NOT valid (the defaults are used)")
        return 1 if errs else 0
    if sub == "edit":
        elevate(["overrides", "edit"], [p])
        import tempfile

        ov, _ = mgoverrides.load()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "overrides.json"
            f.write_text(json.dumps(ov, indent=1) + "\n")
            editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or shutil.which("nano") or "vi"
            run([editor, f])
            try:
                mgoverrides.save(json.loads(f.read_text()), p)
            except (ValueError, OSError) as e:
                say(f"not saved: {e}")
                return 1
        say(f"saved {p}. Apply it with: sudo material-grub apply")
        return 0
    say("usage: material-grub overrides show | check | path | edit")
    return 2


def _readable(p):
    try:
        json.loads(Path(p).read_text() or "{}")
        return True
    except (OSError, ValueError):
        return False


def c_conf(argv):
    path = os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf")
    if not argv:
        for k, v in mgrub.load_conf(path).items():
            say(f"  {k}={v}")
        return 0
    try:
        updates = dict(a.split("=", 1) for a in argv)
    except ValueError:
        say("usage: material-grub conf [KEY=VALUE ...]   keys: " + ", ".join(mgrub.CONF_DEFAULTS))
        return 2
    elevate(["conf", *argv], [path])
    try:
        mgrub.write_conf(path, updates)
    except ValueError as e:
        say(f"material-grub: {e}")
        return 1
    say("saved; apply it with: sudo material-grub apply (the path unit also does it by itself)")
    return 0


def c_ventoy(argv):
    import ventoy_sticks

    if argv and not argv[0].startswith("-"):
        stick, rest = argv[0], argv[1:]
    else:
        stick, rest = "", argv
        found = [s for s in ventoy_sticks.detect() if s["mounted"]]
        if not found:
            say(
                "No mounted Ventoy stick found. Mount it (open it in your file manager) or give the mount point: material-grub ventoy /run/media/you/Ventoy"
            )
            return 1
        stick = found[0]["path"]
        if len(found) > 1:
            for i, s in enumerate(found, 1):
                say(f"  {i}) {s['label'] or 'Ventoy'}  {s['path']}")
            try:
                stick = found[int(input("which stick? ")) - 1]["path"]
            except (ValueError, IndexError, EOFError):
                return 1
        say(f"using {stick}")
    return tool("material-grub-ventoy", stick, "--pkg", PKG, *rest)


def c_update(argv):
    cur = version()
    say(f"installed: Material GRUB {cur}")
    if "--check" in argv:
        import urllib.request

        try:
            r = urllib.request.Request(
                RELEASES, headers={"User-Agent": "material-grub", "Accept": "application/vnd.github+json"}
            )
            with urllib.request.urlopen(r, timeout=8) as resp:
                latest = str(json.loads(resp.read(1_000_000)).get("tag_name", "")).lstrip("v")
        except Exception as e:
            say(f"could not reach GitHub ({type(e).__name__})")
            return 1

        def tup(v):
            return tuple(int(x) for x in "".join(c if c.isdigit() else " " for c in v).split()[:3])

        say(
            f"latest:    {latest}"
            + ("   <- a newer version is available" if tup(latest) > tup(cur) else "   (you are up to date)")
        )
    kind = "package" if Path("/usr/share/material-grub-src").is_dir() else "source"
    say(
        "update with your package manager (dnf upgrade / apt upgrade / pacman -Syu)"
        if kind == "package"
        else "update with:  git pull && sudo ./install.sh   (in your clone of the repository)"
    )
    return 0


def c_uninstall(argv):
    elevate(["uninstall", *argv], ["/usr/share/material-grub"])
    script = next(
        (
            c
            for c in (
                PKG / "uninstall.sh",
                Path("/usr/share/material-grub-src/install/uninstall.sh"),
                Path("/var/lib/material-grub/uninstall.sh"),
            )
            if c.is_file()
        ),
        None,
    )
    if script is None:
        say("uninstall.sh was not found: from a checkout of the repository run  sudo ./install.sh --uninstall")
        return 1
    if "--yes" not in argv and "-y" not in argv:
        if not sys.stdin.isatty() or input(
            "Remove Material GRUB (your settings in /etc stay)? [y/N] "
        ).strip().lower() not in ("y", "yes"):
            say("nothing changed")
            return 1
    return run(["sh", script])


def core():
    """What an optional part (a plugin) gets to work with: the plugin API version and the helpers of this command. See docs/plugins.md."""
    return SimpleNamespace(
        api=mgplugins.CORE_API,
        version=version(),
        pkg=PKG,
        say=say,
        run=run,
        elevate=elevate,
        conf_path=lambda: os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf"),
        state_dir=lambda: Path(os.environ.get("MATERIAL_STATE_DIR", "/var/lib/material-grub")),
        lib=Path(sys.modules["material_boot"].__file__)
        .resolve()
        .parent.parent,  # the core that is running, and the data it is to use (this package's: one scheme)
        data=PKG,
    )


# optional parts that are known by name, so that asking for one that is not installed gets an answer instead of "unknown command"
KNOWN_PARTS = {"plymouth": ("the Plymouth boot splash", "material-plymouth")}


def c_version(argv):
    say(f"material-grub {version()}")
    for p in mgplugins.usable(COMMANDS):
        say(f"{p.name} {p.version}")
    return 0


def c_help(argv):
    say("\n".join((__doc__ or "").strip("\n").split("\n")[1:]).split("Commands that write")[0].strip("\n"))
    found = mgplugins.discover(COMMANDS)
    if found:
        say("\nOptional parts installed:")
        for p in found:
            say(
                f"  material-grub {p.name:<10}{p.title}"
                + (f": {p.summary}" if p.summary else "")
                + (f"  [{p.problem}]" if p.problem else "")
            )
    return 0


def c_part(name, argv):
    """`material-grub <name> ...` for an optional part: run its plugin, or say why it cannot be run."""
    p = mgplugins.find(name, COMMANDS)
    if p is None:
        title, pkg = KNOWN_PARTS[name]
        say(f"material-grub: {title} is an optional part and it is not installed (package: {pkg}).")
        say("It adds the `material-grub " + name + "` commands; nothing else changes without it.")
        return 1
    if p.problem:
        say(f"material-grub: cannot use '{name}': {p.problem}")
        return 1
    return mgplugins.run(p, argv, core())


COMMANDS = {
    "doctor": c_doctor, "status": c_doctor, "apply": c_apply, "preview": c_preview, "gui": c_gui,
    "colour": c_colour, "color": c_colour, "seed": c_colour, "presets": c_presets, "preset": c_presets,
    "overrides": c_overrides, "conf": c_conf, "config": c_conf, "ventoy": c_ventoy, "update": c_update,
    "uninstall": c_uninstall, "version": c_version, "help": c_help,
}  # fmt: skip


# ---------------------------------------------------------------- the menu
MENU = [
    ("Health check", "Is everything installed and valid?", ["doctor"]),
    ("Apply changes", "Regenerate grub.cfg and re-apply the theme", ["apply"]),
    ("Open the GUI", "The graphical editor (optional package)", ["gui"]),
    ("Preview the menu", "Your boot entries as a web page", ["preview"]),
    ("One colour for everything", "Pick a seed colour (or go back to a colour per entry)", ["@colour"]),
    ("Presets", "Save, apply and delete looks", ["@presets"]),
    ("Settings", "Style, cookie, hints, timeout ...", ["@conf"]),
    ("Ventoy stick", "Theme a Ventoy USB stick", ["ventoy"]),
    ("Check for updates", "Version and how to update", ["update", "--check"]),
    ("Uninstall", "Remove Material GRUB", ["uninstall"]),
    ("Quit", "", None),
]


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
        return ["colour", "multi", "--apply"]
    if r.isdigit() and 1 <= int(r) <= len(mgseeds.SEEDS):
        return ["colour", mgseeds.SEEDS[int(r) - 1][1], "--apply"]
    return ["colour", r, "--apply"] if seed_from(r) else (say("not a colour") or None)


def sub_presets():
    rows = __import__("mgpresets").listing(presets_path())
    say("presets: " + (", ".join(n for n, _ in rows) if rows else "none yet"))
    r = ask("[s]ave current as..., [a]pply one, [d]elete one, Enter cancels: ").lower()
    if r.startswith("s"):
        n = ask("name: ")
        return ["presets", "save", n] if n else None
    if r.startswith(("a", "d")):
        n = ask("which one: ")
        return (
            ["presets", "apply" if r.startswith("a") else "delete", n, *(["--apply"] if r.startswith("a") else [])]
            if n
            else None
        )
    return None


def sub_conf():
    c = mgrub.load_conf()
    for k, v in c.items():
        say(f"  {k}={v}")
    r = ask("change one, like STYLE=list (Enter cancels): ")
    return ["conf", r] if "=" in r else None


def menu_items():
    """The menu: the built-in entries, then those of the installed optional parts, then Quit."""
    return MENU[:-1] + [m for p in mgplugins.usable(COMMANDS) for m in p.menu] + MENU[-1:]


def menu():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return c_help([])
    items = menu_items()
    title = f"Material GRUB {version()}"
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
        if args[0] == "@colour":
            args = sub_colour()
        elif args[0] == "@presets":
            args = sub_presets()
        elif args[0] == "@conf":
            args = sub_conf()
        if args:
            try:
                rc = main(args)
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
            say(f"\n(finished{'' if not rc else ', status ' + str(rc)})")
        ask("Press Enter to return to the menu ")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return menu()
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-h", "--help"):
        return c_help(rest)
    if cmd in ("-V", "--version"):
        return c_version(rest)
    fn = COMMANDS.get(cmd)
    if fn is None and (cmd in KNOWN_PARTS or mgplugins.find(cmd, COMMANDS)):
        return c_part(cmd, rest)
    if fn is None:
        say(f"material-grub: unknown command '{cmd}'\n")
        c_help([])
        return 2
    return fn(rest) or 0


def main_quiet():
    """`material-grub version | head -1`: a reader that closes the pipe is not an error (no traceback, the status of a SIGPIPE'd program)."""
    try:
        code = main()
        sys.stdout.flush()
        return code
    except BrokenPipeError:
        os.dup2(
            os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno()
        )  # so the flush at exit has nowhere to fail either
        return 141


if __name__ == "__main__":
    sys.exit(main_quiet())
