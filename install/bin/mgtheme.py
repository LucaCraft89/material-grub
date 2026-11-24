"""theme.txt for ANY screen size, and the safety nets around it. stdlib only (it runs at config time on the user's machine, where there is no build).

The scenes are pictures that GRUB scales to `icon_width x icon_height`, so a theme is pixel-bound: it only fits the screen mode it was written for.
What went wrong before: the installed bundle was the CLOSEST built-in size (1366x768 got the 1280x720 one) and `gfxmode` named that size, so a machine whose
firmware has no 1280x720 mode fell back to its native mode and showed a 1280x720 theme in the top-left corner with empty margins. Now:

  theme_text(W, H, ...)   the theme for exactly this size (the same template the build uses for its bundles; tests/test_mgtheme.py checks it byte for byte)
  anchor_centre(text)     every left/top becomes `50%+N` / `50%-N`: identical when the mode is the one asked for, and when it is not (a firmware that has no
                          such mode) the theme sits CENTRED with even margins instead of in a corner. The raw-name line is anchored to the bottom edge.
  basic_theme_text(...)   a theme with no picture and no pixel size that fits any screen: a plain list, used where the screen size is not known

GRUB 2.12's gfxmenu accepts `left = 50%-320` (verified in QEMU/OVMF); it does NOT accept percentages for icon sizes, hence the pixel-exact themes above.
"""

import re

MIN_SIDE, MAX_SIDE = 320, 16384
ASPECTS = {
    "16x9": 1920,
    "16x10": 1728,
    "21x9": 2560,
    "32x9": 3840,
}  # the scene sets: design width at 1080 high (scripts/build_theme.py reads this table)


def parse_mode(mode):
    """'1366x768' or '1366x768x32' -> (1366, 768); None for anything else (empty, 'auto', 'keep', garbage, absurd sizes)."""
    m = re.match(r"^\s*(\d{3,5})x(\d{3,5})(?:x\d+)?\s*$", str(mode or ""))
    if not m:
        return None
    w, h = int(m[1]), int(m[2])
    return (w, h) if MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE else None


def first_mode(gfxmode):
    """The first usable WxH of a GRUB_GFXMODE value ('1366x768,1280x720,auto' -> (1366, 768)); None when there is none ('auto', '', 'keep')."""
    for part in str(gfxmode or "").split(","):
        r = parse_mode(part)
        if r:
            return r
    return None


def native_mode(drm="/sys/class/drm"):
    """The native size of the biggest connected display, from the kernel's own mode lists (the first mode of a connector is its preferred one); None when it cannot
    be told (no DRM, a VM without a display, no permission). The biggest wins so that a small secondary screen does not decide."""
    import glob
    import os

    best, area = None, 0
    for status in sorted(glob.glob(os.path.join(drm, "card*-*", "status"))):
        try:
            with open(status) as f:
                if f.read().strip() != "connected":
                    continue
            with open(os.path.join(os.path.dirname(status), "modes")) as f:
                first = f.read().splitlines()[0]
        except (OSError, IndexError):
            continue
        m = parse_mode(first)
        if m and m[0] * m[1] > area:
            best, area = m, m[0] * m[1]
    return best


def colours(light):
    """(desktop colour, countdown track, countdown fill, countdown text, raw-name colour): neutral Material greys chosen per scheme (GRUB cannot recolour per entry)."""
    track, fill, text = ("#CAC4D0", "#49454F", "#49454F") if light else ("#49454F", "#E6E1E5", "#CAC4D0")
    desktop, raw = ("#F6F4F7", "#5F5B66") if light else ("#0D1411", "#6E7681")
    return desktop, track, fill, text, raw


def sizes(H):
    """The sizes that follow the screen height: (px(), bar height, label font size, raw font size). `px` scales a 1080-high design value."""
    sf = H / 1080

    def px(v):
        return round(v * sf)

    return px, max(8, round(14 * sf)), round(26 * sf), max(12, round(20 * sf))


def theme_text(W, H, wds=None, light=False, aspect="16x9", fs=None, rs=None, bh=None):
    """The theme for a W x H screen. `wds`: the design width of the scene set at 1080 high (ASPECTS): the scene pictures are scaled by GRUB to W x H, so the machine
    logo goes where the baked cookie ends up, x scaled by W / wds and y by H / 1080 (for a built bundle both are the same factor). None: derived from W.
    `fs`, `rs`, `bh`: the font sizes and bar height of the fonts and pictures copied from a built bundle (their names carry the size)."""
    px, bh0, fs0, rs0 = sizes(H)
    fs, rs, bh = fs or fs0, rs or rs0, bh or bh0
    wds = wds if wds is not None else W / (H / 1080)
    desktop, track, fill, text, raw = colours(light)
    sx = W / wds

    def px_x(v):
        return round(v * sx)

    cxp, barw, logo = round(W / 2), px(560), px(120)
    lx, ly = px_x(wds - 150) - logo // 2, px(140) - logo // 2
    FN, RN = f"MG-Label Regular {fs}", f"MG-Raw Regular {rs}"
    return f'''# Material 3 Expressive GRUB theme (generated for {W}x{H}, {aspect} scenes)
title-text: ""
desktop-color: "{desktop}"
terminal-font: "{FN}"

# mg:begin raw
# raw entry name (debug/clarity): a 1-item list that only ever shows the selected entry
+ boot_menu {{
  left = {px_x(96)}
  top = {H - px(58)}
  width = {W - px_x(192)}
  height = {px(34)}
  item_height = {px(34)}
  item_spacing = 0
  item_padding = 0
  item_icon_space = 0
  icon_width = 1
  icon_height = 1
  item_font = "{RN}"
  selected_item_font = "{RN}"
  item_color = "{raw}"
  selected_item_color = "{raw}"
  scrollbar = false
}}
# mg:end raw

# mg:begin logo
+ image {{
  left = {lx}
  top = {ly}
  width = {logo}
  height = {logo}
  file = "machine-logo.png"
}}
# mg:end logo

# mg:begin countdown
+ progress_bar {{
  id = "__timeout__"
  left = {cxp - barw // 2}
  top = {px(755)}
  width = {barw}
  height = {bh}
  bar_style = "bar_*.png"
  highlight_style = "hl_*.png"
}}

+ label {{
  id = "__timeout__"
  left = {cxp - barw // 2}
  top = {px(790)}
  width = {barw}
  height = {px(34)}
  align = "center"
  color = "{text}"
  font = "{FN}"
  text = "Booting in %d seconds"
}}
# mg:end countdown

# GRUB draws the first-declared component on top, so the menu goes last
+ boot_menu {{
  left = 0
  top = 0
  width = {W}
  height = {H}
  item_height = {H}
  item_spacing = 0
  item_padding = 0
  item_icon_space = 0
  icon_width = {W}
  icon_height = {H}
  item_font = "{FN}"
  selected_item_font = "{FN}"
  item_color = "#00000000"
  selected_item_color = "#00000000"
  scrollbar = false
}}
'''


