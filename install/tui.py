#!/usr/bin/env python3
"""Material GRUB installer questions (curses TUI with a plain-prompt fallback). stdlib only.
It only COLLECTS answers: install.sh does the work. Answers go to --out as shell-safe KEY=value lines (every value is validated first).
usage: tui.py --out FILE [--preset KEY=value ...] [--immutable] [--plain] [--monitors JSON] [--ask-target] [--sticks JSON]
  presets (answers given by installer flags) are not asked again: TARGET STICK RES RESX STYLE SCHEME COOKIE LOGO HINTS RAW_NAME COUNTDOWN TIMEOUT MODE
  --ask-target first asks "this computer's GRUB or a Ventoy USB stick"; TARGET=ventoy switches to the Ventoy questions (stick picker, resolutions, dynamic/snapshot)
exit status: 0 = confirmed, 1 = cancelled."""
import json, os, re, sys, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

BUILTIN = "1280x720 1920x1080 1920x1200 2560x1080 2560x1440 2880x1800 3440x1440 3840x1080 3840x1600 3840x2160 5120x1440 5120x2160".split()
RES_RE = re.compile(r"^[0-9]{3,5}x[0-9]{3,5}$")
def stick_ok(p):
    """A typed mount point must be a Ventoy data partition: its disk has a VTOYEFI partition (a fresh stick has no /ventoy folder yet) or it holds a /ventoy folder."""
    if not CHECK["STICK"].match(p): return False
    try: import ventoy_sticks; return bool(ventoy_sticks.check(p))
    except Exception: return Path(p, "ventoy").is_dir()
def snap(res):
    """Same rule as install.sh / material-grub-assemble: exact size, else the closest aspect ratio, then the closest height."""
    w, h = map(int, res.split("x")); size = lambda r: tuple(map(int, r.split("x")))
    return res if res in BUILTIN else min(BUILTIN, key=lambda r: (abs(size(r)[0] / size(r)[1] - w / h) > 0.02, abs(size(r)[1] - h)))

WIRE = {
 "rail": ["+------------------+", "|[o]          (o) |", "| o     ( icon )  |", "| o     Fedora    |", "|[o]   [pills]    |", "+------[hints]-----+"],
 "clean": ["+------------------+", "| (next panel peek)|", "|  ( chip )   (o)  |", "|  (  icon  )      |", "|  ( chip )        |", "| (next panel peek)|"],
 "list": ["+------------------+", "|            (o)  |", "|  (o) [ Fedora  ] |", "|  (o) [ Windows ] |", "|  (o) [ Restart ] |", "+------[hints]-----+"],
}

def target_step():
    return {"id": "TARGET", "title": "Where to install", "type": "choice", "cur": 0, "options": [
        {"v": "grub", "label": "This computer's GRUB", "help": "Theme the GRUB boot menu of this machine (needs sudo; it changes /boot and /etc/grub.d, with backups)."},
        {"v": "ventoy", "label": "A Ventoy USB stick", "help": "Theme the menu of a Ventoy stick. Nothing on this computer changes; the files go onto the stick. The theme recognises ISOs by their file name, so you can add or remove ISOs later without installing again."}]}

