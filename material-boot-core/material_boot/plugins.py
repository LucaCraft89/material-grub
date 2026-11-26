"""The parts of Material Boot (material-grub, material-plymouth, the GUI, ...) and how the core finds, checks and runs them. Plugin API 2. stdlib only.

A part announces itself by dropping ONE manifest into a plugin directory; the core knows nothing about its code. A part that is not installed has no
manifest, so it has no module, no menu entry and no line in `doctor`. A broken, incompatible or unsatisfied part never breaks `material-boot`: it is
reported (`doctor`, `help`) and the rest keeps working. The contract, in prose, is docs/plugins.md.

    <plugin dir>/<name>.json
    {
      "manifest": 2,
      "name": "plymouth",                  # the module: `material-boot plymouth ...`
      "title": "Plymouth boot splash",
      "version": "1.0.0",
      "summary": "boot splash that continues the GRUB theme",
      "core_api": 2,                       # must equal CORE_API
      "core_min": "1.0.0",                 # optional: the oldest material-boot-core this part works with
      "entry": "/usr/share/material-plymouth/bin/mgplugin.py",   # absolute path of a Python file that defines main(argv, core) -> int
      "commands": {"apply": "render the theme and rebuild the initramfs", "status": "what is installed"},
      "menu": [["Apply the Plymouth theme", "Render it and rebuild the initramfs", ["plymouth", "apply"]]],
      "conf": ["PLYMOUTH", "PLYMOUTH_BAR", "PLYMOUTH_MOTION"],   # the keys of /etc/material-grub.conf this part owns
      "install": {"default": false, "needs": ["grub"], "package": "material-plymouth", "layouts": ["normal"],
                  "options": [{"name": "no-cmdline", "takes": "flag", "summary": "never edit the kernel command line"}]},  # for the installer
      "hooks": ["detect", "install", "uninstall", "migrate", "verify", "doctor"]   # the optional hook_<name>(ctx) functions the entry file defines
    }

Plugin directories: $MATERIAL_PLUGIN_PATH (os.pathsep separated, used by the tests and by checkouts), else /usr/share/material-boot/plugins.d and
/usr/local/share/material-boot/plugins.d.
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from . import CORE_API, __version__

MANIFEST = 2
NAME = re.compile(r"^[a-z][a-z0-9-]{1,19}$")
COMMAND = re.compile(r"^[a-z][a-z0-9-]{0,29}$")
CONF_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")
OPTION = re.compile(r"^[a-z][a-z0-9-]{0,29}$")
# Words that are the core's own: the built-in module and the top-level commands. A part cannot take them over.
RESERVED = frozenset({"core", "help", "version", "menu"})
# The hooks the unified installer and `doctor` may call, each as a function `hook_<name>(ctx)` in the part's entry file.
HOOKS = ("detect", "plan", "install", "uninstall", "migrate", "verify", "doctor")
DEFAULT_DIRS = ("/usr/share/material-boot/plugins.d", "/usr/local/share/material-boot/plugins.d")
MAX_MANIFEST = 64 * 1024


def version_tuple(v):
    """'1.2.3' -> (1, 2, 3); None when it is not dotted numbers."""
    if not isinstance(v, str) or not re.fullmatch(r"\d+(\.\d+){0,3}", v):
        return None
    return tuple(int(x) for x in v.split("."))


def search_dirs():
    env = os.environ.get("MATERIAL_PLUGIN_PATH")
    return [Path(d) for d in (env.split(os.pathsep) if env is not None else DEFAULT_DIRS) if d]


def _clean_menu(menu, name, warnings):
    out = []
    for m in menu if isinstance(menu, list) else []:
        ok = (
            isinstance(m, list)
            and len(m) == 3
            and isinstance(m[0], str)
            and isinstance(m[1], str)
            and isinstance(m[2], list)
            and m[2]
            and all(isinstance(a, str) for a in m[2])
        )
        if not ok:
            warnings.append(f"{name}: a menu entry is malformed and was ignored")
        elif m[2][0] != name:
            warnings.append(f"{name}: the menu entry {m[0]!r} runs {m[2][0]!r}, not this part, and was ignored")
        else:
            out.append((m[0], m[1], m[2]))
    return out


def read_manifest(path, core_version=None):
    """One manifest file -> a part record (SimpleNamespace). `problem` is None when the part is usable, else a sentence for `doctor`;
    `warnings` are things that were ignored. Never raises."""
    path = Path(path)
    p = SimpleNamespace(
        name=path.stem,
        title=path.stem,
        version="?",
        summary="",
        entry=None,
        commands={},
        menu=[],
        conf=[],
        hooks=(),
        default=False,
        needs=[],
        options=[],
        layouts=[],
        package=None,
        source=None,
        core_min=None,
        path=path,
        problem=None,
        warnings=[],
        shadows=[],
    )
    try:
        if path.stat().st_size > MAX_MANIFEST:
            raise ValueError("the manifest is too large")
        m = json.loads(path.read_text())
        if not isinstance(m, dict):
            raise ValueError("the manifest must be a JSON object")
    except (OSError, ValueError) as e:
        p.problem = f"cannot read {path}: {e}"
        return p
    name = m.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        p.problem = f"{path}: 'name' must be 2 to 20 characters: a letter, then lowercase letters, digits or '-'"
        return p
    p.name = name
    p.title = m.get("title") if isinstance(m.get("title"), str) else name
    p.version = str(m.get("version", "?"))[:40]
    p.summary = m.get("summary") if isinstance(m.get("summary"), str) else ""
    if name in RESERVED:
        p.problem = f"{path}: '{name}' belongs to the core and cannot be taken over by a part"
        return p
    if m.get("manifest") != MANIFEST:
        p.problem = f"{path}: unknown manifest version {m.get('manifest')!r} (this core reads {MANIFEST})"
        return p
    if m.get("core_api") != CORE_API:
        p.problem = (
            f"{name} {p.version} was written for plugin API {m.get('core_api')!r}, this core has {CORE_API}: "
            "update whichever of the two is older"
        )
        return p
    core_version = core_version or __version__
    if m.get("core_min") is not None:
        need = version_tuple(m["core_min"])
        have = version_tuple(core_version)
        if need is None:
            p.problem = f"{name}: 'core_min' {m['core_min']!r} is not a version"
            return p
        p.core_min = m["core_min"]
        if have is not None and have < need:
            p.problem = f"{name} {p.version} needs material-boot-core {m['core_min']} or newer, this is {core_version}: update the core"
            return p
    entry = m.get("entry")
    if isinstance(entry, str) and entry and not os.path.isabs(entry):
        entry = str(
            path.resolve().parent / entry
        )  # a bundle's manifest cannot know where it will be unpacked: relative to the manifest
    if not isinstance(entry, str) or not entry or not Path(entry).is_file():
        p.problem = f"{name}: its entry file {m.get('entry')!r} is missing (is the package half removed?)"
        return p
    p.entry = entry
    cmds = m.get("commands", {})
    if isinstance(cmds, dict):
        for c, text in cmds.items():
            if COMMAND.match(c) and isinstance(text, str):
                p.commands[c] = text
            else:
                p.warnings.append(f"{name}: the command {c!r} is malformed and was ignored")
    else:
        p.warnings.append(f"{name}: 'commands' must be an object and was ignored")
    p.menu = _clean_menu(m.get("menu"), name, p.warnings)
    p.conf = (
        [k for k in m.get("conf", []) if isinstance(k, str) and CONF_KEY.match(k)]
        if isinstance(m.get("conf"), list)
        else []
    )
    hooks = m.get("hooks", [])
    p.hooks = tuple(h for h in hooks if h in HOOKS) if isinstance(hooks, list) else ()
    if isinstance(hooks, list) and len(p.hooks) != len(hooks):
        p.warnings.append(f"{name}: unknown hooks were ignored (known: {', '.join(HOOKS)})")
    inst = m.get("install") if isinstance(m.get("install"), dict) else {}
    p.default = inst.get("default") is True
    p.package = inst.get("package") if isinstance(inst.get("package"), str) else None
    layouts = inst.get("layouts", [])
    p.layouts = [x for x in layouts if x in ("normal", "immutable")] if isinstance(layouts, list) else []
    for o in inst.get("options", []) if isinstance(inst.get("options"), list) else []:
        if isinstance(o, dict) and isinstance(o.get("name"), str) and OPTION.match(o["name"]):
            p.options.append(
                {
                    "name": o["name"],
                    "takes": "value" if o.get("takes") == "value" else "flag",
                    "summary": str(o.get("summary", ""))[:200],
                }
            )
        else:
            p.warnings.append(f"{name}: an install option is malformed and was ignored")
    needs = inst.get("needs", [])
    if isinstance(needs, list) and all(isinstance(n, str) and (n == "core" or NAME.match(n)) for n in needs):
        p.needs = [
            n for n in dict.fromkeys(needs) if n != "core"
        ]  # the core is always there: it is what is reading this
    else:
        p.problem = f"{name}: install.needs must be a list of part names"
    return p


def discover(dirs=None, core_version=None):
    """Every part found in the plugin directories, usable or not, ordered by name, with their dependencies resolved (see resolve).
    The first manifest of a name wins (earlier directories first); the paths of the others are kept in `.shadows` so `doctor` can say so."""
    found = {}
    for d in dirs if dirs is not None else search_dirs():
        try:
            files = sorted(d.glob("*.json"))
        except OSError:
            continue
        for f in files:
            rec = read_manifest(f, core_version)
            if rec.name in found:
                found[rec.name].shadows.append(f)
            else:
                found[rec.name] = rec
    return resolve([found[k] for k in sorted(found)])


def discover_bundle(bundle, core_version=None):
    """The parts a bundle (see docs/installer.md) carries, usable or not: parts/<name>/manifest.json, with `entry` relative to the manifest. They are not
    installed yet, so no plugin directory knows them. Each record's `source` is the part's directory in the bundle."""
    found = []
    try:
        files = sorted(Path(bundle).glob("parts/*/manifest.json"))
    except OSError:
        files = []
    for f in files:
        rec = read_manifest(f, core_version)
        rec.source = f.parent
        found.append(rec)
    return resolve(found)


def resolve(parts):
    """A part that needs another part (install.needs) which is missing or unusable is itself unusable: `problem` says which one. Repeats until
    nothing changes, so a chain of needs is followed. Returns the same list."""
    changed = True
    while changed:
        changed = False
        by = {p.name: p for p in parts}
        for p in parts:
            if p.problem is None:
                for n in p.needs:
                    d = by.get(n)
                    if d is None or d.problem is not None:
                        why = "is not installed" if d is None else "cannot be used"
                        p.problem = f"{p.name} needs the {n} part, which {why}"
                        changed = True
                        break
    return parts


def usable(dirs=None, core_version=None):
    return [p for p in discover(dirs, core_version) if p.problem is None]


def find(name, dirs=None, core_version=None):
    return next((p for p in discover(dirs, core_version) if p.name == name), None)


def load(part):
    """Import the part's entry file. Raises ImportError with a readable message when it cannot be loaded, has no main(), or lacks a hook its manifest
    promises."""
    if getattr(part, "module", None) is not None:  # a built-in part (the core's own) that is already imported
        return part.module
    spec = importlib.util.spec_from_file_location(f"mbpart_{part.name.replace('-', '_')}", part.entry)
    if spec is None or spec.loader is None:
        raise ImportError(f"{part.entry} is not a Python file")
    mod = importlib.util.module_from_spec(spec)
    here = str(Path(part.entry).resolve().parent)
    sys.path.insert(1, here)  # the part's own modules sit next to its entry file
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise ImportError(f"{part.name}: cannot load {part.entry}: {e}") from e
    finally:
        if here in sys.path:
            sys.path.remove(here)
    if not callable(getattr(mod, "main", None)):
        raise ImportError(f"{part.name}: {part.entry} defines no main(argv, core)")
    missing = [h for h in part.hooks if not callable(getattr(mod, f"hook_{h}", None))]
    if missing:
        raise ImportError(
            f"{part.name}: its manifest lists the hooks {', '.join(missing)} but {part.entry} does not define them"
        )
    return mod


def run(part, argv, core):
    """Run the part's main(argv, core) and return its exit status (an int; None counts as 0). A crash is reported, not raised."""
    try:
        mod = load(part)
    except ImportError as e:
        print(f"material-boot: {e}", file=sys.stderr)
        return 1
    try:
        rc = mod.main(list(argv), core)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # a part's bug must not look like a core bug
        print(f"material-boot: the {part.name} part failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return rc if isinstance(rc, int) else 0


def call_hook(part, name, ctx):
    """Call hook_<name>(ctx) of a part. Returns SimpleNamespace(ok, value, error): a part that does not have the hook, or whose hook crashes, is a
    failed step for the installer to report and roll back, never an exception that takes the installer down."""
    if name not in part.hooks:
        return SimpleNamespace(ok=False, value=None, error=f"{part.name} has no {name} hook")
    try:
        fn = getattr(load(part), f"hook_{name}")
        return SimpleNamespace(ok=True, value=fn(ctx), error=None)
    except Exception as e:
        return SimpleNamespace(
            ok=False, value=None, error=f"{part.name}: the {name} hook failed: {type(e).__name__}: {e}"
        )


def make_core(say=print, run_cmd=None, elevate=None, conf_path=None, data=None, state_dir=None, parts=()):
    """What a part's main(argv, core) and hooks get to work with. The real helpers are the dispatcher's; they are passed in so tests can fake them.

    api, version      CORE_API and the core's version
    data              the directory of the shared data (palettes.json, classes.json, glyphs/, fonts/, ...)
    lib               the directory that holds the material_boot package (a part puts it on sys.path to import the shared modules)
    say(text)         print a line the way the core does
    run(cmd)          run a command, return the CompletedProcess
    elevate(argv, paths)   re-run through sudo when one of `paths` is not writable
    conf_path()       the path of /etc/material-grub.conf (or $MATERIAL_CONF)
    state_dir()       /var/lib/material-grub (or $MATERIAL_STATE_DIR)
    parts             the names of the usable parts, so a part can tell whether another one is installed
    """
    return SimpleNamespace(
        api=CORE_API,
        version=__version__,
        data=Path(data) if data else None,
        lib=Path(__file__).resolve().parent.parent,
        say=say,
        run=run_cmd,
        elevate=elevate,
        conf_path=conf_path or (lambda: Path(os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf"))),
        state_dir=state_dir or (lambda: Path(os.environ.get("MATERIAL_STATE_DIR", "/var/lib/material-grub"))),
        parts=tuple(parts),
    )


def make_ctx(
    core=None,
    root="",
    dry_run=False,
    yes=False,
    progress=None,
    options=None,
    conf=None,
    backup_dir=None,
    previous=None,
    target_version=None,
    how="source",
    source=None,
):
    """The `ctx` every hook_<name>(ctx) gets (docs/plugins.md): the `core` object, `root` (a staged tree for tests and packaging; empty for the real
    system), `dry_run`, `yes`, `progress(event)` (the --progress json stream), `options` (the part's own installer choices), `conf` (the settings),
    `backup_dir`, `previous` (what the state record says about this part, or None), `target_version`, `how` (`source`, `package` or `immutable`: how THIS
    run installs) and `source` (the bundle's directory when the run is from a bundle, else None)."""
    return SimpleNamespace(
        core=core or make_core(),
        root=root,
        dry_run=dry_run,
        yes=yes,
        progress=progress or (lambda event: None),
        options=dict(options or {}),
        conf=dict(conf or {}),
        backup_dir=backup_dir,
        previous=previous,
        target_version=target_version or __version__,
        how=how,
        source=source,
    )
