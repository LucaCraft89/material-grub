"""Safety net for rewriting grub.cfg (stdlib only): validate the result, roll back on failure, tell the user.

Used by cmd_postprocess (the installer, `material-boot grub apply`, the systemd path unit and the immutable path).
  check_script(cfg)         structural check with the scanner + grub-script-check when available
  theme_problems(theme)     what is missing from a theme directory
  guarded(cfg, steps, ...)  snapshot cfg, run the steps, validate, restore the snapshot if anything is wrong
  report_failure(...)       a box in the terminal, the journal (logger), `wall` without a terminal, and last-error for `doctor`
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import grubscript

STATE_DIR = Path("/var/lib/material-grub")
LAST_ERROR = "last-error"


def state_dir():
    """/var/lib/material-grub; $MATERIAL_STATE_DIR moves it (tests)."""
    return Path(os.environ.get("MATERIAL_STATE_DIR", str(STATE_DIR)))


def sha256_file(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- validation


def script_checker():
    """The grub-script-check binary ($MG_SCRIPT_CHECK overrides it for tests); None when GRUB's tools are not installed."""
    forced = os.environ.get("MG_SCRIPT_CHECK")
    if forced is not None:
        return forced or None
    for name in ("grub2-script-check", "grub-script-check"):
        found = shutil.which(name)
        if found:
            return found
    return None


def structure_problems(text):
    """Problems the scanner can see without GRUB: a block that never closes, a `}` with no `{`."""
    problems = []
    sc = grubscript.scan(text)
    for e in sc.entries:
        if e.close_brace is None:
            problems.append(f"{e.word} {e.title!r} (line {e.line + 1}) is never closed")
    depth = 0
    for t in sc.tokens:
        if t.kind == "op" and t.text == "{":
            depth += 1
        elif t.kind == "op" and t.text == "}":
            depth -= 1
            if depth < 0:
                problems.append(f"a `}}` without a matching `{{` (line {t.line + 1})")
                depth = 0
    if depth > 0:
        problems.append(f"{depth} block(s) are never closed")
    return problems


def check_script(cfg):
    """(ok, messages). The structural check always runs; grub-script-check runs when it is installed."""
    cfg = Path(cfg)
    problems = structure_problems(cfg.read_text(errors="replace"))
    checker = script_checker()
    if checker:
        r = subprocess.run([checker, str(cfg)], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append(
                f"{os.path.basename(checker)} failed: " + (r.stderr or r.stdout).strip().replace("\n", " | ")
            )
    return not problems, problems


def theme_problems(theme, pkg=None):
    """Messages for everything missing from an assembled theme directory (empty list: complete)."""
    theme = Path(theme)
    if not theme.is_dir():
        return [f"{theme} does not exist"]
    out = [
        f"{n} is missing in {theme}" for n in ("theme.txt", "MG-Label.pf2", "MG-Raw.pf2") if not (theme / n).is_file()
    ]
    icons = theme / "icons"
    if not icons.is_dir():
        out.append(f"{icons} does not exist")
    elif pkg is not None and (Path(pkg) / "classes.json").is_file():
        classes = json.loads((Path(pkg) / "classes.json").read_text())
        gone = [n for names in classes.values() for n in names if not (icons / f"{n}.png").is_file()]
        if gone:
            out.append(f"{len(gone)} class scene(s) missing in {icons} (first: {gone[0]}.png)")
    elif not any(icons.glob("*.png")):
        out.append(f"{icons} holds no scenes")
    return out


# ---------------------------------------------------------------- notification


def box(title, lines):
    width = max([len(title)] + [len(l) for l in lines]) + 2
    bar = "+" + "-" * (width + 2) + "+"
    rows = [bar, f"| {title.ljust(width)} |", bar] + [f"| {l.ljust(width)} |" for l in lines] + [bar]
    return "\n".join(rows)


def write_last_error(reason, details, input_sha=None):
    d = state_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / LAST_ERROR).write_text(
            json.dumps(
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S%z"),
                    "reason": reason,
                    "details": details,
                    "input_sha256": input_sha,
                },
                indent=1,
            )
            + "\n"
        )
    except OSError:
        pass


def read_last_error():
    try:
        return json.loads((state_dir() / LAST_ERROR).read_text())
    except (OSError, ValueError):
        return None


def clear_last_error():
    try:
        (state_dir() / LAST_ERROR).unlink()
    except OSError:
        pass


def report_failure(reason, details, input_sha=None, interactive=None):
    """Tell the user a rollback happened. Always: terminal box on stderr, journal, last-error. Without a terminal: also wall."""
    if interactive is None:
        interactive = sys.stderr.isatty()
    lines = list(details) + [
        "",
        "Your GRUB menu was left as it was before this run (no change was kept).",
        "Run `material-boot grub doctor` for the state of the setup.",
    ]
    text = box("material-grub: " + reason, lines)
    print(text, file=sys.stderr)
    short = reason + ": " + "; ".join(details)
    if shutil.which("logger"):
        subprocess.run(["logger", "-t", "material-grub", "-p", "user.err", short], check=False)
    if not interactive and shutil.which("wall"):
        subprocess.run(["wall"], input=text + "\n", text=True, check=False)
    write_last_error(reason, details, input_sha)


# ---------------------------------------------------------------- the guard


def restore(cfg, data):
    """Put the snapshot back (same mode, atomic replace)."""
    cfg = Path(cfg)
    mode = cfg.stat().st_mode if cfg.exists() else 0o644
    tmp = cfg.with_name(cfg.name + ".material-rollback")
    tmp.write_bytes(data)
    os.chmod(tmp, mode & 0o7777)
    os.replace(tmp, cfg)


def guarded(cfg, steps, theme=None, pkg=None, force=False, interactive=None):
    """Run `steps` (callables returning True on success) that rewrite `cfg`; keep the result only if it is valid.
    Returns "ok", "skipped" (this exact grub.cfg failed before and nothing changed since) or "rolled-back"."""
    cfg = Path(cfg)
    snapshot = cfg.read_bytes()
    sha = hashlib.sha256(snapshot).hexdigest()
    last = read_last_error()
    if last and last.get("input_sha256") == sha and not force:
        print(
            f"material-grub: skipping {cfg}: it already failed validation (see {state_dir() / LAST_ERROR}); run `sudo material-boot grub apply` to retry",
            file=sys.stderr,
        )
        return "skipped"
    problems = []
    try:
        for step in steps:
            if not step():
                problems.append(f"a step failed ({getattr(step, '__name__', 'step')})")
                break
    except Exception as e:  # a crash in a step is a failure like any other
        problems.append(f"{type(e).__name__}: {e}")
    if not problems:
        ok, msgs = check_script(cfg)
        if not ok:
            problems += [f"{cfg} no longer passes the GRUB script check"] + msgs
        before = len(grubscript.scan(snapshot.decode(errors="replace")).entries)
        after = len(grubscript.scan(cfg.read_text(errors="replace")).entries)
        if ok and after < before:
            problems.append(f"entries were lost: {before} before, {after} after")
    if not problems and theme is not None:
        problems += theme_problems(theme, pkg)
    if problems:
        restore(cfg, snapshot)
        report_failure("rolled back, GRUB menu unchanged", problems, sha, interactive)
        return "rolled-back"
    clear_last_error()
    return "ok"