def ventoy_steps(presets, monitors, sticks):
    def opt(v, label, help): return {"v": v, "label": label, "help": help}
    steps = []
    so = [opt(s["path"], describe_stick(s), "A Ventoy stick" + ("" if s["mounted"] else ": it is not mounted, the installer mounts it for the copy and unmounts it afterwards") + ". Everything is added under /ventoy; your ventoy.json is merged, not replaced (a backup is kept).") for s in sticks or []]
    so.append(opt("custom", "Type a mount point..." if sticks else "Type the stick's mount point...", "The folder where the Ventoy data partition is mounted, for example /run/media/you/Ventoy. It must be a Ventoy stick (a fresh one is fine)." + ("" if sticks else "\n\nNo Ventoy stick was detected: plug it in and mount it, or type the path.")))
    steps.append({"id": "STICK", "title": "Ventoy stick", "type": "choice", "options": so, "cur": 0})
    mons = monitors or [{"name": "default", "w": 1920, "h": 1080, "primary": False, "source": "default"}]
    ro = [opt(f"{m['w']}x{m['h']}", f"{m['w']}x{m['h']} {m['name']}" + (" (primary)" if m.get("primary") else ""), "The screen mode Ventoy starts in, and the first theme size. Pick the resolution of the screen you boot on most; the next step adds others for other computers.") for m in mons]
    ro.append(opt("custom", "Type another resolution...", "Enter WxH, for example 2560x1440. Sizes that are not built in use the closest theme."))
    steps.append({"id": "RES", "title": "Main resolution", "type": "choice", "options": ro, "cur": 0})
    steps.append({"id": "RESX", "title": "More resolutions", "type": "multi", "cur": 0, "rows": [
        {"id": r, "kind": "toggle", "label": r, "val": False, "help": "Add a theme for this size (about 8 to 14 MB). Ventoy switches to the matching theme when you change the resolution with F5 Tools -> Resolution Configuration."} for r in ("1280x720", "1920x1080", "2560x1440", "3840x2160")]})
    steps.append({"id": "STYLE", "title": "Style", "type": "choice", "cur": 0, "options": [
        opt("rail", "Full screen with a left rail", "A big hero panel for the selected ISO's distro and a small rail with three sections (Linux, Windows, Tools) on the left."),
        opt("clean", "Full screen, no rail", "A big panel per distro with label chips on the edges. The neighbour peeks only exist in snapshot mode."),
        opt("list", "Centred list", "The distro's logo and name on the left and the ISO list on the right, drawn by GRUB itself so it follows the files on the stick.")]})
    steps.append({"id": "SCHEME", "title": "Colour scheme", "type": "choice", "cur": 0, "options": [
        opt("dark", "Dark", "Deep Material 3 surfaces."), opt("light", "Light", "Light Material 3 surfaces.")]})
    steps.append({"id": "LOGO", "title": "Cookie and logo", "type": "choice", "cur": 0, "options": [
        opt("both", "Cookie with the logo", "The cookie shape at the top right with a static logo inside (a Material V mark; pass --logo FILE to the Ventoy tool for another image)."),
        opt("cookie", "Cookie only", "The cookie shape without the logo."), opt("none", "Neither", "No cookie and no logo.")]})
    steps.append({"id": "HINTS", "title": "Key hints", "type": "choice", "cur": 0, "options": [
        opt("on", "Show key hints", "Small pills at the bottom with Ventoy's keys: L Language, F1 Help, F2 Browse, F3 Tree, F4 Local boot, F5 Tools, F6 Ext menu."), opt("off", "No key hints", "Cleaner screen; the keys keep working.")]})
    steps.append({"id": "MODE", "title": "Mode", "type": "choice", "cur": 0, "options": [
        opt("dynamic", "Dynamic (recommended)", "Works with whatever ISOs are on the stick, now and later: add, remove or rename files on any computer and the theme follows. Trade-offs: in the list style the highlighted row is a neutral colour and the rows have no icons; no neighbour peeks in the clean style."),
        opt("snapshot", "Snapshot", "Draws the exact list (icons, colours, neighbours) for the ISOs that are on the stick right now. Run this installer again after changing the files; a file added later gets a plain list without highlight.")]})
    steps.append({"id": "EXTRAS", "title": "Extras", "type": "multi", "cur": 0, "rows": [
        {"id": "RAW_NAME", "kind": "toggle", "label": "Raw file name line", "val": True, "help": "The small muted line at the bottom with the ISO's file name exactly as Ventoy lists it."}]})
    return steps

def describe_stick(s):
    return (s["path"] if s["mounted"] else f"{s['dev']} (not mounted)") + (f"  {s['label']}" if s.get("label") else "")

