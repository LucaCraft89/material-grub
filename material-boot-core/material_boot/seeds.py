"""The 32 seed colours offered for the single-colour theme (TUI and GUI), as (name, '#RRGGBB'), ordered by hue so a grid reads like a colour wheel.
stdlib only. The first one, Forest, is this project's own seed. Greys make the Material scheme fall back to monochrome (see mgpalette.scheme)."""

import re

SEEDS = (
    ("Crimson", "#C62828"),
    ("Cherry", "#E53935"),
    ("Coral", "#FF7043"),
    ("Peach", "#FF8A65"),
    ("Tangerine", "#E95420"),
    ("Orange", "#FB8C00"),
    ("Amber", "#FFB300"),
    ("Gold", "#FBC02D"),
    ("Lime", "#8BC34A"),
    ("Moss", "#689F38"),
    ("Pine", "#1B5E20"),
    ("Forest", "#0B3D2E"),
    ("Emerald", "#00A86B"),
    ("Teal", "#00897B"),
    ("Turquoise", "#00ACC1"),
    ("Ice", "#80DEEA"),
    ("Sky", "#29B6F6"),
    ("Ocean", "#0288D1"),
    ("Cobalt", "#1565C0"),
    ("Navy", "#283593"),
    ("Indigo", "#3949AB"),
    ("Violet", "#5E35B1"),
    ("Lavender", "#7E57C2"),
    ("Purple", "#8E24AA"),
    ("Plum", "#6A1B9A"),
    ("Magenta", "#D81B60"),
    ("Fuchsia", "#C2185B"),
    ("Rose", "#EC407A"),
    ("Coffee", "#6D4C41"),
    ("Sand", "#A1887F"),
    ("Slate", "#546E7A"),
    ("Mono", "#808080"),
)
DEFAULT = "#0B3D2E"
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def name_of(color):
    """The name of a preset colour, or None for a custom one."""
    c = color.upper()
    return next((n for n, h in SEEDS if h == c), None)


def xterm256(color):
    """The nearest xterm-256 colour index of '#RRGGBB' (the 6x6x6 cube and the grey ramp), for terminals that cannot define colours."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))

    def cube(v):
        return 0 if v < 48 else 1 if v < 115 else (v - 35) // 40

    ri, gi, bi = cube(r), cube(g), cube(b)
    levels = (0, 95, 135, 175, 215, 255)
    cube_c = (levels[ri], levels[gi], levels[bi])
    grey_i = min(23, max(0, round((((r + g + b) / 3) - 8) / 10)))
    grey = 8 + 10 * grey_i

    def d(a, bb):
        return sum((x - y) ** 2 for x, y in zip(a, bb))

    if max(r, g, b) - min(r, g, b) < 24 and d((grey, grey, grey), (r, g, b)) < d(
        cube_c, (r, g, b)
    ):  # only real greys use the ramp
        return 232 + grey_i
    return 16 + 36 * ri + 6 * gi + bi
