"""material-grub preview: render the menu scenes for the chosen style, scheme and resolution as a web page. No root, no VM, nothing installed.

Reads the real boot entries read-only (grub.cfg, else /boot/loader/entries; a sample list when neither is readable), renders every scene with
the same code the installer uses into a scratch directory, and writes a self-contained HTML contact sheet plus the PNGs.
It is a render of the scenes, not GRUB itself: how the real GRUB menu behaves is tested by the QEMU jobs in CI.

usage: material-grub preview [--pkg DIR] [--res WxH] [--style rail|clean|list|split] [--out DIR] [--sample] [--no-open]
"""

import base64
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

import grubscript
import mgrub

SAMPLE_CFG = """menuentry 'Fedora Linux (7.3.3-200.fc44.x86_64) 44 (Workstation Edition)' --class fedora --class gnu-linux --class os { true }
submenu 'Advanced options for Fedora Linux' --class fedora {
\tmenuentry 'Fedora Linux (7.2.11-200.fc44.x86_64) 44 (Workstation Edition)' --class fedora { true }
\tmenuentry 'Fedora Linux (0-rescue-1657f3fb24ae) 44 (Workstation Edition)' --class fedora { true }
}
menuentry 'Windows Boot Manager (on /dev/nvme0n1p1)' --class windows --class os { true }
menuentry 'Ubuntu 24.04.1 LTS (on /dev/sda5)' --class ubuntu --class gnu-linux --class os { true }
menuentry 'Ubuntu 22.04.5 LTS (on /dev/nvme0n1p3)' --class ubuntu --class gnu-linux --class os { true }
menuentry 'UEFI Firmware Settings' --class efi { true }
menuentry 'Restart' --class restart { reboot }
menuentry 'Shut down' --class shutdown { halt }
"""


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def entries_to_cfg(text):
    """A scratch grub.cfg that keeps only the menu structure (titles, classes, submenus) of a real one."""
    sc = grubscript.scan(text)
    out = []

    def q(s):
        return "'" + s.replace("'", "'\\''") + "'"

    def emit(parent, depth):
        for e in sc.entries:
            if e.parent is not parent:
                continue
            ind = "\t" * depth
            cls = "".join(f" --class {c}" for c in e.classes)
            if e.word == "submenu":
                out.append(f"{ind}submenu {q(e.title)}{cls} {{")
                emit(e, depth + 1)
                out.append(f"{ind}}}")
            else:
                out.append(f"{ind}menuentry {q(e.title)}{cls} {{ true }}")

    emit(None, 0)
    return "\n".join(out) + "\n"


def gather(work, sample):
    """Write the scratch grub.cfg and BLS entries; returns a note saying where the entries came from."""
    cfg = work / "grub.cfg"
    entries = work / "entries"
    entries.mkdir()
    if sample:
        cfg.write_text(SAMPLE_CFG)
        return "sample entries (--sample)"
    note, text = "", ""
    for f in ("/boot/grub2/grub.cfg", "/boot/grub/grub.cfg"):
        try:
            text = Path(f).read_text(errors="replace")
            note = f
            break
        except OSError:
            continue
    bls = Path("/boot/loader/entries")
    try:
        confs = sorted(bls.glob("*.conf"))
        for c in confs:
            shutil.copy(c, entries / c.name)
    except OSError:
        confs = []
    if text:
        body = entries_to_cfg(text)
        if "blscfg" in text and confs:
            body += "blscfg\n"
        if grubscript.scan(body).entries or confs:
            cfg.write_text(body)
            return f"your entries from {note}" + (f" and {len(confs)} boot loader entries" if confs else "")
    if confs:
        cfg.write_text("blscfg\n")
        return f"{len(confs)} boot loader entries from /boot/loader/entries"
    cfg.write_text(SAMPLE_CFG)
    return "sample entries (grub.cfg and /boot/loader/entries are not readable: run with sudo to see your own)"


def scene_for(theme, e, classes):
    cls = e.get("class", "")
    if cls.startswith("mg_") and (theme / "icons" / f"{cls}.png").is_file():
        return theme / "icons" / f"{cls}.png"
    names = classes.get(e.get("key"), [e.get("key")])
    p = theme / "icons" / f"{names[0]}.png"
    return p if p.is_file() else None