def build_steps(presets, monitors, immutable, sticks=None):
    def opt(v, label, help): return {"v": v, "label": label, "help": help}
    if presets.get("TARGET") == "ventoy": return keep_open(ventoy_steps(presets, monitors, sticks), presets)
    steps = []
    mons = monitors or [{"name": "default", "w": 1920, "h": 1080, "primary": False, "source": "default"}]
    ro = []
    for i, m in enumerate(mons):
        tag = "primary monitor" if m.get("primary") else ("current GRUB setting" if m["source"] == "grub" else ("default" if m["source"] == "default" else "monitor"))
        ro.append(opt(f"{m['w']}x{m['h']}", f"{m['w']}x{m['h']} {m['name']}" + (" (primary)" if m.get("primary") else ""),
            f"GRUB draws on whichever output the firmware picks, usually the primary one, so use that monitor's native resolution.\n\nDetected via {m['source']}. Is this the screen you boot on? If not, pick another entry or type your own."))
    ro.append(opt("custom", "Type another resolution...", "Enter WxH, for example 2560x1440. Sizes that are not built in use the closest theme (same aspect ratio first); the native mode of your monitor looks best."))
    steps.append({"id": "RES", "title": "Resolution", "type": "choice", "options": ro, "cur": 0})
    steps.append({"id": "STYLE", "title": "Style", "type": "choice", "cur": 0, "options": [
        opt("rail", "Full screen with a left rail", "The default: a big hero panel for the selected entry and a rail of icons on the left, grouped Linux | Windows | System."),
        opt("clean", "Full screen, no rail", "The very first design: a big panel per entry, with the previous and next entry peeking in above and below in their own colours and small label chips on the edges."),
        opt("list", "Centered list", "The whole menu as a centred list: each entry is an icon in a Material shape plus its name in a pill; the selected row is highlighted and the background follows its colour.")]})
    steps.append({"id": "SCHEME", "title": "Colour scheme", "type": "choice", "cur": 0, "options": [
        opt("dark", "Dark", "Deep Material 3 surfaces, easy on the eyes in a dark room. This is the colour scheme baked into the scene images."),
        opt("light", "Light", "Light Material 3 surfaces. The scheme is chosen when the images are built, so switching later means installing again.")]})
    steps.append({"id": "LOGO", "title": "Cookie and firmware logo", "type": "choice", "cur": 0, "options": [
        opt("both", "Cookie with the firmware logo", "The cookie shape at the top right with your machine's own boot logo (from the firmware BGRT table) inside it."),
        opt("cookie", "Cookie only", "The cookie shape without the firmware logo."),
        opt("none", "Neither", "No cookie and no logo: the top right stays empty.")]})
    steps.append({"id": "HINTS", "title": "Key hints", "type": "choice", "cur": 0, "options": [
        opt("on", "Show key hints", "Small pills at the bottom: Arrows select, Enter boot, E edit, C console."),
        opt("off", "No key hints", "Cleaner screen; the keys keep working.")]})
    steps.append({"id": "EXTRAS", "title": "Extras", "type": "multi", "cur": 0, "rows": [
        {"id": "RAW_NAME", "kind": "toggle", "label": "Raw entry name line", "val": True, "help": "The small muted line at the bottom with the entry title exactly as GRUB sees it. Useful when something looks wrong."},
        {"id": "COUNTDOWN", "kind": "toggle", "label": "Countdown bar", "val": True, "help": "The 'Booting in N seconds' bar and label."},
        {"id": "TIMEOUT", "kind": "text", "label": "Timeout (seconds)", "val": "", "help": "Seconds before the default entry boots. Empty keeps GRUB_TIMEOUT (or 5). Press Enter to edit."}]})
    if immutable:
        steps.append({"id": "IMMUTABLE", "title": "Immutable system", "type": "choice", "cur": 1, "options": [
            opt("no", "Cancel", "Do not change anything."),
            opt("yes", "I understand, continue", "ostree/bootc layout (experimental, not tested on a real ostree boot): nothing under /usr; the static grub.cfg is edited (an untouched copy is kept in /var/backups/material-grub) and re-applied after 'bootupctl update'. Undo with ./install.sh --uninstall.")]})
    return keep_open(steps, presets)

def keep_open(steps, presets):
    """Drop the steps the installer flags already answered."""
    keep = []
    for st in steps:
        v = presets.get(st["id"])
        if st["id"] == "LOGO" and any(k in presets for k in ("COOKIE", "LOGO")): continue
        if st["id"] == "EXTRAS" and all(k in presets for k in ("RAW_NAME", "COUNTDOWN", "TIMEOUT")): continue
        if st["id"] == "EXTRAS" and presets.get("TARGET") == "ventoy" and "RAW_NAME" in presets: continue
        if st["id"] == "RESX" and "RESX" in presets: continue
        if v is not None and st["type"] == "choice": continue
        keep.append(st)
    return keep

