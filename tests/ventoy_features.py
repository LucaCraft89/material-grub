#!/usr/bin/env python3
"""Real Ventoy 1.1.18 in QEMU + OVMF with the 0.7 customisations: per-image colour, icon and name (and the single-colour mode) on the stick, in both Ventoy styles and
both modes, plus the same customisation made through the GUI in Chrome, written to the stick by the GUI and booted. Checks what Ventoy really draws.
usage: python3 tests/ventoy_features.py SCENARIO     SCENARIO: list-dynamic | full-dynamic | list-snapshot | single | gui
Needs what tests/ventoy_smoke.py needs (qemu, OVMF, mtools, Pillow, dist/material-grub 1920x1080 dark, Ventoy cached or downloadable); `gui` also Playwright + Chrome.
Screenshots: build/ventoy-feature-shots/."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "install/bin"))
import mgpalette  # noqa: E402
import ventoy_smoke as V  # noqa: E402

PKG = V.PKG
OUT = ROOT / "build/ventoy-feature-shots"
ISOS = (
    "Fedora-Workstation-Live-x86_64-44-1.7.iso",
    "ubuntu-24.04.1-desktop-amd64.iso",
    "Win11_24H2_English_x64.iso",
)  # Ventoy lists them in this order
dark = (PKG / "scheme.txt").read_text().strip() != "light"
pal = json.loads((PKG / "palettes.json").read_text())


def surf(seed):
    return V.hexc(mgpalette.scheme(seed, dark)["surface"])


def surface_of(img):
    return img.getpixel((img.width - 3, 3))  # the scene's own background, outside the cookie


def make_stage(work, style, mode):
    """A stick folder themed by the installer (no overrides yet)."""
    stage = work / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "ventoy").mkdir(parents=True)
    (stage / "ISO").mkdir()
    for n in ISOS:
        (stage / "ISO" / n).write_bytes(b"\0" * V.MIB)
    r = subprocess.run(
        [
            "sh",
            str(ROOT / "install.sh"),
            "--ventoy",
            str(stage),
            "--pkg",
            str(PKG),
            "--res",
            "1920x1080",
            "--style",
            style,
            "--mode",
            mode,
            "--scheme",
            "dark",
            "--yes",
            "--no-tui",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        sys.exit("installer failed:\n" + r.stdout + r.stderr)
    return stage


def retheme(stage):
    """Re-run the Ventoy tool on the stick (what `material-boot grub ventoy` does) after the overrides changed."""
    r = subprocess.run(
        [sys.executable, str(PKG / "bin/material-grub-ventoy"), str(stage), "--pkg", str(PKG), "--res", "1920x1080"],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        sys.exit("material-grub-ventoy failed:\n" + r.stdout + r.stderr)


def boot_stage(stage, work, n=3, name="stick"):
    img = work / f"{name}.img"
    img.unlink(missing_ok=True)
    V.make_stick(img)
    subprocess.run(["mcopy", "-s", "-i", f"{img}@@1M", *map(str, stage.iterdir()), "::/"], check=True)
    return V.boot(img, n)


def save(shots, scenario):
    OUT.mkdir(parents=True, exist_ok=True)
    for i, im in enumerate(shots):
        im.save(OUT / f"{scenario}-{i + 1}.png")


def row_region(img):
    W, H = img.size
    x0, y0, w, h = round(W * 0.47), round(110 * H / 1080), round(640 * H / 1080), round(76 * H / 1080)
    return img.crop((x0, y0, x0 + w, y0 + h))


def ink_pixels(img, color, side_hero):
    """How many pixels of the title band (the hero's name: left of the list in the list style, under the logo in the full-screen one) are in `color`."""
    W, H = img.size
    box = (
        (round(W * 0.04), round(640 * H / 1080), round(W * 0.46), round(820 * H / 1080))
        if side_hero
        else (round(W * 0.2), round(520 * H / 1080), round(W * 0.8), round(700 * H / 1080))
    )
    return sum(1 for px in img.crop(box).getdata() if all(abs(a - b) <= 14 for a, b in zip(px, color)))


def row1_text_width(img):
    """Width of the bright text in the first row of the baked list (snapshot list): the file name is long, a custom name is short."""
    box = (745, 415, 1250, 470)
    bg = img.getpixel((1262, 444))  # the row's own colour, right of the text
    xs = [
        x
        for x in range(box[2] - box[0])
        for y in range(box[3] - box[1])
        if sum(abs(a - b) for a, b in zip(img.getpixel((box[0] + x, box[1] + y)), bg)) > 150
    ]
    return (max(xs) - min(xs)) if xs else 0


def same_pixels(a, b):
    from PIL import ImageChops

    return ImageChops.difference(a, b).getbbox() is None


def custom_overrides(stage):
    from PIL import Image

    d = stage / "ventoy/material-grub-icons"
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (96, 96), (30, 160, 30, 255)).save(d / "logo.png")
    (stage / "ventoy/material-grub-overrides.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {"match": {"title": "Fedora"}, "name": "Work laptop", "color": "#E95420", "icon": "file:logo.png"}
                ],
            }
        )
    )