def thumb(path, width):
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im = im.resize((width, max(1, im.height * width // im.width)))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def page(cards, meta):
    items = "\n".join(
        f'<figure><img alt="{html.escape(t)}" src="data:image/png;base64,{b}"><figcaption><b>{html.escape(t)}</b><br><small>{html.escape(sub)}</small></figcaption></figure>'
        for t, sub, b in cards
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Material GRUB preview</title>
<style>
:root{{color-scheme:light dark;--bg:#fafafa;--fg:#1b1b1f;--card:#fff;--line:#d9d9e0}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141418;--fg:#e4e1e9;--card:#1d1d22;--line:#36363d}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1500px;margin:auto}}h1{{font-size:1.4rem;margin:0 0 4px}}p{{max-width:70ch}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,420px),1fr));gap:16px;margin-top:20px}}
figure{{margin:0;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
img{{display:block;width:100%;height:auto}}figcaption{{padding:10px 14px}}small{{opacity:.7}}
.note{{border-left:4px solid var(--line);padding:4px 12px;opacity:.85}}
</style><main>
<h1>Material GRUB preview</h1>
<p>{html.escape(meta)}</p>
<p class="note">This is a render of the scenes with the installer's own drawing code, not GRUB itself. How the real GRUB menu behaves (keys, timing, fonts it loads) is tested in QEMU by the project's CI. Nothing was installed or changed on this computer.</p>
<div class="grid">{items}</div></main></html>"""


def main(argv=None):
    pkg = Path(arg("--pkg", os.environ.get("MATERIAL_PKG", "/usr/share/material-grub")))
    if not (pkg / "res").is_dir():
        sys.exit(
            f"material-grub preview: {pkg} is not a theme package (build one with ./install.sh --preview, or pass --pkg DIR)"
        )
    res = arg("--res") or "1920x1080"
    avail = sorted(p.name for p in (pkg / "res").iterdir())
    res = mgrub.snap(res, avail)
    scheme = (pkg / "scheme.txt").read_text().strip() if (pkg / "scheme.txt").is_file() else "dark"
    out = Path(arg("--out") or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "material-grub-preview")
    work = Path(tempfile.mkdtemp(prefix="material-grub-preview."))
    try:
        note = gather(work, "--sample" in sys.argv)
        conf = work / "material-grub.conf"
        base = Path("/etc/material-grub.conf")
        text = base.read_text() if base.is_file() else ""
        if arg("--style"):
            text += f"\nSTYLE={arg('--style')}\n"
        conf.write_text(text)
        env = dict(os.environ, MATERIAL_CONF=str(conf), MATERIAL_STATE_DIR=str(work / "state"), MG_PREVIEW_LOGO="1")
        theme = work / "theme"
        state = work / "state/entries.json"

        def run(cmd):
            subprocess.run([sys.executable, *map(str, cmd)], env=env, check=True, stdout=subprocess.DEVNULL)

        run([pkg / "bin/material-grub-assemble", "--mode", res, "--pkg", pkg, "--out", theme])
        run(
            [
                pkg / "bin/material-grub-classes",
                work / "grub.cfg",
                "--pkg",
                pkg,
                "--bls",
                work / "entries",
                "--loader",
                work / "loader",
                "--mirrors",
                work / "mirrors",
                "--blsbase",
                "/loader",
                "--state",
                state,
            ]
        )
        run([pkg / "bin/material-grub-scenes", "--theme", theme, "--pkg", pkg, "--state", state])
        entries = json.loads(state.read_text())
        classes = json.loads((pkg / "classes.json").read_text())
        menu = json.loads(state.with_name("menu.json").read_text())
        by_class = {e["class"]: e for e in entries}
        order = [c for lvl in menu for c in lvl["items"] if c in by_class] or [e["class"] for e in entries]
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        cards, n = [], 0
        for c in order:
            e = by_class[c]
            src = scene_for(theme, e, classes)
            if src is None:
                continue
            n += 1
            name = f"{n:02d}-{re.sub(r'[^A-Za-z0-9]+', '-', e['title']).strip('-')[:50]}.png"
            shutil.copy(src, out / name)
            where = f" on {e['where']}" if e.get("where") else ""
            cards.append((e["title"], f"{e['kind']}{where} · {name}", thumb(src, 900)))
        style = mgrub.load_conf(str(conf))["STYLE"]
        meta = f"{len(cards)} menu entries from {note}, style {style}, {scheme} scheme, {res} theme."
        (out / "index.html").write_text(page(cards, meta))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"material-grub preview: {len(cards)} scenes written to {out}")
    print(f"  open {out / 'index.html'}")
    if "--no-open" not in sys.argv and (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sys.platform == "darwin"
    ):
        webbrowser.open((out / "index.html").as_uri())
    return 0