def defaults(steps, presets):
    for st in steps:
        for p in (presets.get(st["id"]),):
            if p and st["type"] == "choice":
                for i, o in enumerate(st["options"]):
                    if o["v"] == p: st["cur"] = i

def value(st):
    if st["type"] == "choice": return st["options"][st["cur"]]["v"]
    return {r["id"]: r["val"] for r in st["rows"]}

def label(st):
    if st["type"] == "choice": return st["options"][st["cur"]]["label"]
    return ", ".join(f"{r['label'].split()[0].lower()} {'on' if r['val'] else 'off'}" if r["kind"] == "toggle" else f"timeout {r['val'] or 'default'}" for r in st["rows"])

def answers(steps, presets):
    a = {k: v for k, v in presets.items()}
    for st in steps:
        v = value(st)
        if st["id"] == "LOGO": a["COOKIE"] = "off" if v == "none" else "on"; a["LOGO"] = "on" if v == "both" else "off"
        elif st["id"] == "EXTRAS":
            a["RAW_NAME"] = "on" if v["RAW_NAME"] else "off"
            if "COUNTDOWN" in v: a["COUNTDOWN"] = "on" if v["COUNTDOWN"] else "off"; a["TIMEOUT"] = v["TIMEOUT"]
        elif st["id"] == "RESX": a["RESX"] = ",".join(r for r, on in v.items() if on)
        elif st["id"] == "STICK": a["STICK"] = v if v != "custom" else st.get("custom", "")
        elif st["id"] == "RES": a["RES"] = v if v != "custom" else st.get("custom", "1920x1080")
        else: a[st["id"]] = v
    if a.get("COOKIE") == "off": a["LOGO"] = "off"
    return a

CHECK = {"RES": RES_RE, "STYLE": re.compile(r"^(rail|clean|list)$"), "SCHEME": re.compile(r"^(dark|light)$"), "COOKIE": re.compile(r"^(on|off)$"), "LOGO": re.compile(r"^(on|off)$"),
         "HINTS": re.compile(r"^(on|off)$"), "RAW_NAME": re.compile(r"^(on|off)$"), "COUNTDOWN": re.compile(r"^(on|off)$"), "TIMEOUT": re.compile(r"^[0-9]{0,4}$"),
         "IMMUTABLE": re.compile(r"^(yes|no)$"), "TARGET": re.compile(r"^(grub|ventoy)$"), "MODE": re.compile(r"^(dynamic|snapshot)$"),
         "STICK": re.compile(r"^(dev:/dev/[A-Za-z0-9/_.-]+|/[^'\x00-\x1f]*)$"), "RESX": re.compile(r"^([0-9]{3,5}x[0-9]{3,5}(,[0-9]{3,5}x[0-9]{3,5})*)?$")}
def write_out(path, a):
    lines = []
    for k, v in a.items():
        if k not in CHECK or not CHECK[k].match(str(v)): raise ValueError(f"refusing to write {k}={v!r}")
        lines.append(f"{k}='{v}'")
    Path(path).write_text("\n".join(lines) + "\n")

def command_line(a):
    if a.get("TARGET") == "ventoy":
        res = ",".join(x for x in [a.get("RES", "")] + [r for r in a.get("RESX", "").split(",") if r and r != a.get("RES")] if x); stick = a.get("STICK", "")
        c = ["./install.sh", "--ventoy", "'" + stick + "'" if stick else "", f"--res {res}" if res else "", f"--style {a['STYLE']}" if "STYLE" in a else "", f"--scheme {a['SCHEME']}" if "SCHEME" in a else "",
             "--mode snapshot" if a.get("MODE") == "snapshot" else ""]
        if a.get("COOKIE") == "off": c.append("--no-cookie")
        elif a.get("LOGO") == "off": c.append("--no-logo")
        if a.get("HINTS") == "off": c.append("--no-hints")
        return " ".join(x for x in c if x)
    c = ["sudo ./install.sh", f"--res {a['RES']}" if "RES" in a else "", f"--style {a['STYLE']}" if "STYLE" in a else "", f"--scheme {a['SCHEME']}" if "SCHEME" in a else ""]
    if a.get("COOKIE") == "off": c.append("--no-cookie")
    elif a.get("LOGO") == "off": c.append("--no-logo")
    if a.get("HINTS") == "off": c.append("--no-hints")
    return " ".join(x for x in c if x)