def check_custom(scenario, stage, shots, baseline=None):
    fail = []
    want = surf("#E95420")
    if surface_of(shots[0]) != want:
        fail.append(f"Fedora should be drawn in the custom colour {want}, got {surface_of(shots[0])}")
    for i, key in ((1, "ubuntu"), (2, "windows11")):
        w = V.hexc(pal[key]["surface"])
        if surface_of(shots[i]) != w:
            fail.append(f"{ISOS[i]} should keep the {key} colour {w}, got {surface_of(shots[i])}")
    vj = json.loads((stage / "ventoy/ventoy.json").read_text())
    if not vj["menu_class"][0]["class"].startswith("mgu_"):
        fail.append("the customised file has no mgu_ rule first in menu_class")
    if {"image": f"/ISO/{ISOS[0]}", "alias": "Work laptop"} not in vj.get("menu_alias", []):
        fail.append("menu_alias for the renamed image is missing")
    ink = V.hexc(mgpalette.scheme("#E95420", dark)["primary"])
    if scenario != "list-snapshot" and ink_pixels(shots[0], ink, "list" in scenario or "gui" in scenario) < 3000:
        fail.append("the custom name is not drawn in the custom colour on the scene (no title ink found)")
    if baseline is not None and ink_pixels(baseline, ink, "list" in scenario) > 200:
        fail.append("the baseline already had the custom colour")
    if scenario == "list-snapshot" and baseline is not None:
        a, b = row1_text_width(baseline), row1_text_width(shots[0])
        if not (a > 300 and 0 < b < a * 0.75):
            fail.append(
                f"the first row should show the short name 'Work laptop' instead of the file name (text width {b} vs {a})"
            )
    return fail


