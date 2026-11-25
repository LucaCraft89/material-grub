"""Material 3 colours for the installed tools and the GUI: a seed colour to the 14 roles the theme uses. stdlib only.

The colour science is `materialyoucolor` (the Python port of material-color-utilities; pure Python apart from its image quantizer, which is not used).
A copy of the pure part lives in material_boot/_vendor/materialyoucolor so the installed tools need no pip packages (material-grub's build keeps using
the pinned pip release and checks both give the same colours).

    scheme("#E95420", dark=True) -> {"primary": "#...", "onPrimary": ..., ...}   (the keys of ROLES)
"""

import sys
from pathlib import Path

try:
    import materialyoucolor  # noqa: F401  (a system or venv copy wins)
except ImportError:
    _vendor = Path(__file__).resolve().parent / "_vendor"  # the unmodified pure-Python copy shipped inside this package
    if (_vendor / "materialyoucolor").is_dir():
        sys.path.insert(0, str(_vendor))

from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors as M  # noqa: E402
from materialyoucolor.hct import Hct  # noqa: E402
from materialyoucolor.scheme.scheme_expressive import SchemeExpressive  # noqa: E402
from materialyoucolor.scheme.scheme_monochrome import SchemeMonochrome  # noqa: E402

ROLES = (
    "primary",
    "onPrimary",
    "primaryContainer",
    "onPrimaryContainer",
    "secondary",
    "secondaryContainer",
    "tertiary",
    "tertiaryContainer",
    "surface",
    "surfaceContainer",
    "surfaceContainerHigh",
    "onSurface",
    "onSurfaceVariant",
    "outline",
)


def argb(color):
    return 0xFF000000 | int(color.lstrip("#"), 16)


def hexs(a):
    return "#%06X" % (a & 0xFFFFFF)


def hct(color):
    """(hue, chroma, tone) of '#RRGGBB'."""
    h = Hct.from_int(argb(color))
    return h.hue, h.chroma, h.tone


def scheme(seed, dark=True):
    """The 14 roles as '#RRGGBB' (Expressive). A (near) grey seed gives a truly grey scheme, like scripts/palettes.py."""
    h = Hct.from_int(argb(seed))
    cls = SchemeMonochrome if h.chroma < 8 else SchemeExpressive
    s = cls(h, bool(dark), 0.0)
    return {r: hexs(getattr(M, r).get_hct(s).to_int()) for r in ROLES}
