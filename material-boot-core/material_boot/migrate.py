"""Migration steps: what an update does to the files that belong to the user (settings), so a new version never needs the user to redo anything. stdlib only.

A step is small, **idempotent** (running it twice changes nothing the second time) and says what it would do (`plan`) before doing it (`apply`).
`run` backs up every file a step says it touches, restores them all when a step fails, and reports each step. Used by the installer and, through it,
by the packages' scriptlets; `--dry-run` shows the plan and changes nothing.

    ctx = context(root="", backup=Path(...))     # root "" is the real system
    results = run(ctx, steps_for("0.7.1", "1.0.0"))
"""

import os
import re
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

# the name of the module is kept as it was in material-grub, so the bodies below are the original ones (only version_tuple is used)
from . import state as mgdetect  # noqa: E402


class Step:
    """since: the first version that needs this step (an install older than it runs it). Subclasses fill in touches/plan/apply."""

    id = "step"
    since = "0.0.0"
    title = ""

    def touches(self, ctx):
        return []

    def plan(self, ctx):
        """Sentences for what would change now; empty when there is nothing to do."""
        return []

    def apply(self, ctx):
        raise NotImplementedError


class ConfSamples(Step):
    """1.0.0: the Plymouth options appear in /etc/material-grub.conf as commented samples. Existing lines, values and comments are never touched."""

    id = "conf-samples"
    since = "1.0.0"
    title = "add the new options to /etc/material-grub.conf as commented samples"
    SAMPLES = (
        ("PLYMOUTH", "on", "the Plymouth boot splash, when the optional material-plymouth part is installed (on|off)"),
        ("PLYMOUTH_BAR", "indeterminate", "its wavy progress bar (indeterminate|progress)"),
        ("PLYMOUTH_MOTION", "full", "its animation level (full|calm|off)"),
    )

    def path(self, ctx):
        return ctx.root_path / "etc/material-grub.conf"

    def missing(self, ctx):
        p = self.path(ctx)
        if not p.is_file():
            return []  # no file: the installer writes the shipped one, which has them
        text = p.read_text(errors="replace")
        return [s for s in self.SAMPLES if not re.search(rf"(?m)^\s*#?\s*{s[0]}\s*=", text)]

    def touches(self, ctx):
        return [self.path(ctx)] if self.missing(ctx) else []

    def plan(self, ctx):
        return [f"add #{k}={v} to {self.path(ctx)}" for k, v, _ in self.missing(ctx)]

    def apply(self, ctx):
        todo = self.missing(ctx)
        if not todo:
            return
        p = self.path(ctx)
        text = p.read_text(errors="replace")
        if not text.endswith("\n"):
            text += "\n"
        text += "".join(f"# {k}={v}   {doc}\n#{k}={v}\n" for k, v, doc in todo)
        tmp = p.with_name(p.name + ".new")
        tmp.write_text(text)
        os.chmod(tmp, p.stat().st_mode & 0o7777)
        os.replace(tmp, p)


STEPS = [ConfSamples()]


def context(root="", backup=None, steps=None):
    return SimpleNamespace(root=root, root_path=Path(root or "/"), backup=Path(backup) if backup else None, steps=steps)


def steps_for(installed, target, steps=None):
    """The steps an install of version `installed` (None: unknown, so every step up to `target` is checked) needs to reach `target`. Steps are idempotent, so
    running one that was not needed does nothing."""
    lo = mgdetect.version_tuple(installed) if installed else (0,)
    hi = mgdetect.version_tuple(target)
    return [s for s in (STEPS if steps is None else steps) if lo < mgdetect.version_tuple(s.since) <= hi]


def plan(ctx, steps):
    """[(step, [sentences])] for the steps that have something to do."""
    out = []
    for s in steps:
        p = s.plan(ctx)
        if p:
            out.append((s, p))
    return out


def backup_dir(root, installed, target, now=None):
    stamp = now or time.strftime("%Y%m%d-%H%M%S")
    base = Path(root) / "var/backups/material-grub" if root else Path("/var/backups/material-grub")
    return base / f"upgrade-{installed or 'unknown'}-to-{target}-{stamp}"


def _rel(ctx, p):
    return Path(p).relative_to(ctx.root_path)


def run(ctx, steps, emit=None):
    """Run the steps in order. Returns a list of (step, status, detail) with status 'done', 'skipped' (nothing to do) or 'failed'.
    A failing step restores every file the steps touched so far from the backup and stops; the steps after it are not run."""
    emit = emit or (lambda s: None)
    results, saved = [], {}
    for s in steps:
        todo = s.plan(ctx)
        if not todo:
            results.append((s, "skipped", ""))
            continue
        for p in s.touches(ctx):
            p = Path(p)
            if p not in saved and ctx.backup is not None:
                dst = ctx.backup / _rel(ctx, p)
                if p.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dst)
                    saved[p] = dst
                else:
                    saved[p] = None  # did not exist: a failure removes what the step created
        try:
            emit(f"{s.title}")
            s.apply(ctx)
            results.append((s, "done", "; ".join(todo)))
        except Exception as e:
            for p, dst in saved.items():
                try:
                    if dst is None:
                        p.unlink()
                    else:
                        shutil.copy2(dst, p)
                except OSError:
                    pass
            results.append(
                (
                    s,
                    "failed",
                    f"{type(e).__name__}: {e} (the files this step and the earlier ones touched were put back)",
                )
            )
            break
    return results