def run_scenario(name):
    work = Path(tempfile.mkdtemp())
    fail = []
    try:
        if name in ("list-dynamic", "full-dynamic", "list-snapshot"):
            style, mode = name.split("-")
            stage = make_stage(work, style, mode)
            base = boot_stage(stage, work, 1, "base")  # before: no overrides
            save(base, name + "-before")
            custom_overrides(stage)
            retheme(stage)
            shots = boot_stage(stage, work, 3)
            save(shots, name)
            fail += check_custom(name, stage, shots, base[0])
        elif name == "single":
            stage = make_stage(work, "list", "dynamic")
            (stage / "ventoy/material-grub-overrides.json").write_text(
                json.dumps({"version": 1, "seed": {"mode": "single", "color": "#7E57C2"}})
            )
            retheme(stage)
            shots = boot_stage(stage, work, 3)
            save(shots, name)
            want = surf("#7E57C2")
            for i, im in enumerate(shots):
                if surface_of(im) != want:
                    fail.append(f"{ISOS[i]}: the single-colour stick should be {want}, got {surface_of(im)}")
        elif name == "gui":
            fail += run_gui(work)
        else:
            sys.exit("unknown scenario " + name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return fail


def run_gui(work):
    """Customise the stick in the GUI (Chrome), let the GUI write it, then boot what it wrote."""
    from playwright.sync_api import expect, sync_playwright

    def find_browser():
        for c in (
            os.environ.get("GUI_BROWSER"),
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ):
            if c and os.path.exists(c):
                return c
        sys.exit("no Chrome or Chromium found (set GUI_BROWSER=/path/to/chrome)")

    stage = make_stage(work, "list", "dynamic")
    from PIL import Image

    picture = work / "my-logo.png"
    Image.new("RGBA", (96, 96), (30, 160, 30, 255)).save(picture)
    tmp = work / "guistate"
    (tmp / "state").mkdir(parents=True)
    os.environ.update(
        {
            "MATERIAL_PKG": str(PKG),
            "MATERIAL_GRUB_PKG": str(PKG),  # the editor draws the stick with GRUB's built package
            "MATERIAL_GRUB_MODULES": str(ROOT / "install/bin"),
            "MATERIAL_STATE_DIR": str(tmp / "state"),
            "MATERIAL_CONF": str(tmp / "mg.conf"),
            "MATERIAL_OVERRIDES": str(tmp / "overrides.json"),
            "XDG_CONFIG_HOME": str(tmp / "cfg"),
            "XDG_CACHE_HOME": str(tmp / "cache"),
        }
    )
    core = os.environ.get("MATERIAL_LIB") or str(
        ROOT / "material-boot-core"
    )  # the editor is the core's (material_boot/ui)
    sys.path.insert(0, core)
    os.environ.setdefault(
        "MATERIAL_DATA", str(PKG)
    )  # the built GRUB package has the same palettes, classes and fonts as the shared data
    from material_boot.ui import server as mgserver

    srv = mgserver.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.app.port}/?t={srv.app.token}"
    OUT.mkdir(parents=True, exist_ok=True)
    fail = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=find_browser(), headless=True, args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_selector(".nav")
        page.get_by_role("button", name="Ventoy").first.click()
        page.get_by_label("Mount point of the stick").fill(str(stage))
        page.get_by_role("button", name="Open", exact=True).click()
        expect(page.locator(".entry", has_text=ISOS[0])).to_be_visible()
        page.locator(".entry", has_text=ISOS[0]).click()
        ed = page.locator("section.card.high")
        name = ed.locator("input[type=text]").first
        name.fill("Work laptop")
        name.press("Tab")
        ed.locator(".swatch[aria-label='Tangerine']").click()
        ed.locator("input[type=file]").set_input_files(str(picture))
        expect(ed.locator(".icon-cell[aria-pressed='true'] img")).to_be_visible()  # the uploaded picture is selected
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "gui-editor.png"))
        page.get_by_role("button", name="Write to the stick", exact=True).click()
        expect(page.locator("dialog[open] .steps")).to_contain_text("The stick is themed", timeout=180000)
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "gui-written.png"))
        page.get_by_role("button", name="Close", exact=True).click()
        if errors:
            fail.append("browser errors: " + "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    srv.app.close()
    ov = json.loads((stage / "ventoy/material-grub-overrides.json").read_text())
    rule = ov["entries"][0] if ov["entries"] else {}
    if not (
        rule.get("name") == "Work laptop"
        and rule.get("color") == "#E95420"
        and str(rule.get("icon", "")).startswith("file:")
    ):
        fail.append(f"the GUI did not write the expected rule: {rule}")
    if not list((stage / "ventoy/material-grub-icons").glob("*.png")):
        fail.append("the uploaded picture is not on the stick")
    shots = boot_stage(stage, work, 3)
    save(shots, "gui")
    fail += check_custom("gui", stage, shots)
    return fail


if __name__ == "__main__":
    for tool in ("qemu-system-x86_64", "mformat", "mcopy", "mdel"):
        if not shutil.which(tool):
            sys.exit(f"skipped: {tool} not found")
    if not V.OVMF:
        sys.exit("skipped: OVMF firmware not found")
    scenario = sys.argv[1] if len(sys.argv) > 1 else "list-dynamic"
    problems = run_scenario(scenario)
    if problems:
        sys.exit(f"VENTOY FEATURES FAILED ({scenario}):\n  " + "\n  ".join(problems))
    print(f"ventoy features ok ({scenario}): shots in {OUT}")
