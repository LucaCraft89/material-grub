"""The commands of `material-boot grub`: apply, doctor, preview, ventoy, uninstall. stdlib only (Python 3.8+).

    material-boot grub apply               regenerate grub.cfg and re-apply the theme (root)
    material-boot grub doctor [--json]     check the installation (alias: status)
    material-boot grub preview             render your boot entries as a web page, nothing is installed
    material-boot grub ventoy [STICK] ...  theme a Ventoy stick (without STICK: finds it)
    material-boot grub uninstall           remove Material GRUB (root)

The look itself (style, colours, presets, per-entry changes) is edited with `material-boot core conf | colour | presets | overrides` or in the editor
(`material-boot ui`); the old `material-grub` command is gone (1.2.0). Commands that write system files ask for root themselves (through sudo, in a terminal).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(
    1, str(HERE.parent)
)  # a checkout keeps ventoy_sticks.py in install/; the installed package has it in bin/

PKG = Path(os.environ.get("MATERIAL_PKG") or HERE.parent)
PROG = "material-boot grub"


def say(msg=""):
    print(msg, flush=True)


def elevate(argv, paths=()):
    """Re-run `material-boot grub ...` as root through sudo when something it writes is not writable by us."""
    from material_boot import cli

    return cli.elevate(["grub", *argv], paths)


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
        sys.exit("material-boot grub: grub-mkconfig not found")
    cfg = "/boot/grub2/grub.cfg" if Path("/boot/grub2/grub.cfg").is_file() else "/boot/grub/grub.cfg"
    post = "/usr/libexec/material-grub-postprocess"
    if not Path(post).is_file():
        sys.exit("material-boot grub: not installed (" + post + " is missing)")
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


def c_ventoy(argv):
    import ventoy_sticks

    if argv and not argv[0].startswith("-"):
        stick, rest = argv[0], argv[1:]
    else:
        stick, rest = "", argv
        found = [s for s in ventoy_sticks.detect() if s["mounted"]]
        if not found:
            say(
                "No mounted Ventoy stick found. Mount it (open it in your file manager) or give the mount point: material-boot grub ventoy /run/media/you/Ventoy"
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


COMMANDS = {
    "doctor": c_doctor, "status": c_doctor, "apply": c_apply, "preview": c_preview,
    "ventoy": c_ventoy, "uninstall": c_uninstall,
}  # fmt: skip
MOVED = {  # the words of the old `material-grub` command, and where they went
    "gui": "material-boot ui",
    "colour": "material-boot core colour",
    "color": "material-boot core colour",
    "seed": "material-boot core colour",
    "presets": "material-boot core presets",
    "preset": "material-boot core presets",
    "overrides": "material-boot core overrides",
    "conf": "material-boot core conf",
    "config": "material-boot core conf",
    "update": "material-boot core install (sudo; it updates and installs what is missing)",
    "version": "material-boot version",
}


def main(argv):
    """`material-boot grub ...`. Returns the exit status."""
    if not argv or argv[0] in ("-h", "--help", "help"):
        say("\n".join((__doc__ or "").strip("\n").split("\n")[0:1]) + "\n")
        for line in (__doc__ or "").strip("\n").split("\n")[2:8]:
            say(line)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = COMMANDS.get(cmd)
    if fn is None:
        if cmd in MOVED:
            say(f"{PROG}: '{cmd}' moved: use  {MOVED[cmd]}")
        else:
            say(f"{PROG}: unknown command '{cmd}' (try: {', '.join(c for c in COMMANDS if c != 'status')})")
        return 2
    return fn(rest) or 0


def main_quiet(argv=None):
    """A reader that closes the pipe (`... | head -1`) is not an error: no traceback, the status of a SIGPIPE'd program."""
    try:
        code = main(list(sys.argv[1:] if argv is None else argv))
        sys.stdout.flush()
        return code
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141


if __name__ == "__main__":
    sys.exit(main_quiet())