def summary_lines(steps, a):
    out = [f"{st['title']:<26} {label(st)}" for st in steps]
    if "RES" in a and snap(a["RES"]) != a["RES"]: out.append(f"(theme used for {a['RES']}: {snap(a['RES'])}, the closest built-in size)")
    return out

# ----------------------------------------------------------------- plain prompts
def run_plain(steps, presets, inp=input, out=print, final=True):
    out("Material GRUB installer: answer the questions (Enter keeps the default shown in [ ]).")
    i = 0
    while i < len(steps):
        st = steps[i]; out(f"\n[{i + 1}/{len(steps)}] {st['title']}")
        if st["type"] == "choice":
            for n, o in enumerate(st["options"], 1): out(f"  {n}) {o['label']}{'  [default]' if n - 1 == st['cur'] else ''}\n       {textwrap.shorten(o['help'], 150)}")
            while True:
                r = inp("  choice: ").strip()
                if not r: break
                if r.isdigit() and 1 <= int(r) <= len(st["options"]): st["cur"] = int(r) - 1; break
                out("  please type one of the numbers")
            if st["options"][st["cur"]]["v"] == "custom":
                while True:
                    r = inp("  mount point of the Ventoy stick: " if st["id"] == "STICK" else "  resolution WxH: ").strip()
                    if st["id"] == "STICK" and stick_ok(r) or st["id"] != "STICK" and RES_RE.match(r): st["custom"] = r; break
                    out("  expected the mount point of a Ventoy data partition" if st["id"] == "STICK" else "  expected WxH, for example 2560x1440")
        else:
            for r in st["rows"]:
                if r["kind"] == "toggle": x = inp(f"  {r['label']} [{'Y/n' if r['val'] else 'y/N'}]: ").strip().lower(); r["val"] = r["val"] if not x else x.startswith("y")
                else:
                    while True:
                        x = inp(f"  {r['label']} [{r['val'] or 'default'}]: ").strip()
                        if x == "" or x.isdigit(): r["val"] = x or r["val"]; break
        i += 1
    if not final: return answers(steps, presets)
    a = answers(steps, presets); out("\nSummary:"); [out("  " + l) for l in summary_lines(steps, a)]
    out("Equivalent command: " + command_line(a))
    if any(s["id"] == "IMMUTABLE" and value(s) == "no" for s in steps): return None
    return a if inp("Install now? [Y/n] ").strip().lower() in ("", "y", "yes") else None

