"""The unified installer: `material-boot core install` (docs/installer.md). stdlib only.

It knows nothing about GRUB, Plymouth or any part. A part brings its own steps as hooks (docs/plugins.md); this module chooses the parts, shows one notice
for what is already there, writes the shared look once, runs the migrations, runs the parts in dependency order, and records the state.

  parse_args(argv, parts)    -> Options, errors     the generic options, the shared look, and the options each part declares (routed by name)
  select(parts, installed, o)-> ordered parts, notes, errors   which parts, with `needs` followed, in dependency order
  Installer(...).run()       -> exit status        the run of docs/installer.md (or the uninstall)
"""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from . import __version__, coreinstall, detect, migrate, plugins, state
from . import conf as mgconf
from . import overrides as mgoverrides
from . import seeds as mgseeds

# options that take a value / that are flags, for the parts of the installer itself
FLAG_ATTR = {
    "--dry-run": "dry_run",
    "--force": "force",
    "--from-package": "from_package",
    "--uninstall": "uninstall",
    "--keep-build": "keep_build",
    "-h": "help",
    "--help": "help",
}
LOOK_FLAG = {
    "--cookie": ("COOKIE", "on"),
    "--no-cookie": ("COOKIE", "off"),
    "--logo": ("LOGO", "on"),
    "--no-logo": ("LOGO", "off"),
    "--hints": ("HINTS", "on"),
    "--no-hints": ("HINTS", "off"),
}


# ---------------------------------------------------------------- options
def parse_args(argv, parts=()):
    """-> (Options, errors). `parts` are the parts that can be chosen (usable or not); their declared install options are accepted as `--<part>-<name>` and,
    when exactly one chosen part declares the name, as `--<name>`. A bare option that two parts declare is an error that names the prefix."""
    o = SimpleNamespace(
        with_=[],
        without=[],
        only=None,
        yes=False,
        dry_run=False,
        force=False,
        from_package=False,
        uninstall=False,
        keep_build=False,
        help=False,
        root="",
        bundle=None,
        json=False,
        look={},  # conf key -> value, from the shared-look options
        seed=None,
        seed_mode=None,
        raw_part=[],  # [(token, value or None)] options that are not the installer's own, routed by route_part_options once the parts are chosen
        part_opts={},
    )
    errors = []
    declared = {}  # option name -> {part: takes}
    for p in parts:
        for opt in p.options:
            declared.setdefault(opt["name"], {})[p.name] = opt["takes"]
    prefixed = {f"{p.name}-{opt['name']}": (p.name, opt["name"], opt["takes"]) for p in parts for opt in p.options}
    i, argv = 0, list(argv)

    def value(flag):
        nonlocal i
        if i + 1 >= len(argv) or (argv[i + 1].startswith("-") and argv[i + 1] != "-"):
            errors.append(f"{flag} needs a value")
            return None
        i += 1
        return argv[i]

    while i < len(argv):
        a = argv[i]
        flag, eq, inline = a.partition("=") if a.startswith("--") else (a, "", "")
        get = (lambda f=flag, v=inline: v) if eq else (lambda f=flag: value(f))
        if flag in ("--with", "--without"):
            v = get()
            if v:
                (o.with_ if flag == "--with" else o.without).extend(x for x in v.split(",") if x)
        elif flag == "--only":
            o.only = get()
        elif flag in ("--root", "--bundle"):
            setattr(o, flag[2:], get())
        elif flag == "--progress":
            if get() == "json":
                o.json = True
            else:
                errors.append("--progress only knows json")
        elif flag in ("--yes", "-y"):
            o.yes = True
        elif flag in FLAG_ATTR:
            setattr(o, FLAG_ATTR[flag], True)
        elif flag == "--style":
            v = get()
            if v in mgconf.CONF_CHOICES["STYLE"]:
                o.look["STYLE"] = v
            else:
                errors.append("--style must be one of " + ", ".join(mgconf.CONF_CHOICES["STYLE"]))
        elif flag == "--scheme":
            v = get()
            if v in mgconf.CONF_CHOICES["SCHEME"]:
                o.look["SCHEME"] = v
            else:
                errors.append("--scheme must be light or dark")
        elif flag == "--seed":
            v = get()
            if v and mgseeds.HEX.match(v):
                o.seed = v.upper()
            else:
                errors.append("--seed must look like #RRGGBB")
        elif flag == "--seed-mode":
            v = get()
            if v in ("multi", "single"):
                o.seed_mode = v
            else:
                errors.append("--seed-mode must be multi or single")
        elif a in LOOK_FLAG:
            k, v = LOOK_FLAG[a]
            o.look[k] = v
        elif flag.startswith("--") and flag[2:] in prefixed:
            part, name, takes = prefixed[flag[2:]]
            o.part_opts.setdefault(part, {})[name] = get() if takes == "value" else True
        elif flag.startswith("--") and flag[2:] in declared:
            takes = set(declared[flag[2:]].values())
            o.raw_part.append((flag[2:], get() if "value" in takes else None))
        else:
            errors.append(f"unknown option {a}")
        i += 1
    if o.seed and not o.seed_mode:
        o.seed_mode = "single"
    return o, errors