_POS = re.compile(r"(?m)^(?P<k>\s*(?:left|top) = )(?P<v>-?\d+)$")


def anchor_centre(text, W, H):
    """Rewrite every `left`/`top` of a theme written for W x H relative to the centre of the screen (`50%+N`, `50%-N`). On a W x H screen nothing changes;
    on any other the theme stays together and centred. The raw-name list (`# mg:begin raw`) is anchored to the BOTTOM edge instead (`100%-N`): GRUB shows as
    many rows of a list as fit down to the screen edge, so that is what keeps it a one-row list on a screen taller than the theme."""

    def centre(m):
        half = W // 2 if m["k"].lstrip().startswith("left") else H // 2
        v = int(m["v"]) - half
        return f"{m['k']}50%{'+' if v >= 0 else '-'}{abs(v)}"

    def bottom(m):
        return m.group(0) if m["k"].lstrip().startswith("left") else f"{m['k']}100%-{H - int(m['v'])}"

    out, pos = [], 0
    for blk in re.finditer(r"(?ms)^# mg:begin raw\n.*?^# mg:end raw\n", text):
        out.append(_POS.sub(centre, text[pos : blk.start()]))
        raw = blk.group(0)
        raw = _POS.sub(bottom, raw)
        raw = re.sub(
            r"(?m)^(\s*left = )(-?\d+)$",
            lambda m: f"{m[1]}50%{'+' if int(m[2]) - W // 2 >= 0 else '-'}{abs(int(m[2]) - W // 2)}",
            raw,
        )
        out.append(raw)
        pos = blk.end()
    out.append(_POS.sub(centre, text[pos:]))
    return "".join(out)


def basic_theme_text(light=False, fs=26, rs=20, bh=14):
    """A theme that fits any screen: no scene picture, nothing sized in pixels except the text. A centred list of the entries (the selected one on a pill) and the
    countdown. Used where the screen size is not known, so there is no pixel-exact theme to give; also the proof that the menu never depends on a size."""
    desktop, track, fill, text, raw = colours(light)
    on_pill = "#FFFFFF" if light else "#1C1B1F"
    rowh = round(fs * 2.2)
    FN, RN = f"MG-Label Regular {fs}", f"MG-Raw Regular {rs}"
    return f'''# Material 3 Expressive GRUB theme: basic, any screen size (no pictures, percentages)
title-text: ""
desktop-color: "{desktop}"
terminal-font: "{FN}"

# mg:begin raw
+ boot_menu {{
  left = 5%
  top = 100%-{round(rs * 2.6)}
  width = 90%
  height = {round(rs * 1.7)}
  item_height = {round(rs * 1.7)}
  item_spacing = 0
  item_padding = 0
  item_icon_space = 0
  icon_width = 1
  icon_height = 1
  item_font = "{RN}"
  selected_item_font = "{RN}"
  item_color = "{raw}"
  selected_item_color = "{raw}"
  scrollbar = false
}}
# mg:end raw

# mg:begin countdown
+ progress_bar {{
  id = "__timeout__"
  left = 30%
  top = 86%
  width = 40%
  height = {bh}
  bar_style = "bar_*.png"
  highlight_style = "hl_*.png"
}}

+ label {{
  id = "__timeout__"
  left = 30%
  top = 89%
  width = 40%
  height = {round(fs * 1.4)}
  align = "center"
  color = "{text}"
  font = "{FN}"
  text = "Booting in %d seconds"
}}
# mg:end countdown

+ boot_menu {{
  left = 20%
  top = 12%
  width = 60%
  height = 70%
  item_height = {rowh}
  item_spacing = {round(fs * 0.4)}
  item_padding = {round(fs * 0.9)}
  item_icon_space = 0
  icon_width = 1
  icon_height = 1
  item_font = "{FN}"
  selected_item_font = "{FN}"
  item_color = "{text if not light else "#49454F"}"
  selected_item_color = "{on_pill}"
  selected_item_pixmap_style = "hl_*.png"
  scrollbar = false
}}
'''
