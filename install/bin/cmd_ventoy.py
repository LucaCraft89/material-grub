"""Install the Material theme onto a mounted Ventoy stick. Pillow + stdlib; needs no root (only write access to the stick).
 - scans the stick for ISO/WIM/IMG/VHD files and maps each file name to a catalog distro (colour + logo only; the shown name is the raw file name)
 - renders the scenes of the chosen STYLE (rail | clean | list) like config time does on a PC, writes /ventoy/themes/material_WxH/
 - merges `theme` and `menu_class` into /ventoy/ventoy.json (backup kept, user entries stay first, --uninstall removes only what this tool added)
usage: material-grub-ventoy STICK [--pkg DIR] [--res WxH[,WxH...]] [--gfxmode MODE] [--conf FILE] [--logo FILE] [--uninstall]
The first --res is the screen mode Ventoy starts in (gfxmode); with several, Ventoy switches to the matching theme when the resolution is changed (F5 Tools). `--gfxmode max` is accepted but did not work in QEMU/OVMF (broken display).
STICK is the mount point of the Ventoy data partition. Options come from STICK/ventoy/material-grub.conf (same keys as /etc/material-grub.conf)."""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import mgoverrides
import mgrub


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


EXTS = (".iso", ".wim", ".img", ".vhd", ".vhdx", ".vtoy")
VTOY_FALLBACK = (
    "vtoyiso",
    "vtoywim",
    "vtoyimg",
    "vtoyvhd",
    "vtoyefi",
    "vtoydir",
    "vtoyret",
    "vtoyvtoy",
)  # built-in Ventoy classes: shown when no menu_class matches (the grey disc scene)
MENU = {
    "vtoydir": ("folder", "Folder", "Browse", "tux"),
    "vtoyret": ("back", "Back", "Previous menu", "nixos"),
    "F5tool": ("wrench", "Tools", "Ventoy tools", "firmware"),
    "F4boot": ("firmware", "Local boot", "Boot from disk", "windows10"),
    # the boot-mode menu Ventoy shows after Enter on an image (classes read from Ventoy 1.1.18's grub binary): each mode gets its own colour, background and icon
    "second_normal": ("play", "Normal mode", "Boot as usual", "reboot"),
    "second_grub2": ("kernel", "GRUB2 mode", "Boot through GRUB2", "tux"),
    "second_wimboot": ("windows11", "WIMBOOT mode", "Windows image", "windows11"),
    "second_memdisk": ("firmware", "Memdisk mode", "Load into RAM", "firmware"),
    "second_checksum": ("tag", "File checksum", "Verify the image", "parrot"),
    "second_return": ("back", "Back", "Previous menu", "nixos"),
}
MENU_ALIAS = {
    "debug_reboot": "reboot",
    "debug_halt": "shutdown",
    "debug_efisetup": "firmware",
    "boot_windows": "windows11",
}  # items whose own scene already exists
HINTS = [
    "Arrows  select",
    "Enter  boot",
    "L  Language",
    "F1  Help",
    "F2  Browse",
    "F3  Tree",
    "F4  Local boot",
    "F5  Tools",
    "F6  Ext menu",
]  # every key on Ventoy 1.1.18's own bar: L:Language F1:Help F2:Browse F3:TreeView F4:Localboot F5:Tools F6:ExMenu
THEMES = "ventoy/themes"
STATE = "ventoy/material-grub-state.json"
OVERRIDES = "ventoy/material-grub-overrides.json"  # the stick's own overrides.json (same format; match "title" = text of the file name)
ICONS = "ventoy/material-grub-icons"  # pictures the overrides on the stick point to


def scan(stick):
    """Image files on the stick (not inside /ventoy), in the order Ventoy lists them (case-insensitive by file name; unverified for nested folders)."""
    out = []
    for dp, dn, fn in os.walk(stick):
        if Path(dp) == Path(stick):
            dn[:] = [d for d in dn if d.lower() != "ventoy" and not d.startswith(".")]
        out += [str(Path(dp, f).relative_to(stick).as_posix()) for f in fn if f.lower().endswith(EXTS)]
    return sorted(out, key=lambda r: (Path(r).name.casefold(), r))