# ----------------------------------------------------------------- curses
def run_curses(steps, presets, summary_screen=True):
    import curses
    def main(scr):
        curses.curs_set(0); scr.keypad(True); i = 0; msg = ""
        def box(y, x, h, w, title=""):
            scr.addstr(y, x, "+" + "-" * (w - 2) + "+"); scr.addstr(y + h - 1, x, "+" + "-" * (w - 2) + "+")
            for r in range(1, h - 1): scr.addstr(y + r, x, "|"); scr.addstr(y + r, x + w - 1, "|")
            if title: scr.addstr(y, x + 2, f" {title} "[: w - 4], curses.A_BOLD)
        def put(y, x, s, attr=0, w=None):
            try: scr.addstr(y, x, s[: w] if w else s, attr)
            except curses.error: pass
        def edit(prompt, check, init=""):
            buf = init; curses.curs_set(1); h, w = scr.getmaxyx()
            while True:
                put(h - 4, 2, " " * (w - 4)); put(h - 4, 2, f"{prompt} {buf}", curses.A_BOLD, w - 4); scr.refresh(); k = scr.getch()
                if k in (10, 13, curses.KEY_ENTER) and check(buf): curses.curs_set(0); return buf
                if k == 27: curses.curs_set(0); return None
                if k in (curses.KEY_BACKSPACE, 127, 8): buf = buf[:-1]
                elif 32 <= k < 127: buf += chr(k)
        while True:
            h, w = scr.getmaxyx(); scr.erase()
            if h < 24 or w < 80: put(0, 0, "Please enlarge the terminal to at least 80x24 (q quits)."); scr.refresh(); k = scr.getch()
            else:
                n = len(steps); summary = i >= n; box(0, 0, h - 1, w, "Material GRUB installer")
                TAB = {"TARGET": "Target", "STICK": "Stick", "RESX": "More res", "MODE": "Mode", "RES": "Res", "STYLE": "Style", "SCHEME": "Scheme", "LOGO": "Logo", "HINTS": "Hints", "EXTRAS": "Extras", "SOURCE": "Source", "IMMUTABLE": "Immut."}
                tabs = [f"[{'x' if j < i else '>' if j == i else ' '}]{TAB.get(st['id'], st['title'])}" for j, st in enumerate(steps)] + [f"[{'>' if summary else ' '}]Summary"]
                x = 2
                for j, t in enumerate(tabs): put(1, x, t, curses.A_REVERSE if j == min(i, n) else (0 if j < i else curses.A_DIM), w - x - 1); x += len(t) + 1
                put(2, 1, "-" * (w - 2)); lw = max(36, (w - 2) * 5 // 11); put(2, lw, "+")
                for r in range(3, h - 3): put(r, lw, "|")
                put(h - 3, 1, "-" * (w - 2)); put(h - 3, lw, "+")
                a = answers(steps, presets)
                if not summary:
                    st = steps[i]; put(3, 2, f"{i + 1}/{n}  {st['title']}", curses.A_BOLD)
                    if st["type"] == "choice":
                        for j, o in enumerate(st["options"]): put(5 + j, 3, f"({'o' if j == st['cur'] else ' '}) {o['label']}", curses.A_BOLD if j == st["cur"] else 0, lw - 4)
                        o = st["options"][st["cur"]]; ctitle, ctext = o["label"], o["help"]
                        if st["id"] == "RES" and o["v"] != "custom": ctext += f"\n\nTheme used: {snap(o['v'])}" if snap(o["v"]) != o["v"] else ""
                        if st["id"] == "RES" and o["v"] == "custom" and st.get("custom"): ctext += f"\n\nEntered: {st['custom']} (theme {snap(st['custom'])})"
                    else:
                        for j, r in enumerate(st["rows"]):
                            put(5 + j, 3, (f"[{'x' if r['val'] else ' '}] " if r["kind"] == "toggle" else "    ") + r["label"] + ("" if r["kind"] == "toggle" else f": {r['val'] or 'default'}"), curses.A_BOLD if j == st["cur"] else 0, lw - 4)
                        r = st["rows"][st["cur"]]; ctitle, ctext = r["label"], r["help"] + ("  (Space toggles)" if r["kind"] == "toggle" else "")
                    cx, cw = lw + 2, w - lw - 4; box(3, cx, h - 7, cw, ctitle); yy = 4
                    wire = WIRE.get(o["v"]) if st["id"] == "STYLE" else None
                    for line in (wire or []): put(yy, cx + 2, line, 0, cw - 4); yy += 1
                    if wire: yy += 1
                    for para in ctext.split("\n"):
                        for line in textwrap.wrap(para, cw - 4) or [""]:
                            if yy < h - 5: put(yy, cx + 2, line, 0, cw - 4); yy += 1
                else:
                    put(3, 2, "Summary", curses.A_BOLD); yy = 5
                    for l in summary_lines(steps, a): put(yy, 3, l, 0, w - 6); yy += 1
                    put(yy + 1, 3, "Equivalent command:", curses.A_DIM); put(yy + 2, 3, command_line(a), 0, w - 6)
                    put(h - 5, 3, "Enter = install    Left = back    q = quit without changes", curses.A_BOLD, w - 6)
                put(h - 2, 2, msg or ("Up/Down choose  Enter next  Left back  Tab next tab  q quit" if not summary else "Enter install  Left back  q quit"), curses.A_DIM, w - 4); msg = ""
                scr.refresh(); k = scr.getch()
            if k in (ord("q"), 27): return None
            if k == curses.KEY_RESIZE: continue
            if i >= len(steps) or (not summary_screen and i == len(steps) - 1 and k in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT)):
                if k in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT): return answers(steps, presets)
                if k in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127): i = len(steps) - 1
                continue
            st = steps[i]; key = k
            if st["type"] == "choice":
                if key in (curses.KEY_UP, ord("k")): st["cur"] = (st["cur"] - 1) % len(st["options"])
                elif key in (curses.KEY_DOWN, ord("j")): st["cur"] = (st["cur"] + 1) % len(st["options"])
                elif key in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT):
                    if st["options"][st["cur"]]["v"] == "custom":
                        r = edit("Mount point of the Ventoy stick:", stick_ok, st.get("custom", "")) if st["id"] == "STICK" else edit("Resolution WxH:", lambda b: bool(RES_RE.match(b)), st.get("custom", ""))
                        if r is None: continue
                        st["custom"] = r
                    if st["id"] == "IMMUTABLE" and value(st) == "no": return None
                    i += 1
            else:
                rows = st["rows"]
                if key in (curses.KEY_UP, ord("k")): st["cur"] = (st["cur"] - 1) % len(rows)
                elif key in (curses.KEY_DOWN, ord("j")): st["cur"] = (st["cur"] + 1) % len(rows)
                elif key == ord(" ") and rows[st["cur"]]["kind"] == "toggle": rows[st["cur"]]["val"] = not rows[st["cur"]]["val"]
                elif key in (10, 13, curses.KEY_ENTER) and rows[st["cur"]]["kind"] == "text":
                    r = edit("Timeout seconds (empty = default):", lambda b: b == "" or b.isdigit(), rows[st["cur"]]["val"])
                    if r is not None: rows[st["cur"]]["val"] = r
                elif key in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT): i += 1
            if key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127) and i > 0: i -= 1
            if key == 9 and i < len(steps): i += 1
            if key == curses.KEY_BTAB and i > 0: i -= 1
    return curses.wrapper(main)

