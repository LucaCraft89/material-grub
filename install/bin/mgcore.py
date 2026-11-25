"""Finds material-boot-core (the code Material GRUB shares with the other Material Boot parts) and puts it on sys.path. stdlib only.

Importing this module is enough: `import mgcore` before `import material_boot`. Where it looks, in this order:
  $MATERIAL_LIB                         explicit: only this one, no fallback (a wrong value is an error, not a surprise)
  /usr/share/material-boot/lib          the core's package, or a source install of the core
  /usr/local/share/material-boot/lib
  /var/lib/material-boot/lib            reserved for immutable systems (not used by the core's installer yet)
  <an ancestor of this file>/material-boot-core    a checkout: next to material-grub's, or inside it (what CI does)

The installed tools refuse to start without it, with a message that says what to install: they cannot do anything useful without the shared code.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_CORE = (1, 0, 0)  # the oldest core this material-grub works with
CORE_API = 2  # the plugin API this material-grub speaks (docs/plugins.md of the core)
SYSTEM = ("/usr/share/material-boot/lib", "/usr/local/share/material-boot/lib", "/var/lib/material-boot/lib")


def _is_core(p):
    return (Path(p) / "material_boot" / "__init__.py").is_file()


def candidates():
    env = os.environ.get("MATERIAL_LIB")
    if env:
        return [Path(env)]
    found = [Path(p) for p in SYSTEM]
    for anc in list(HERE.parents)[:5]:  # a checkout: material-boot-core next to material-grub's, or inside it
        found.append(anc / "material-boot-core")
    return found


def find():
    """The directory that holds the material_boot package, or None."""
    return next((p for p in candidates() if _is_core(p)), None)


def system():
    """The core as an installed system finds it (not through $MATERIAL_LIB or a checkout), or None."""
    return next((Path(p) for p in SYSTEM if _is_core(p)), None)


def _version_tuple(v):
    out = []
    for part in str(v or "").split("."):
        digits = "".join(c for c in part if c.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out) or (0,)


def ensure():
    """Put the core on sys.path (once) and check that it is new enough. Exits with a message when it is missing or too old."""
    if "material_boot" in sys.modules:
        return Path(sys.modules["material_boot"].__file__).resolve().parent.parent
    where = find()
    if where is None:
        looked = ", ".join(str(p) for p in candidates())
        sys.exit(
            "material-grub: material-boot-core is not installed (looked in: " + looked + ").\n"
            "It holds the code Material GRUB shares with the other Material Boot parts. Install the package `material-boot-core`,\n"
            "or run the installer from the Material Boot bundle; from a checkout, put material-boot-core next to it or set MATERIAL_LIB."
        )
    if str(where) not in sys.path:
        sys.path.insert(0, str(where))
    import material_boot

    if _version_tuple(material_boot.__version__) < MIN_CORE or getattr(material_boot, "CORE_API", 0) != CORE_API:
        sys.exit(
            f"material-grub: material-boot-core {material_boot.__version__} (plugin API {getattr(material_boot, 'CORE_API', '?')}) at {where} "
            f"does not fit: this needs {'.'.join(map(str, MIN_CORE))} or newer with plugin API {CORE_API}. Update whichever of the two is older."
        )
    return where


ensure()