def key_of(name, rules):
    """Catalog key from an ISO file name: the PC matcher (case-insensitive tokens), then Windows 10/11 by name, else the Tux fallback."""
    if "pnlug" in name.lower():
        return "pnlug"  # Pordenone Linux User Group: any letter case
    stem = re.sub(r"\.[^.]+$", "", name)
    low = stem.lower()
    k = mgrub.key_for(stem, rules)
    if k:
        return k
    if re.search(r"win(dows)?[ _.\-]?10", low):
        return "windows10"
    if re.search(r"\bwin(dows)?\b|win(dows)?[ _.\-]?11|microsoft", low) or low.startswith("win"):
        return "windows11"
    return "iso"  # not recognised: the grey disc scene


def pick_key(name, others):
    """The `menu_class` key for one file. Ventoy checks it as a case-sensitive substring of the file name, but (verified on Ventoy 1.1.18) a key equal to the WHOLE name never matches
    and keys longer than 31 characters are ignored. So: the longest proper substring of at most 30 characters that no other file name contains (None: no such substring)."""
    for n in range(min(30, len(name) - 1), 0, -1):
        for i in range(len(name) - n + 1):
            s = name[i : i + n]
            if not any(s in o for o in others):
                return s
    return None


GENERIC = mgrub.GENERIC
MIN_KEY = 4
# A Ventoy key is a plain substring, so these common words would match archive, kalimba, mintchoc, tailsman...: they only count with a separator after them
RISKY = {"arch", "kali", "mint", "tails"}
SYSTEM = {"tux", "iso", "firmware", "reboot", "shutdown", "windows10", "windows11"}
WIN_KEYS = [
    ("windows10", ("Windows10", "Windows_10", "Windows-10", "Windows 10", "Win10", "Win_10", "Win-10", "Win 10")),
    (
        "windows11",
        (
            "Windows11",
            "Windows_11",
            "Windows-11",
            "Windows 11",
            "Win11",
            "Win_11",
            "Win-11",
            "Win 11",
            "Windows",
            "Win_",
            "Win-",
            "Win ",
        ),
    ),
]
EXTRA_KEYS = {
    "mxlinux": ["MX-", "MX_"],
    "linuxmint": ["lmde", "LMDE"],
    "opensuse": ["Leap-", "SLE-", "SLES-"],
    "gentoo": ["install-amd64-minimal", "admincd-amd64", "livegui-amd64", "stage3-"],
    "puppy": ["Pup64", "Pup32", "Puppy", "S15Pup", "fossapup", "bionicpup", "focalpup", "bookwormpup", "Pup_"],
    "openbsd": ["install7", "install6", "install8", "miniroot", "cd7", "cd8"],
    "windows10": ["Win_Pro_10", "Win_Ent_10", "Win_Home_10", "Windows_10", "en_windows_10"],
    "windows11": ["Win_Pro_11", "Win_Ent_11", "windows_11", "windows_server"],
    "raspberrypi": ["raspios", "RaspiOS", "Raspios", "raspbian"],
    "freebsd": ["FreeBSD"],
    "tails": ["tails-amd64"],
    "qubes": ["Qubes"],
    "centos": ["CentOS"],
}


def pnlug_rules():
    """`key` is a case-sensitive substring in Ventoy, so every upper / lower combination of 'pnlug' is a rule (32). They go in front of everything else: PNLug-Fedora... is a PNLug image."""
    import itertools

    return [{"key": "".join(c), "class": "mg_pnlug"} for c in itertools.product(*[(ch, ch.upper()) for ch in "pnlug"])]


def dynamic_rules(classes, titles):
    """Generic `menu_class` rules that need no list of files: every catalog alias and title in four letter-cases (as is, lower, UPPER, Capitalised), longest first.
    `key` is a case-sensitive substring in Ventoy, so the cases are what makes 'fedora-...', 'Fedora-...' and 'FEDORA-...' all match. Keys shorter than 4 chars are skipped (too many false hits)."""
    rules = {}
    for k, al in classes.items():
        if k in SYSTEM:
            continue
        for a in set(al) | {
            titles[k],
            titles[k].replace(" ", ""),
            titles[k].replace(" ", "_"),
            titles[k].replace(" ", "-"),
        }:
            if a.lower() in GENERIC:
                continue
            for f in (a, a.lower(), a.upper(), a[:1].upper() + a[1:].lower()):
                if len(f) >= MIN_KEY and 0 < len(f) <= 30:
                    if a.lower() in RISKY:
                        for sep in ("-", "_", " ", "."):
                            rules.setdefault(f + sep, f"mg_{k}")
                    else:
                        rules.setdefault(f, f"mg_{k}")
    for k, keys in EXTRA_KEYS.items():
        for s in keys:
            for f in (s, s.lower(), s.upper()):
                rules.setdefault(f, f"mg_{k}")
    for k, keys in WIN_KEYS:
        for s in keys:
            for f in (s, s.lower(), s.upper()):
                rules.setdefault(f, f"mg_{k}")
    return [{"key": k, "class": c} for k, c in sorted(rules.items(), key=lambda kv: (-len(kv[0]), kv[0]))]


