"""material-boot: the one command. stdlib only.

    material-boot                       a menu of everything below (a terminal UI)
    material-boot core <command> ...    the settings and tools of the whole system (material_boot/commands.py): conf, colour, overrides, apply, doctor, parts
    material-boot <part> <command> ...  an installed part: grub, plymouth, gui, ... (docs/plugins.md); a part that is not installed has no module
    material-boot help | version | menu

Only help, version and menu are top-level words: they must work with nothing installed. Everything else belongs to a module, so the dispatcher has no
special cases: `core` is just the module that is always there.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import CORE_API, __version__, plugins

PROG = "material-boot"
TOP = ("help", "version", "menu")
# Parts that are known by name, so that asking for one that is not installed gets an answer instead of "unknown command": name -> (what it is, package).
KNOWN_PARTS = {
    "grub": ("the GRUB theme", "material-grub"),
    "plymouth": ("the Plymouth boot splash", "material-plymouth"),
    "gui": ("the graphical editor", "material-grub-gui"),
}


# ---------------------------------------------------------------- runtime helpers (what a part gets in `core`)
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


def self_command():
    """How to run this command again: $MB_CLI_SELF (the shim sets it), else the one on PATH, else what we were started as."""
    return os.environ.get("MB_CLI_SELF") or shutil.which(PROG) or sys.argv[0]


def elevate(argv, paths=()):
    """Re-run this command as root through sudo when something it writes is not writable by us. Returns normally when no elevation is needed."""
    if os.geteuid() == 0 or all(can_write(p) for p in paths) and paths:
        return
    sudo = shutil.which("sudo")
    if sudo and sys.stdin.isatty():
        say("(this needs root: asking sudo)")
        os.execv(sudo, [sudo, self_command(), *argv])
    sys.exit(f"{PROG}: this needs root: run sudo {PROG} " + " ".join(argv))


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], **kw).returncode


def data_dir():
    """The shared data (palettes, glyphs, fonts, ...): $MATERIAL_DATA, else /usr/share/material-boot/data when it exists, else None."""
    for c in (os.environ.get("MATERIAL_DATA"), "/usr/share/material-boot/data"):
        if c and Path(c).is_dir():
            return Path(c)
    return None


def real_core(parts=None):
    """The `core` object of docs/plugins.md, with the real helpers."""
    names = [p.name for p in plugins.usable()] if parts is None else parts
    return plugins.make_core(say=say, run_cmd=run, elevate=elevate, data=data_dir(), parts=names)


# ---------------------------------------------------------------- the top level
def c_version(argv):
    say(f"{PROG} {__version__} (plugin API {CORE_API})")
    for p in plugins.usable():
        say(f"{p.name} {p.version}")
    return 0


def c_help(argv):
    from . import commands

    say("\n".join((__doc__ or "").strip("\n").split("\n")[1:]).split("Only help, version")[0].strip("\n"))
    say("\nCore commands:")
    for name, (_fn, text) in commands.COMMANDS.items():
        say(f"  {PROG} core {name:<10}{text}")
    found = plugins.discover()
    if found:
        say("\nParts installed:")
        for p in found:
            say(
                f"  {PROG} {p.name:<10}{p.title}"
                + (f": {p.summary}" if p.summary else "")
                + (f"  [{p.problem}]" if p.problem else "")
            )
            for c, text in p.commands.items():
                say(f"      {c:<12}{text}")
    return 0


def c_part(name, argv):
    """`material-boot <name> ...`: run the part, or say why it cannot be run."""
    from . import commands

    p = plugins.find(name)
    if p is None:
        if name in KNOWN_PARTS:
            what, pkg = KNOWN_PARTS[name]
            say(f"{PROG}: {what} is a part and it is not installed (package: {pkg}).")
            say(f"It adds the `{PROG} {name}` commands; nothing else changes without it.")
            return 1
        if name in commands.COMMANDS:
            say(f"{PROG}: '{name}' is a core command. Did you mean:  {PROG} core {name}")
            return 2
        say(f"{PROG}: unknown command '{name}'\n")
        c_help([])
        return 2
    if p.problem:
        say(f"{PROG}: cannot use '{name}': {p.problem}")
        return 1
    return plugins.run(p, argv, real_core())


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "menu":
        from . import menu

        return menu.main(main)
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-h", "--help", "help"):
        return c_help(rest)
    if cmd in ("-V", "--version", "version"):
        return c_version(rest)
    if cmd == "core":
        from . import commands

        return commands.dispatch(rest)
    return c_part(cmd, rest) or 0


if __name__ == "__main__":
    sys.exit(main())
