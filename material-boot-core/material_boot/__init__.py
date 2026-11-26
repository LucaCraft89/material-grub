"""material-boot-core: the code Material GRUB and Material Plymouth share, and the `material-boot` command (see docs/architecture.md).

This is the skeleton: it carries the version and the plugin API number, nothing else yet. The shared modules move in with the next pull requests.
"""

from pathlib import Path

# The contract between the core and the parts (material-grub, material-plymouth, ...). API 1 was the first draft inside material-grub, never released;
# API 2 is the one the parts are written against: a manifest lists the part's commands, menu entries, installer options and hooks.
# A part whose manifest says another number is not run, and `doctor` says which of the two to update.
CORE_API = 2


def _version():
    here = Path(__file__).resolve().parent
    for p in (here / "VERSION", here.parent / "VERSION"):  # installed next to the package, or in a checkout
        try:
            return p.read_text().strip()
        except OSError:
            continue
    return "0+unknown"


__version__ = _version()