def route_part_options(o, chosen):
    """Hand the bare options to the chosen part that declares them. Returns errors (an option nobody chosen declares, or two chosen parts do)."""
    errors = []
    for name, val in o.raw_part:
        owners = [p for p in chosen if any(x["name"] == name for x in p.options)]
        if len(owners) == 1:
            o.part_opts.setdefault(owners[0].name, {})[name] = val if val is not None else True
        elif not owners:
            errors.append(f"--{name} belongs to a part that is not being installed")
        else:
            errors.append(
                f"--{name} is declared by more than one part ({', '.join(p.name for p in owners)}): write --{owners[0].name}-{name}"
            )
    return errors


# ---------------------------------------------------------------- which parts
def select(parts, installed, o):
    """-> (ordered usable parts, notes, errors). `parts`: every part that can be installed (from the bundle and from the plugin directories), `installed`:
    names of the parts that are installed now. The set is `--only`, else the installed parts (an update keeps what is there), or, on a fresh system, the
    parts whose manifest says install.default (unless `--with` chose some); plus `--with`, minus `--without`; `needs` is followed."""
    by = {p.name: p for p in parts}
    errors, notes = [], []

    def needs_of(p):
        # every part needs the core (its library, its data, its command), and the core is installed first
        return p.needs if p.name == "core" or "core" not in by else ["core", *p.needs]

    if "core" in o.without:
        errors.append("the core cannot be left out: every part needs it (--without core does not exist)")
    for n in [*o.with_, *o.without, *([o.only] if o.only else [])]:
        if n not in by:
            errors.append(f"there is no part called '{n}' (known: {', '.join(sorted(by)) or 'none'})")
    if errors:
        return [], notes, errors
    if o.only:
        chosen = {o.only}
    else:
        # defaults only make sense for an install on a fresh system: removing "the defaults" would remove things nobody asked about
        fresh = set() if o.uninstall or o.with_ else {p.name for p in parts if p.default and p.problem is None}
        chosen = set(installed) if installed else fresh
        chosen |= set(o.with_)
        chosen -= set(o.without)
        if o.uninstall and "core" not in o.with_:
            chosen.discard(
                "core"
            )  # the core goes last and only on request (--only core): the parts are what was asked about
    for n in sorted(chosen):
        if by[n].problem:
            errors.append(f"cannot use '{n}': {by[n].problem}")
    # follow `needs`: add what is missing, unless it was excluded
    todo = sorted(chosen)
    while todo:
        n = todo.pop()
        for need in needs_of(by[n]):
            if need in chosen or need in installed:
                continue
            if need not in by:
                errors.append(f"{n} needs the {need} part, which is not available")
            elif need in o.without:
                errors.append(f"{n} needs the {need} part, which you excluded with --without")
            else:
                chosen.add(need)
                todo.append(need)
                notes.append(f"{need} is added because {n} needs it")
    if errors:
        return [], notes, errors
    ordered, seen = [], set()

    def visit(n):
        if n in seen or n not in chosen:
            return
        seen.add(n)
        for need in sorted(needs_of(by[n])):
            visit(need)
        ordered.append(by[n])

    for n in sorted(chosen):
        visit(n)
    return ordered, notes, errors


# ---------------------------------------------------------------- the run
def system_layout(root=""):
    """`immutable` on an ostree/bootc system (or when the installer wrote MG_IMMUTABLE=1), else `normal`."""
    r = Path(root or "/")
    try:
        if (r / "run/ostree-booted").exists() or "MG_IMMUTABLE=1" in (r / "var/lib/material-grub/env").read_text(
            errors="ignore"
        ):
            return "immutable"
    except OSError:
        pass
    return "normal"