def pill_slices(out, prefix, h, rgba, w=None):
    """9-slice pieces of a pill (GRUB pixmap style `prefix_*.png`), same method as scripts/build_theme.py but with a translucent colour."""
    from PIL import Image, ImageDraw

    w = w or 2 * h + 8
    S = 4
    r = h // 2
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=r * S, fill=rgba)
    im = im.resize((w, h), Image.LANCZOS)
    cs = r - 1
    xs = [(0, cs), (cs, w - cs), (w - cs, w)]
    ys = [(0, cs), (cs, h - cs), (h - cs, h)]
    names = [["nw", "n", "ne"], ["w", "c", "e"], ["sw", "s", "se"]]
    for j, (y0, y1) in enumerate(ys):
        for i, (x0, x1) in enumerate(xs):
            im.crop((x0, y0, x1, y1)).save(out / f"{prefix}_{names[j][i]}.png")


def _bm(font, left, top, width, height, item_h, spacing, color, sel_color, pix=""):
    return f'''+ boot_menu {{
  left = {left}
  top = {top}
  width = {width}
  height = {height}
  item_height = {item_h}
  item_spacing = {spacing}
  item_padding = 0
  item_icon_space = 0
  icon_width = 1
  icon_height = 1
  item_font = "{font}"
  selected_item_font = "{font}"
  item_color = "{color}"
  selected_item_color = "{sel_color}"
{pix}  scrollbar = false
}}
'''


def row_geom(W, H):
    """The rows of the native list: pixel values of the 1080-high design scaled to this resolution. (x, y of the first row, width, row height, pitch, number of rows)"""

    def q(v):
        return round(v * H / 1080)

    return round(W * 0.47), q(110), q(640), q(76), q(88), 7


def rows_block(text, W, H, light, opaque=None):
    """theme.txt block of the native list: one pill per entry (works for any number of ISOs, GRUB scrolls it). GRUB grows every item box DOWNWARDS by the pixmap's edge slices (2*cs px; verified, no growth sideways or upwards)
    and clips text to the item rectangle, so two synchronised lists are used: the pills (a 2 px item rectangle that the pixmap grows into a pill) and, on top, the text (full-height items, no pixmap)."""
    font = re.findall(r'item_font = "([^"]+)"', text)[-1]
    x0, y0, w, h, pitch, N = row_geom(W, H)

    def q(v):
        return round(v * H / 1080)

    cs = h // 2 - 1
    ih = h - 2 * cs
    ink, sel = ("#1B1B1F", "#000000") if light else ("#E6E1E5", "#FFFFFF")
    H_ = N * pitch - (pitch - h)
    return (
        "# mg:list rows drawn by GRUB (dynamic list): text on top, pills below\n"
        + _bm(font, x0 + q(30), y0, w - q(60), H_, h, pitch - h, ink, sel)
        + "\n"
        + _bm(
            font,
            x0,
            y0,
            w,
            H_,
            ih,
            pitch - ih,
            "#00000000",
            "#00000000",
            '  item_pixmap_style = "mgrow_*.png"\n  selected_item_pixmap_style = "mgsel_*.png"\n',
        )
        + "\n"
    )


def native_list(text, W, H, light):
    """`list` style: the rows go before the scene menu, so they are drawn on top of the scene."""
    block = rows_block(text, W, H, light)
    mark = "# GRUB draws the first-declared component on top"
    return text.replace(mark, block + mark, 1) if mark in text else text + block


def pill_geom(W, H):
    """The wide pill under the title in the full-screen ISO scenes: (left, top, width, height) and the x where the file name starts (after the distro logo and the disc icon)."""

    def q(v):
        return round(v * H / 1080)

    w, h = q(900), q(72)
    left, top = (W - w) // 2, q(736)
    return left, top, w, h, left + q(26) + 2 * q(36) + q(14) + q(18)