def main(argv):
    def arg(n, d=None): return argv[argv.index(n) + 1] if n in argv else d
    presets = {}
    for i, a in enumerate(argv):
        if a == "--preset" and "=" in argv[i + 1]: k, v = argv[i + 1].split("=", 1); presets[k] = v
    out = arg("--out"); mons = None
    plain = "--plain" in argv or not sys.stdin.isatty() or not sys.stdout.isatty() or os.environ.get("TERM", "dumb") in ("dumb", "")
    if not plain:
        try: import curses
        except ImportError: plain = True
    sticks = json.loads(Path(arg("--sticks")).read_text()) if arg("--sticks") else None
    try:
        if "--ask-target" in argv and "TARGET" not in presets:
            a1 = run_plain([target_step()], presets, final=False) if plain else run_curses([target_step()], presets, summary_screen=False)
            if a1 is None: return 1
            presets["TARGET"] = a1["TARGET"]
    except (KeyboardInterrupt, EOFError): return 1
    if arg("--monitors"): mons = json.loads(Path(arg("--monitors")).read_text())
    if mons is None and "RES" not in presets:
        try: import monitors; mons = monitors.detect()
        except Exception: mons = None
    if presets.get("TARGET") == "ventoy" and sticks is None and "STICK" not in presets:
        try: import ventoy_sticks; sticks = ventoy_sticks.detect()
        except Exception: sticks = []
    steps = build_steps(presets, mons, "--immutable" in argv, sticks); defaults(steps, presets)
    if "COOKIE" in presets and "LOGO" not in presets: presets.setdefault("LOGO", "on")
    try: a = run_plain(steps, presets) if plain else run_curses(steps, presets)
    except (KeyboardInterrupt, EOFError): a = None
    except Exception as e:
        if plain: raise
        print(f"material-grub: the TUI failed ({e}); falling back to plain prompts", file=sys.stderr); a = run_plain(steps, presets)
    if a is None: return 1
    if out: write_out(out, a)
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