class Installer:
    """One run. `parts` are the chosen parts in dependency order; `say(text)` prints; `ask(prompt)` reads an answer; `emit` receives the events of the
    --progress json stream (called as emit(event, **fields))."""

    def __init__(self, o, parts, say=print, ask=input, emit=None, core=None, how=None):
        self.o, self.parts = o, parts
        self.say_, self.ask, self.emit_ = say, ask, emit
        self.core = core or plugins.make_core(say=say)
        self.root = o.root or ""
        self.layout = system_layout(self.root)
        self.how = how or ("package" if o.from_package else "immutable" if self.layout == "immutable" else "source")
        self.t0 = time.time()
        self.results = []  # (part name, "installed" | "failed" | "removed" | "unchanged", detail)

    # -- output
    def emit(self, event, **kw):
        if self.emit_:
            self.emit_(event, t=round(time.time() - self.t0, 1), **kw)

    def say(self, text="", event="info"):
        self.say_(text)
        self.emit(event, text=text)

    def step(self, text):
        self.say_(f"\n== {text}")
        self.emit("step", text=text)

    # -- paths
    def conf_path(self):
        return Path(self.root) / "etc/material-grub.conf" if self.root else self.core.conf_path()

    def overrides_path(self):
        return Path(self.root) / "etc/material-grub/overrides.json" if self.root else mgoverrides.path()

    def ctx(self, part=None, dry=None):
        o = self.o
        return plugins.make_ctx(
            core=self.core,
            root=self.root,
            dry_run=o.dry_run if dry is None else dry,
            yes=o.yes or o.json or o.from_package,
            progress=lambda ev, n=part.name if part else None: self.emit(
                ev.get("event", "info") if isinstance(ev, dict) else "info",
                part=n,
                **{k: v for k, v in (ev if isinstance(ev, dict) else {"text": str(ev)}).items() if k != "event"},
            ),
            options=(o.part_opts.get(part.name, {}) if part else {}),
            conf=mgconf.load_conf(str(self.conf_path())),
            backup_dir=getattr(self, "backup", None),
            previous=(state.read(self.root) or {}).get("parts", {}).get(part.name) if part else None,
            target_version=part.version if part else __version__,
            how=self.how,
            source=self.o.bundle,
        )

    # -- the stages
    def check_layouts(self):
        bad = [p for p in self.parts if p.layouts and self.layout not in p.layouts]
        for p in bad:
            self.say(
                f"{p.title} is not available on a system with the {self.layout} layout (it supports: {', '.join(p.layouts)}).",
                "error",
            )
        return not bad

    def detect_all(self):
        """-> {part name: Finding}. A part without a detect hook is found through the state record only."""
        out, st = {}, (state.read(self.root) or {}).get("parts", {})
        for p in self.parts:
            res = None
            if "detect" in p.hooks:
                r = plugins.call_hook(p, "detect", self.ctx(p, dry=True))
                res = r.value if r.ok else None
                if not r.ok:
                    self.say(r.error, "warn")
            if res is None and p.name in st:
                e = st[p.name]
                res = {"found": True, "version": e.get("version") if isinstance(e, dict) else e}
            out[p.name] = detect.finding(res, p.version)
        return out

    def existing(self):
        """Print one notice for everything that is already there, apply the policy, ask. Returns True to go on."""
        found = self.detect_all()
        if all(f.kind == "none" for f in found.values()):
            return True
        self.step("Existing install")
        for p in self.parts:
            f = found[p.name]
            lines = detect.notice(f, p.version, p.title)
            for ln in lines:
                self.say(ln)
            ok, msg = detect.policy(
                f, p.version, "package" if self.o.from_package else "source", p.title, p.package or p.name, self.o.force
            )
            if not ok:
                self.say(msg, "error")
                return False
            if detect.adopting(f, "package" if self.o.from_package else "source"):
                self.say(f"The package takes over the existing {p.title} install; your settings are kept.")
        self.emit(
            "existing_install",
            msg="; ".join(ln for p in self.parts for ln in detect.notice(found[p.name], p.version, p.title)),
        )
        if self.o.yes or self.o.json or self.o.from_package or self.o.dry_run:
            return True
        try:
            ans = self.ask("Continue? [Y/n] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans in ("", "y", "yes"):
            return True
        self.say("nothing changed")
        return False

    def write_look(self):
        """The shared look, once, before any part runs: the conf keys and the seed colour."""
        o = self.o
        if not (o.look or o.seed_mode):
            return True
        self.step("The look (shared by every part)")
        for k, v in o.look.items():
            self.say(f"  {k}={v}")
        if o.seed_mode:
            self.say(
                f"  colours: {'one seed colour ' + o.seed if o.seed_mode == 'single' and o.seed else 'every entry its own colour' if o.seed_mode == 'multi' else 'one seed colour'}"
            )
        if o.dry_run:
            return True
        try:
            if o.look:
                self.conf_path().parent.mkdir(parents=True, exist_ok=True)
                mgconf.write_conf(self.conf_path(), o.look)
            if o.seed_mode:
                p = self.overrides_path()
                ov, _ = mgoverrides.load(p)
                ov["seed"] = {"mode": o.seed_mode, "color": o.seed or ov["seed"]["color"]}
                mgoverrides.save(ov, p)
        except (OSError, ValueError) as e:
            self.say(f"cannot write the look: {e}", "error")
            return False
        return True

    def migrations(self):
        old = (state.read(self.root) or {}).get("version")
        steps = migrate.steps_for(old, __version__)
        stamp = migrate.backup_dir(self.root, old, __version__)
        self.backup = stamp
        mc = migrate.context(root=self.root, backup=stamp)
        plan = migrate.plan(mc, steps)
        if plan:
            self.step("Migrations" + (" (dry run)" if self.o.dry_run else ""))
            for s, sentences in plan:
                for t in sentences:
                    self.say(f"  {s.title}: {t}")
        if self.o.dry_run or not plan:
            return True
        for s, status, detail in migrate.run(mc, steps, emit=lambda t: self.emit("step", text=t)):
            if status == "failed":
                self.say(f"migration '{s.title}' failed: {detail}", "error")
                return False
        for p in self.parts:
            if "migrate" in p.hooks:
                r = plugins.call_hook(p, "migrate", self.ctx(p))
                if not r.ok:
                    self.say(r.error, "error")
                    return False
        return True

    def record(self, part):
        st = state.read(self.root) or {}
        entry = (st.get("parts") or {}).get(part.name)
        new = dict(entry, version=part.version) if isinstance(entry, dict) else part.version
        state.record(self.root, __version__, self.how, self.layout, parts={part.name: new})

    def forget(self, part):
        st = state.read(self.root)
        if st and part.name in (st.get("parts") or {}):
            del st["parts"][part.name]
            state.write(self.root, st)

    def install(self):
        for idx, p in enumerate(self.parts):
            self.step(f"{p.title} {p.version}")
            r = plugins.call_hook(p, "install", self.ctx(p)) if "install" in p.hooks else None
            if r is None:
                self.say(f"{p.name} has no install step: nothing to do")
                self.results.append((p.name, "unchanged", "no install hook"))
                continue
            if not r.ok:
                self.say(r.error, "error")
                self.results.append((p.name, "failed", r.error))
                self.results += [(q.name, "not run", "") for q in self.parts[idx + 1 :]]
                return False
            value = r.value if isinstance(r.value, dict) else {}
            for n in value.get("notes", []):
                self.say(f"  {n}")
            if "verify" in p.hooks:
                v = plugins.call_hook(p, "verify", self.ctx(p))
                problems = v.value if v.ok and v.value else ([v.error] if not v.ok else [])
                if problems:
                    for t in problems:
                        self.say(f"  {t}", "error")
                    self.results.append((p.name, "failed", "; ".join(map(str, problems))))
                    self.results += [(q.name, "not run", "") for q in self.parts[idx + 1 :]]
                    return False
            self.record(p)
            self.results.append((p.name, "installed" if value.get("changed", True) else "unchanged", ""))
            self.emit("ok", text=f"{p.title} {p.version} installed", part=p.name)
        return True

    def uninstall(self):
        ok = True
        for p in reversed(self.parts):
            self.step(f"Removing {p.title}")
            if "uninstall" not in p.hooks:
                self.say(f"{p.name} has no uninstall step")
                self.results.append((p.name, "unchanged", "no uninstall hook"))
                continue
            r = plugins.call_hook(p, "uninstall", self.ctx(p))
            if not r.ok:
                self.say(r.error, "error")
                self.results.append((p.name, "failed", r.error))
                ok = False
                break
            self.forget(p)
            self.results.append((p.name, "removed", ""))
        return ok

    def plan(self):
        for p in self.parts:
            self.step(f"{p.title} {p.version}: what would change")
            if "plan" not in p.hooks:
                self.say("  (this part does not say what it would change)")
                continue
            r = plugins.call_hook(p, "plan", self.ctx(p, dry=True))
            if not r.ok:
                self.say(r.error, "error")
                return False
            for t in r.value or ["nothing"]:
                self.say(f"  {t}")
        return True

    def summary(self, ok):
        by = {}
        for name, status, _d in self.results:
            by.setdefault(status, []).append(name)
        parts = [f"{s}: {', '.join(n)}" for s, n in by.items()]
        self.say(
            "\n" + (". ".join(x.capitalize() for x in parts) + "." if parts else "Nothing to do."),
            "ok" if ok else "error",
        )
        if not ok and "failed" in by:
            self.say(
                "Parts that were installed stay installed; a failed part rolled itself back. Run again to retry the rest."
            )

    def run(self):
        o = self.o
        self.emit("step", text="Checking the system")
        if not self.check_layouts():
            return 1
        if o.uninstall:
            ok = self.uninstall()
            self.summary(ok)
            self.emit("done", ok=ok)
            return 0 if ok else 1
        if not self.existing():
            return 1
        if not self.write_look() or not self.migrations():
            return 1
        if o.dry_run:
            ok = self.plan()
            self.say("\nDry run: nothing was changed.")
            self.emit("done", ok=ok, dry_run=True)
            return 0 if ok else 1
        ok = self.install()
        self.summary(ok)
        self.emit("done", ok=ok)
        return 0 if ok else 1


# ---------------------------------------------------------------- the command
def available_parts(bundle=None):
    """Every part that can be installed: the bundle's (when there is one) and the installed ones; a bundle's record wins, it is the version to install."""
    found = {p.name: p for p in plugins.discover()}
    found["core"] = coreinstall.part()  # the core is a part like the others, and the first
    for p in plugins.discover_bundle(bundle) if bundle else []:
        found[p.name] = p
    return [found[k] for k in sorted(found)]


def usage():
    return (
        "usage: material-boot core install [--with PART]... [--without PART]... [--only PART] [--yes] [--dry-run] [--force] [--from-package]\n"
        "           [--root DIR] [--bundle DIR] [--progress json] [--uninstall]\n"
        "           [--style S] [--scheme dark|light] [--seed #RRGGBB] [--seed-mode multi|single] [--[no-]cookie] [--[no-]logo] [--[no-]hints]\n"
        "           [part options: --<part>-<name>, or --<name> when only one chosen part declares it]\n"
    )


def main(argv, say=print, ask=None):
    """`material-boot core install ...`. Returns the exit status."""
    if "--uninstall" in argv:
        sys.dont_write_bytecode = (
            True  # a removal must not leave new caches next to the files the package manager is about to delete
        )
    bundle = None
    for i, a in enumerate(argv):
        if a == "--bundle" and i + 1 < len(argv):
            bundle = argv[i + 1]
        elif a.startswith("--bundle="):
            bundle = a.split("=", 1)[1]
    bundle = bundle or os.environ.get("MATERIAL_BUNDLE")
    parts = available_parts(bundle)
    o, errors = parse_args(argv, parts)
    if o.help:
        say(
            usage()
            + "\nparts: "
            + (", ".join(p.name for p in parts) or "none")
            + "\n"
            + "".join(f"  --{p.name}-{x['name']:<16}{x['summary']}\n" for p in parts for x in p.options)
        )
        return 0
    # installed = a manifest in a plugin directory, or a part the state record knows (a half-removed part still counts: it has to be repaired or removed)
    installed = {p.name for p in plugins.discover()} | set((state.read(o.root) or {}).get("parts") or {})
    chosen, notes, serr = select(parts, installed, o)
    errors += serr
    if not errors:
        errors += route_part_options(o, chosen)
    if errors:
        for e in errors:
            say(f"material-boot: {e}")
        say(usage())
        return 2
    emit = None
    if o.json:

        def emit(event, **kw):
            sys.__stdout__.write(json.dumps({"event": event, **kw}) + "\n")
            sys.__stdout__.flush()

        say = lambda text="": None  # noqa: E731  (the events carry the text)
    inst = Installer(
        o, chosen, say=say, ask=ask or input, emit=emit
    )  # `input` is looked up now, so a test can replace it
    for n in notes:
        inst.say(n)
    return inst.run()