def fullscreen_layers(text, W, H, light, raw):
    """`rail` / `clean`: the scene menu stays on top of GRUB's own lists. The scenes of Ventoy's other menus (F2-F5, folders, boot modes) are list scenes with holes where the rows are, so the rows show through only there;
    in the ISO scenes (opaque) they are hidden. The same goes for the file name: the raw-name label and a pill under it sit below the scene and show through the hole in the ISO scenes' pill."""

    def q(v):
        return round(v * H / 1080)

    lay = ""
    if raw:
        text = re.sub(r"(?ms)^# mg:begin raw\n.*?^# mg:end raw\n", "", text)
        left, top, w, h, tx = pill_geom(W, H)
        cs = h // 2 - 1
        ih = h - 2 * cs
        ty = (
            2 * (top + h // 2) - H
        )  # GRUB ignores a list's height and shows every row down to the screen edge; one item that reaches the edge keeps it a 1-item list (text is centred in the item, so the item is centred on the pill)
        ink = "#1B1B1F" if light else "#E6E1E5"
        pix = '  item_pixmap_style = "mgrow_*.png"\n  selected_item_pixmap_style = "mgrow_*.png"\n'
        lay += (
            "# mg:filename the raw file name in a pill under the title (seen through the hole of the ISO scenes)\n"
            + _bm("MG-Label Regular 26", tx, ty, left + w - tx - q(28), H - ty, H - ty, 0, ink, ink)
            + "\n"
            + _bm("MG-Label Regular 26", left, top, w, h, ih, h - ih, "#00000000", "#00000000", pix)
            + "\n"
        )
    lay += rows_block(text, W, H, light)

    def cd(m):  # the countdown bar would sit on the pill: move it below
        s = re.sub(r"(?m)^(\s*top = )755$", rf"\g<1>{q(830)}", m[0])
        return re.sub(r"(?m)^(\s*top = )790$", rf"\g<1>{q(848)}", s)

    text = re.sub(r"(?ms)^# mg:begin countdown\n.*?^# mg:end countdown\n", cd, text)
    return text.rstrip("\n") + "\n\n" + lay


def punch(im, boxes):
    """Make rounded rectangles (x, y, w, h) of a scene fully transparent (inset by 1 px so the translucent edge of what lies below never shows)."""
    from PIL import Image, ImageChops, ImageDraw

    im = im.convert("RGBA")
    S = 4
    m = Image.new("L", (im.width * S, im.height * S), 255)
    d = ImageDraw.Draw(m)
    for x, y, w, h in boxes:
        d.rounded_rectangle(
            [(x + 1) * S, (y + 1) * S, (x + w - 1) * S - 1, (y + h - 1) * S - 1], radius=(h // 2 - 1) * S, fill=0
        )
    im.putalpha(ImageChops.darker(im.getchannel("A"), m.resize(im.size, Image.LANCZOS)))
    return im


def logo_png(path, size, src=None):
    """The logo drawn in the cookie: the real Ventoy logo (blue disc with a USB stick, shipped in the package, full colour) or `src`, any image of your own. Both keep their colours."""
    from PIL import Image

    src = (
        Path(src)
        if src
        else next(
            (
                c
                for c in (
                    PKG / "ventoy/VentoyLogo.png",
                    Path(__file__).resolve().parents[2] / "vendor/ventoy/VentoyLogo.png",
                )
                if c.exists()
            ),
            None,
        )
    )
    if src is None:
        sys.exit(
            "material-grub-ventoy: the Ventoy logo is missing from the package (ventoy/VentoyLogo.png); pass --logo FILE or --no-logo"
        )
    im = Image.open(src).convert("RGBA")
    bb = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    im = im.crop(bb) if bb else im  # trim the empty border
    s = size / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    out.save(path)


def load_json(p):
    try:
        return json.loads(Path(p).read_text() or "{}")
    except FileNotFoundError:
        return {}


def uninstall():
    vj = load_json(vj_path)
    mine = state.get("menu_class", [])
    vj["menu_class"] = [m for m in vj.get("menu_class", []) if m not in mine]
    if not vj["menu_class"]:
        vj.pop("menu_class")
    mine_alias = state.get("menu_alias", [])
    vj["menu_alias"] = [m for m in vj.get("menu_alias", []) if m not in mine_alias]
    if not vj["menu_alias"]:
        vj.pop("menu_alias")
    th = vj.get("theme", {})
    ours = state.get("theme_files", [])
    files = th.get("file")
    files = [files] if isinstance(files, str) else files or []
    if files and all(f in ours for f in files):
        vj.pop("theme", None)
        if state.get("prev_theme"):
            vj["theme"] = state["prev_theme"]
    vj_path.write_text(json.dumps(vj, indent=1) + "\n")
    for d in state.get("theme_dirs", []):
        shutil.rmtree(stick / d, ignore_errors=True)
    state_path.unlink(missing_ok=True)
    (stick / "ventoy/material-grub.conf").unlink(missing_ok=True)
    try:
        (stick / THEMES).rmdir()  # only if empty: other themes stay
    except OSError:
        pass
    print("material-grub-ventoy: removed")


LOGOS = {}  # full-colour logos of catalog entries that have their own (PNLug)
entries = []


def main():
    global PKG, state, state_path, stick, vj_path
    stick = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
    if not stick or not (stick / "ventoy").is_dir():
        sys.exit(
            "material-grub-ventoy: STICK must be the mount point of a Ventoy data partition (it has no /ventoy folder)"
        )
    PKG = Path(arg("--pkg", "/usr/share/material-grub"))
    vj_path = stick / "ventoy/ventoy.json"
    state_path = stick / STATE
    state = load_json(state_path)
    if "--uninstall" in sys.argv:
        uninstall()
        sys.exit(0)
    try:
        import mgscenes
        from PIL import Image
    except ImportError:
        sys.exit("material-grub-ventoy: Pillow is required")
    conf = mgrub.load_conf(arg("--conf", str(stick / "ventoy/material-grub.conf")))
    style = conf["STYLE"]
    style = (
        "list" if style in ("list", "split") else "full"
    )  # Ventoy has two styles: the full-screen ISO picker (rail / clean from older versions map to it) and the list (`split` is the same thing: its list already is hero-left / list-right)
    conf["COUNTDOWN"] = "on" if conf["TIMEOUT"] else "off"  # Ventoy has no timeout unless one is configured
    rules = mgrub.load_rules(PKG)
    classes = json.loads((PKG / "classes.json").read_text())
    avail = sorted(p.name for p in (PKG / "res").iterdir())
    resl = [r for r in (arg("--res") or "").split(",") if r] or avail[:1]
    for r in resl:
        if r not in avail:
            sys.exit(f"material-grub-ventoy: resolution {r} is not in the package (has: {', '.join(avail)})")
    dynamic = (
        conf["MODE"] == "dynamic"
    )  # dynamic: nothing depends on the files on the stick (generic rules, one scene per distro); snapshot: scenes are rendered for the files that are there now
    titles = json.loads((PKG / "titles.json").read_text())
    _pn = next(
        (
            c
            for c in (PKG / "ventoy/pnlug.png", Path(__file__).resolve().parents[2] / "vendor/pnlug/logo.png")
            if c.exists()
        ),
        None,
    )
    if _pn and "pnlug" in classes:
        LOGOS["pnlug"] = Image.open(_pn).convert("RGB")
    ov, ov_problems = mgoverrides.load(stick / OVERRIDES)
    for pr in ov_problems:
        print(f"material-grub-ventoy: overrides: {pr}")
    all_files = scan(stick)
    files = [] if dynamic else all_files
    for rel in files:
        name = Path(rel).name
        k = key_of(name, rules)
        entries.append(
            {
                "class": mgrub.uid("ventoy", rel),
                "key": k,
                "kind": "plain",
                "level": "top",
                "title": name,
                "label": name,
                "path": rel,
            }
        )
    # files the user customised (colour, icon, name): each gets its own class and scene, whatever the mode
    custom = []
    for rel in all_files:
        name = Path(rel).name
        custom.append(
            {
                "class": "mgu_" + mgrub.uid("ventoy", rel)[3:],
                "key": key_of(name, rules),
                "kind": "plain",
                "level": "top",
                "title": name,
                "label": name,
                "path": rel,
            }
        )
    keys = sorted({e["key"] for e in entries}) or ["iso"]
    if dynamic:
        keys = list(classes)
    elif "pnlug" in classes and "pnlug" not in keys:
        keys.append("pnlug")  # its rules are always written, so its scene must exist
    groups = mgscenes.groups_of(keys)
    by_class = {e["class"]: e for e in entries}
    menu = [{"level": "top", "items": [e["class"] for e in entries]}]
    opts = {"cookie": conf["COOKIE"] == "on", "hints": conf["HINTS"] == "on", "shape": "cookie"}
    per_entry = style == "list"
    print(
        f"material-grub-ventoy: mode {conf['MODE']}, {len(entries)} images, {len(keys)} distros, style {style}, resolutions {', '.join(resl)}"
    )
    theme_dirs, theme_files, fonts, menu_class = [], [], [], []
    for res in resl:
        rdir = PKG / "res" / res
        aspect = (rdir / "aspect").read_text().strip()
        rel_dir = f"{THEMES}/material_{res}"
        out = stick / rel_dir
        tmp = out.with_name(out.name + ".new")
        shutil.rmtree(tmp, ignore_errors=True)
        (tmp / "icons").mkdir(parents=True)
        for f in rdir.iterdir():
            if f.name not in ("logo_size", "aspect"):
                shutil.copy(f, tmp / f.name)
        th = tmp / "theme.txt"
        th.write_text(mgrub.apply_conf_to_theme(th.read_text(), conf))
        rw, rh = map(int, res.split("x"))
        light = (PKG / "scheme.txt").read_text().strip() == "light" if (PKG / "scheme.txt").exists() else False
        q = round(76 * rh / 1080)
        fs = (
            style == "full"
        )  # full screen: only the ISO picker keeps it; Ventoy's other menus are list scenes whose rows come from GRUB's own list below the scene
        if dynamic and style == "list":
            th.write_text(native_list(th.read_text(), rw, rh, light))
            pill_slices(tmp, "mgrow", q, (0, 0, 0, 20) if light else (255, 255, 255, 24))
            pill_slices(tmp, "mgsel", q, (0, 0, 0, 52) if light else (255, 255, 255, 70))
        elif fs:
            base = mgscenes.hexc(re.search(r'desktop-color: "(#[0-9A-Fa-f]{6})"', th.read_text())[1])
            desk = base  # the rows lie below the scene, over the desktop colour: the pills are opaque, and the list scenes carry a card of that colour behind the rows

            def over(c, a):
                return tuple(round(b * (1 - a / 255) + c * a / 255) for b in base) + (255,)

            th.write_text(fullscreen_layers(th.read_text(), rw, rh, light, conf["RAW_NAME"] == "on"))
            pill_slices(tmp, "mgrow", q, over(0, 20) if light else over(255, 24))
            pill_slices(tmp, "mgsel", q, over(0, 52) if light else over(255, 70))
        for n in ("OFL.txt", "TRADEMARKS.md"):
            if (PKG / "fonts" / n).exists():
                shutil.copy(PKG / "fonts" / n, tmp / n)
        for cand in (
            "/usr/share/grub/unicode.pf2",
            "/usr/share/grub2/unicode.pf2",
            "/usr/share/fonts/grub/unicode.pf2",
            "/usr/share/fonts/truetype/unifont/unicode.pf2",
            "/boot/grub/fonts/unicode.pf2",
            "/boot/grub2/fonts/unicode.pf2",
        ):
            if os.path.exists(cand):
                shutil.copy(cand, tmp / "unicode.pf2")
                break
        if conf["LOGO"] == "on" and conf["COOKIE"] == "on":
            logo_png(tmp / "machine-logo.png", int((rdir / "logo_size").read_text().strip()), arg("--logo"))
        bgs = sorted((PKG / "scenes" / aspect / "bg").glob("*.png"))
        R = mgscenes.Renderer(PKG, Image.open(bgs[0]).height)
        R.hint_labels = HINTS
        R.logos = LOGOS
        import copy

        import mgcustom

        c_ents = copy.deepcopy(custom)
        ov_tmp = tempfile.mkdtemp(prefix="mg-ventoy-overlay-")
        mgcustom.apply(R, ov, c_ents, PKG, aspect, Image.open(bgs[0]).size, classes, icon_dir=stick / ICONS, tmp=ov_tmp)
        custom_done = [e for e in c_ents if e.get("orig_key")]
        bgdir = (
            R.bg_dir
        )  # the overlay's: the baked panel of a key whose colour was not changed, a redrawn one otherwise
        raw_on = conf["RAW_NAME"] == "on"

        def rows_of(im):
            x0, y0, w, h, pitch, n = row_geom(*im.size)
            return [(x0, y0 + i * pitch, w, h) for i in range(n)]

        def carded(im):
            """A rounded card in the desktop colour behind the 7 row slots: slots without an entry show the desktop colour through their hole, so they melt into the card instead of showing as dark ghosts."""
            from PIL import ImageDraw

            x0, y0, w, h, pitch, n = row_geom(*im.size)
            S = 3
            pad = round(24 * im.height / 1080)
            m = Image.new("L", (im.width * S, im.height * S), 0)
            ImageDraw.Draw(m).rounded_rectangle(
                [(x0 - pad) * S, (y0 - pad) * S, (x0 + w + pad) * S, (y0 + (n - 1) * pitch + h + pad) * S],
                radius=round(44 * im.height / 1080) * S,
                fill=255,
            )
            im = im.convert("RGBA")
            im.paste(Image.new("RGBA", im.size, desk + (255,)), mask=m.resize(im.size, Image.LANCZOS))
            return im

        def list_scene(k, pal_key=None):  # a list scene whose rows are holes: GRUB's own list shows through
            return punch(
                carded(R.render_list_hero(k, bgdir / f"{pal_key or k}.png", opts)),
                rows_of(Image.open(bgdir / f"{pal_key or k}.png")),
            )

        if fs:
            (tmp / "_hero").mkdir()
            for k in (
                keys + (["iso"] if "iso" not in keys else []) + [e["key"] for e in custom_done]
            ):  # background + hero with a slightly smaller title (the file name is the main text here)
                sc = Image.open(bgdir / f"{k}.png").convert("RGBA")
                R.hero(sc, {"key": k, "kind": "plain", "title": ""}, R.pal[k], 124)
                sc.save(tmp / "_hero" / f"{k}.png".replace("~", "_"))

        def finish_iso(im, k):
            """ISO picker scene: a hole where the file-name pill is (the raw-name label shows through it) and the distro logo and a disc icon at the start of the pill."""
            im = im.convert("RGBA")
            if not raw_on:
                return im
            W, H = im.size
            L, T, Wp, Hp, tx = pill_geom(W, H)
            s = round(36 * H / 1080)
            im = punch(im, [(L, T, Wp, Hp)])
            ink = mgscenes.hexc(R.pal[k]["primary"]) + (255,)
            x1 = L + round(26 * H / 1080)
            x2 = x1 + s + round(14 * H / 1080)
            for g, x in ((k, x1), ("iso", x2)):
                im.alpha_composite(R.glyph(g, s, ink), (x, T + (Hp - s) // 2))
            return im

        def class_scene(k):
            if fs:  # background + hero, the cookie, two scroll arrows on the left; no rail, no neighbours, no key hints
                sc = Image.open(tmp / "_hero" / f"{k}.png".replace("~", "_")).convert("RGBA")
                R.decorate(sc, R.pal[k], dict(opts, hints=False))
                R.draw_arrows(sc, R.pal[k])
                return finish_iso(sc, k)
            if dynamic:
                return R.render_list_hero(k, bgdir / f"{k}.png", opts)
            # snapshot list: the whole list, nothing highlighted (also what an ISO added after install gets)
            return R.render_list_fallback(k, bgdir / f"{k}.png", entries, opts)

        for k in keys:
            class_scene(k).save(tmp / "icons" / f"mg_{k}.png")
        for e in custom_done:  # one scene per customised file
            class_scene(e["key"]).save(tmp / "icons" / f"{e['class']}.png")
        generic = (
            Image.open(tmp / "icons" / "mg_iso.png") if "iso" in keys else class_scene("iso")
        )  # Ventoy's own classes (vtoyiso, vtoywim, ...) and every file the rules do not recognise
        for c in VTOY_FALLBACK:
            generic.save(tmp / "icons" / f"{c}.png")
        if fs:  # power / firmware / Windows items of F4 / F5: list scenes
            for c, k in MENU_ALIAS.items():
                list_scene(k).save(tmp / "icons" / f"{c}.png")
        elif dynamic:  # the existing scenes for Ventoy's power / firmware / Windows items
            for c, k in MENU_ALIAS.items():
                shutil.copy(tmp / "icons" / f"mg_{k}.png", tmp / "icons" / f"{c}.png")
        if (
            fs or dynamic
        ):  # Ventoy's own menus: a scene each (folder, back, tools, local boot, the boot modes); the snapshot list bakes its rows into the scenes, so it has none
            for c, (glyph, title, _sub, pal) in MENU.items():
                pk = f"mgm_{c}"
                R.pal[pk] = R.pal[pal]
                R.titles[pk] = title
                R.galias[pk] = glyph
                bg = bgdir / f"{pal}.png"
                if fs:
                    img = punch(carded(R.render_list_hero(pk, bg, opts)), rows_of(Image.open(bg)))
                else:
                    img = R.render_list_hero(pk, bg, opts)
                img.save(tmp / "icons" / f"{c}.png")
        if per_entry and not dynamic:
            for e in entries:
                im = R.render_entry(e, bgdir / f"{e['key']}.png", groups, "list", opts, menu, by_class)
                im.save(tmp / "icons" / f"{e['class']}.png")
        shutil.rmtree(tmp / "_hero", ignore_errors=True)
        shutil.rmtree(ov_tmp, ignore_errors=True)
        shutil.rmtree(out, ignore_errors=True)
        os.replace(tmp, out)
        theme_dirs.append(rel_dir)
        theme_files.append(f"/{rel_dir}/theme.txt")
        fonts += [f"/{rel_dir}/{p.name}" for p in sorted(out.glob("*.pf2"))]
    bak = vj_path.with_name("ventoy.json.material-grub.bak")
    if vj_path.exists() and not bak.exists():
        shutil.copy(vj_path, bak)
    vj = load_json(vj_path)
    old_mine = state.get("menu_class", [])
    user_mc = [m for m in vj.get("menu_class", []) if m not in old_mine]
    names = sorted({Path(e["path"]).name for e in entries})
    names_all = sorted({Path(e["path"]).name for e in custom})
    menu_class, menu_alias = [], []
    for e in custom_done:  # customised files first: Ventoy takes the first rule that matches
        name = Path(e["path"]).name
        key = pick_key(name, [o for o in names_all if o != name])
        if key is None:
            print(f"material-grub-ventoy: warning: no unique key for {name}; its customisation is skipped")
            continue
        menu_class.append({"key": key, "class": e["class"]})
        if e.get("name"):
            menu_alias.append({"image": "/" + e["path"], "alias": e["name"]})
    if dynamic:
        menu_class += pnlug_rules() + dynamic_rules(classes, titles)
    else:
        menu_class += pnlug_rules()  # also for files added after the install
    for e in [] if dynamic else entries:
        name = Path(e["path"]).name
        key = pick_key(name, [o for o in names if o != name])
        if key is None:
            print(f"material-grub-ventoy: warning: no unique key for {name}; it keeps the generic scene")
            continue
        menu_class.append({"key": key, "class": e["class"] if per_entry else f"mg_{e['key']}"})
    seen = set()
    menu_class = [m for m in menu_class if not (m["key"] in seen or seen.add(m["key"]))]
    vj["menu_class"] = user_mc + menu_class  # the user's own rules come first and win
    old_alias = state.get("menu_alias", [])
    user_alias = [m for m in vj.get("menu_alias", []) if m not in old_alias]
    if user_alias or menu_alias:
        vj["menu_alias"] = user_alias + [
            m for m in menu_alias if m["image"] not in {u.get("image") for u in user_alias}
        ]
    else:
        vj.pop("menu_alias", None)
    th = vj.get("theme", {})
    ours = state.get("theme_files", [])
    cur = th.get("file")
    cur = [cur] if isinstance(cur, str) else cur or []
    prev = state.get("prev_theme") if cur and all(c in ours for c in cur) else (th or None)
    th.update(
        {
            "file": theme_files[0] if len(theme_files) == 1 else theme_files,
            "gfxmode": arg("--gfxmode") or resl[0],
            "fonts": fonts,
        }
    )
    if len(theme_files) > 1:
        th.update({"default_file": 0, "resolution_fit": 1})
    else:
        th.pop("default_file", None)
        th.pop("resolution_fit", None)
    vj["theme"] = th
    vj_path.write_text(json.dumps(vj, indent=1) + "\n")
    state_path.write_text(
        json.dumps(
            {
                "menu_class": menu_class,
                "menu_alias": menu_alias,
                "theme_files": theme_files,
                "theme_dirs": theme_dirs,
                "prev_theme": prev,
            },
            indent=1,
        )
    )
    print(
        f"material-grub-ventoy: wrote {', '.join(theme_dirs)} and merged ventoy.json ({len(menu_class)} menu_class rules); backup: {bak.name}"
    )
