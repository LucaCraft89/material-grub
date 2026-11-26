"""`material-boot core <command>`: the settings and tools that belong to the whole system, not to one part. stdlib only.

    conf [KEY=VALUE ...]      show or change the runtime options of /etc/material-grub.conf (shared by every part)
    colour [WHAT]             one seed colour for the whole look (#RRGGBB or a name), or `multi`
    presets ...               list | save NAME | apply NAME | delete NAME | export NAME FILE | import FILE
    overrides ...             show | check | path | edit   (colours, names and icons per entry)
    apply [--only PART]       rebuild the shared data when the scheme changed, then run the `apply` command of every installed part that has one
    doctor                    the state of the core and of every part (and each part's own checks)
    parts                     which parts are installed, and why one cannot be used
    install ...               install, update or remove parts (material_boot/installer.py, docs/installer.md)

`conf`, `colour`, `presets` and `overrides` are the commands of material-grub's `material-grub` that only ever needed the shared code; the bodies are the same
(only the program name in the messages changed, and "apply" now means every installed part). `update`, `uninstall` and `gui` come with the code they need.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import CORE_API, __version__, plugins
from . import conf as mgconf
from . import overrides as mgoverrides
from . import presets as mgpresets
from . import seeds as mgseeds
from .cli import PROG, elevate, real_core, run, say


# ---------------------------------------------------------------- conf, colour, overrides
def c_conf(argv):
    path = os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf")
    if not argv:
        for k, v in mgconf.load_conf(path).items():
            say(f"  {k}={v}")
        return 0
    try:
        updates = dict(a.split("=", 1) for a in argv)
    except ValueError:
        say(f"usage: {PROG} core conf [KEY=VALUE ...]   keys: " + ", ".join(mgconf.CONF_DEFAULTS))
        return 2
    elevate(["core", "conf", *argv], [path])
    try:
        mgconf.write_conf(path, updates)
    except ValueError as e:
        say(f"{PROG}: {e}")
        return 1
    say(f"saved; apply it with: sudo {PROG} core apply (the path unit also does it by itself)")
    return 0


def seed_from(word):
    w = word.strip()
    if mgseeds.HEX.match(w):
        return w.upper()
    for name, h in mgseeds.SEEDS:
        if name.lower() == w.lower():
            return h
    return None


def c_colour(argv):
    elevate(["core", "colour", *argv], [mgoverrides.path()])
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
            f"change it:  {PROG} core colour #7E57C2 | forest | multi   (names: "
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
            say(f"{PROG}: '{argv[0]}' is neither #RRGGBB nor one of the preset names")
            return 2
        ov["seed"] = {"mode": "single", "color": h}
    mgoverrides.save(ov)
    say(f"saved {mgoverrides.path()}")
    return c_apply([]) if apply_now else say(f"apply it with:  sudo {PROG} core apply") or 0


def presets_path():
    return mgoverrides.path()


def c_presets(argv):
    sub = argv[0] if argv else "list"
    arg = argv[1] if len(argv) > 1 else ""
    p = presets_path()
    if sub == "list":
        rows = mgpresets.listing(p)
        for n, info in rows:
            say(f"  {n:<24} style {info['style']}, {info['entries']} customised")
        if not rows:
            say(f"no presets yet: {PROG} core presets save NAME")
        return 0
    try:
        if sub == "save":
            elevate(["core", "presets", *argv], [mgpresets.preset_dir(p) / "x"])
            say(f"saved {mgpresets.save(arg, p, os.environ.get('MATERIAL_CONF'))}")
        elif sub == "apply":
            elevate(["core", "presets", *argv], [p, os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf")])
            mgpresets.apply(mgpresets.load(arg, p), p, os.environ.get("MATERIAL_CONF"))
            say(f"preset '{arg}' written. Apply it with: sudo {PROG} core apply")
            if "--apply" in argv:
                return c_apply([])
        elif sub == "delete":
            elevate(["core", "presets", *argv], [mgpresets.preset_dir(p) / f"{arg}.json"])
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
            elevate(["core", "presets", *argv], [mgpresets.preset_dir(p) / "x"])
            say(f"saved {mgpresets.save(clean['name'], p, data=data)}")
        else:
            say(
                f"usage: {PROG} core presets list | save NAME | apply NAME [--apply] | delete NAME | export NAME FILE | import FILE"
            )
            return 2
    except (ValueError, OSError, IndexError) as e:
        say(f"{PROG}: {e}")
        return 1
    return 0


def _readable(p):
    try:
        json.loads(Path(p).read_text() or "{}")
        return True
    except (OSError, ValueError):
        return False


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
        elevate(["core", "overrides", "edit"], [p])
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
        say(f"saved {p}. Apply it with: sudo {PROG} core apply")
        return 0
    say(f"usage: {PROG} core overrides show | check | path | edit")
    return 2


# ---------------------------------------------------------------- parts, apply, doctor
def c_install(argv):
    from . import installer

    if not ({"--dry-run", "--root", "-h", "--help"} & set(argv) or any(a.startswith("--root=") for a in argv)):
        elevate(["core", "install", *argv], [os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf")])
    return installer.main(argv, say=say)


def c_parts(argv):
    found = plugins.discover()
    if not found:
        say("no parts are installed (the core alone: conf, colour, overrides)")
        return 0
    for p in found:
        status = "ok" if p.problem is None else "NOT USABLE"
        say(f"  {p.name:<12}{p.version:<10}{status:<11}{p.title}")
        if p.problem:
            say(f"      {p.problem}")
        for w in p.warnings:
            say(f"      warning: {w}")
        for s in p.shadows:
            say(f"      warning: {s} is shadowed by an earlier plugin directory")
    return 1 if any(p.problem for p in found) else 0


def c_apply(argv):
    """Run `apply` of every installed part that declares one, in name order; one part failing does not stop the others, and the exit status says so.
    `--only PART` runs just that one; everything else is handed to each part's own apply."""
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        only = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2 :]
        if not only:
            say(f"usage: {PROG} core apply [--only PART] [ARGS passed to the parts]")
            return 2
    if (
        only in (None, "core")
    ):  # the shared data depends on the scheme: a changed SCHEME means the data is rebuilt before any part draws from it
        from . import coreinstall

        try:
            msg = coreinstall.refresh_data("", mgconf.load_conf().get("SCHEME"))
        except (RuntimeError, OSError) as e:
            say(f"{PROG}: {e}")
            return 1
        if msg:
            say(msg)
        if only == "core":
            return 0
    parts = [p for p in plugins.usable() if "apply" in p.commands and only in (None, p.name)]
    if only and not parts:
        say(f"{PROG}: no usable part '{only}' with an apply command")
        return 1
    if not parts:
        say("nothing to apply: no installed part has an apply command")
        return 0
    core, failed = real_core(), []
    for p in parts:
        say(f"== {p.name}: apply")
        rc = plugins.run(p, ["apply", *argv], core)
        if rc:
            failed.append(p.name)
            say(f"{PROG}: {p.name} apply failed (status {rc})")
    if failed:
        say(f"{PROG}: failed: {', '.join(failed)}")
        return 1
    return 0


