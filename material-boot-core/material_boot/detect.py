"""Is a part already installed here, which version, how, and what is the right thing to do about it? stdlib only.

The generic half of material-grub's mgdetect.py: what is found is told by the part (its `hook_detect(ctx)`, and the state record); what to say about it and
what to allow is the same for every part, so the installer, the packages' scriptlets and `doctor` never disagree. The wording is the original's, with the
product name and the package taken from the part's manifest instead of "Material GRUB" and `material-grub`.

  finding(result, target)               -> Finding, from what hook_detect returned (a dict) against the version about to be installed
  notice(finding, target, product)      -> the lines the user is shown before anything changes
  policy(finding, target, how, ...)     -> (ok, message): refuse a downgrade, or a source install over a package's files
  adopting(finding, how)                -> a package install takes over a source install

`hook_detect` returns a dict; every key is optional: found (bool), version, how (`package:rpm` | `package:deb` | `package:pacman` | `source` | `immutable` |
`unknown`), layout (`normal` | `immutable`), missing (pieces of an install that are not there), details (sentences for the notice: style, GUI, ...),
legacy (found by its files, no state record yet), old_names (leftovers of older layouts that will be removed).
"""

from .state import version_tuple

HOW_TEXT = {
    "package:rpm": "an rpm package",
    "package:deb": "a deb package",
    "package:pacman": "a pacman package",
    "source": "a source install",
    "immutable": "a source install, immutable layout",
    "package:unknown": "a package",
    "unknown": "an install of unknown origin",
}


class Finding:
    """What is installed. kind: none | unknown | older | same | newer (against the version being installed)."""

    def __init__(self):
        self.kind = "none"
        self.version = None
        self.layout = "normal"
        self.how = "unknown"
        self.missing = []
        self.details = []
        self.legacy = False
        self.old_names = []

    def as_dict(self):
        return {
            "kind": self.kind,
            "version": self.version,
            "layout": self.layout,
            "how": self.how,
            "missing": self.missing,
            "details": self.details,
            "legacy": self.legacy,
        }


def finding(result, target=None):
    """A Finding from the dict a part's hook_detect returned (None or {}: nothing is installed). `target` is the version about to be installed (None: the
    kind is only none or unknown)."""
    f = Finding()
    r = result if isinstance(result, dict) else {}
    if not r.get("found"):
        return f
    f.kind = "unknown"
    f.version = r.get("version") or None
    f.layout = r.get("layout") if r.get("layout") in ("normal", "immutable") else "normal"
    f.how = r.get("how") or "unknown"
    f.missing = [str(x) for x in r.get("missing") or []]
    f.details = [str(x) for x in r.get("details") or []]
    f.legacy = bool(r.get("legacy"))
    f.old_names = [str(x) for x in r.get("old_names") or []]
    if f.version and target:
        a, b = version_tuple(f.version), version_tuple(target)
        f.kind = "same" if a == b else "older" if a < b else "newer"
    return f


def notice(f, target, product):
    """The lines shown before anything is changed. Empty when there is no install."""
    if f.kind == "none":
        return []
    head = f"Found {product} {f.version or '(unknown version)'}, {HOW_TEXT.get(f.how, f.how)}"
    if f.layout == "immutable" and f.how != "immutable":
        head += ", immutable layout"
    out = [head + ("" if not f.details else ": " + "; ".join(f.details)) + "."]
    if f.kind == "older":
        out.append(
            f"This will update it to {target}. Your settings (options, colours, entries, icons, presets) are kept."
        )
    elif f.kind == "same":
        out.append(f"It is the same version as this one ({target}): it will be installed again, keeping your settings.")
    elif f.kind == "newer":
        out.append(f"That is NEWER than this one ({target}).")
    else:
        out.append("Its version cannot be read; it will be replaced by " + target + ", keeping your settings.")
    if f.missing and f.kind != "newer":
        out.append("Pieces that are missing and will be put back: " + ", ".join(f.missing) + ".")
    if f.legacy:
        out.append("It has no state record yet (it was installed by an older version): one is written now.")
    if f.old_names:
        out.append("Old command names will be removed: " + ", ".join("/" + n for n in f.old_names) + ".")
    return out


def policy(f, target, how, product, package, force=False):
    """(ok, message). `how` is how THIS run installs: 'package' (a package scriptlet) or 'source'."""
    if f.kind == "none":
        return True, ""
    if f.kind == "newer" and not force:
        return False, (
            f"{product} {f.version} is installed and this is {target}. Installing an older version over a newer one can leave "
            "settings that it does not understand (newer options, presets, overrides). Update to the newer version instead, "
            "or run with --force if you really mean it."
        )
    if how == "source" and f.how.startswith("package:") and not force:
        cmd = {
            "package:rpm": f"sudo dnf upgrade {package}   (or the package manager you installed it with)",
            "package:deb": f"sudo apt install --only-upgrade {package}",
            "package:pacman": f"sudo pacman -Syu {package}",
        }.get(f.how, "update it with the package manager you installed it with")
        return False, (
            f"{product} is installed from {HOW_TEXT.get(f.how, 'a package')}, and a source install would fight your package manager over the same files. "
            f"Update it the usual way:\n    {cmd}\nor remove the package first. --force overrides this."
        )
    return True, ""


def adopting(f, how):
    """True when a package install takes over a source install (its files are replaced, settings kept)."""
    return how == "package" and f.kind != "none" and f.how in ("source", "immutable", "unknown")