def c_doctor(argv):
    found = plugins.discover()
    bad = 0
    say(f"{PROG} {__version__} (plugin API {CORE_API})")
    say("parts:" + ("" if found else " none installed"))
    for p in found:
        if p.problem:
            bad += 1
            say(f"  FAIL  {p.name} {p.version}: {p.problem}")
        else:
            say(f"  ok    {p.name} {p.version}  {p.title}")
        for w in p.warnings:
            say(f"        warning: {w}")
    ctx = plugins.make_ctx(core=real_core())
    for p in found:
        if p.problem or "doctor" not in p.hooks:
            continue
        r = plugins.call_hook(p, "doctor", ctx)
        say(f"\n{p.title}:")
        if not r.ok:
            bad += 1
            say(f"  FAIL  {r.error}")
            continue
        for level, text in r.value or []:
            say(f"  {str(level):<5} {text}")
            bad += level in ("fail", "error")
    return 1 if bad else 0


COMMANDS = {
    "conf": (c_conf, "show or change the shared settings (/etc/material-grub.conf)"),
    "colour": (c_colour, "one seed colour for the whole look, or a colour per entry"),
    "presets": (c_presets, "save, apply and delete looks: list | save | apply | delete | export | import"),
    "overrides": (c_overrides, "colours, names and icons per entry: show | check | path | edit"),
    "apply": (c_apply, "apply the look: the `apply` of every installed part"),
    "doctor": (c_doctor, "the state of the core and of every part"),
    "install": (c_install, "install, update or remove parts: --with, --without, --only, --dry-run, --uninstall"),
    "parts": (c_parts, "which parts are installed, and why one cannot be used"),
}
ALIASES = {"color": "colour", "seed": "colour", "preset": "presets", "config": "conf", "status": "doctor"}


def dispatch(argv):
    """`material-boot core ...`"""
    if not argv or argv[0] in ("help", "-h", "--help"):
        say(f"{PROG} core <command>:")
        for name, (_fn, text) in COMMANDS.items():
            say(f"  {name:<10}{text}")
        return 0
    name = ALIASES.get(argv[0], argv[0])
    if name not in COMMANDS:
        say(f"{PROG}: unknown core command '{argv[0]}' (try: {', '.join(COMMANDS)})")
        return 2
    return COMMANDS[name][0](argv[1:]) or 0
