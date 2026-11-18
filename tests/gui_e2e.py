"""The GUI in a real browser (Playwright + Chrome/Chromium), end to end: every page, the live preview, drag and drop, per-entry edits, one colour, presets,
Apply (through the real privileged helper in a scratch root, with a fake `material-grub apply`), a failing Apply, Ventoy, the update page, the responsive
layout, dark and light, and the browser-side security. Saves screenshots to build/gui-shots/.
usage: python3 tests/gui_e2e.py      Needs: pip install playwright, a Chrome or Chromium (GUI_BROWSER=/path overrides), dist/material-grub, Pillow."""

import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
SHOTS = ROOT / "build/gui-shots"
ENTRIES = [
    {
        "class": "mg_aaaaaaaa01",
        "key": "fedora",
        "kind": "kernel",
        "level": "top",
        "title": "Fedora Linux (7.3.3-200.fc44.x86_64) 44",
        "kver": "7.3.3-200.fc44.x86_64",
    },
    {
        "class": "mg_aaaaaaaa02",
        "key": "fedora",
        "kind": "advanced",
        "level": "top",
        "title": "Advanced options for Fedora Linux",
    },
    {
        "class": "mg_aaaaaaaa03",
        "key": "windows11",
        "kind": "plain",
        "level": "top",
        "title": "Windows Boot Manager (on /dev/nvme0n1p1)",
    },
    {"class": "mg_aaaaaaaa04", "key": "arch", "kind": "plain", "level": "top", "title": "Arch Linux"},
    {
        "class": "mg_aaaaaaaa05",
        "key": "ubuntu",
        "kind": "plain",
        "level": "top",
        "title": "Ubuntu 24.04.1 LTS (on /dev/sda5)",
    },
    {"class": "mg_aaaaaaaa06", "key": "firmware", "kind": "plain", "level": "top", "title": "UEFI Firmware Settings"},
    {"class": "mg_aaaaaaaa07", "key": "reboot", "kind": "plain", "level": "top", "title": "Restart"},
    {"class": "mg_aaaaaaaa08", "key": "shutdown", "kind": "plain", "level": "top", "title": "Shut down"},
]


def find_browser():
    for c in (
        os.environ.get("GUI_BROWSER"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ):
        if c and os.path.exists(c):
            return c
    sys.exit("no Chrome or Chromium found (set GUI_BROWSER=/path/to/chrome)")


def main():
    from playwright.sync_api import expect, sync_playwright

    tmp = Path(tempfile.mkdtemp())
    (tmp / "state").mkdir()
    (tmp / "state/entries.json").write_text(json.dumps(ENTRIES))
    (tmp / "state/menu.json").write_text(json.dumps([{"level": "top", "items": [e["class"] for e in ENTRIES]}]))
    (tmp / "mg.conf").write_text("STYLE=rail\n")
    fake = tmp / "apply.sh"
    fake.write_text(
        "#!/bin/sh\necho 'Generating grub configuration file ...'\nsleep ${FAKE_APPLY_SLEEP:-3}\necho done\nexit ${FAKE_APPLY_RC:-0}\n"
    )
    fake.chmod(0o755)
    stick = tmp / "stick"
    (stick / "ventoy").mkdir(parents=True)
    (stick / "ISO").mkdir()
    for n in ("Fedora-Workstation-44.iso", "ubuntu-24.04.iso"):
        (stick / "ISO" / n).write_bytes(b"")
    os.environ.update(
        {
            "MATERIAL_PKG": str(PKG),
            "MATERIAL_STATE_DIR": str(tmp / "state"),
            "MATERIAL_CONF": str(tmp / "mg.conf"),
            "MATERIAL_OVERRIDES": str(tmp / "root/etc/material-grub/overrides.json"),
            "XDG_CONFIG_HOME": str(tmp / "cfg"),
            "XDG_CACHE_HOME": str(tmp / "cache"),
            "MG_HELPER_ROOT": str(tmp / "root"),
            "MG_HELPER_APPLY": str(fake),
            "MG_GUI_HELPER": json.dumps([sys.executable, str(ROOT / "gui/mghelper.py")]),
            "MG_BGRT_IMAGE": "/nonexistent/bgrt",  # no firmware logo: the preview shows the penguin
        }
    )
    sys.path.insert(0, str(ROOT / "gui"))
    import mgserver

    srv = mgserver.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    app = srv.app
    base = f"http://127.0.0.1:{app.port}"
    url = f"{base}/?t={app.token}"
    shutil.rmtree(SHOTS, ignore_errors=True)
    SHOTS.mkdir(parents=True)
    problems = []

    def shot(page, name):
        page.wait_for_timeout(600)  # the preview cross-fade and the page animations
        page.screenshot(path=str(SHOTS / f"{name}.png"))

    def preview_ready(page):
        try:
            _preview_ready(page)
        except Exception:
            page.screenshot(path=str(SHOTS / "99-failure.png"))
            raise

    def _preview_ready(page):
        page.wait_for_function(
            "() => { const f = document.getElementById('frame'); return f && !f.classList.contains('loading') && [...f.querySelectorAll('img')].some(i => i.style.opacity === '1'); }",
            timeout=30000,
        )

    def check(cond, msg):
        if not cond:
            problems.append(msg)
            print("FAIL:", msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=find_browser(), headless=True, args=["--no-sandbox"])

        def new_context(**kw):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, **kw)
            return ctx

        ctx = new_context(color_scheme="light")
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: errors.append(f"request failed: {r.url} ({r.failure})"))

        def on_fail():
            try:
                page.screenshot(path=str(SHOTS / "99-failure.png"))
            except Exception:
                pass

        import atexit

        atexit.register(on_fail)
        page.goto(url)
        page.wait_for_selector(".nav")
        expect(page.locator("h1")).to_have_text("Overview")
        page.wait_for_selector(".status-row")  # the health checks ran
        shot(page, "01-overview-light")

        # --- style page and the live preview
        page.get_by_role("button", name="Style").first.click()
        expect(page.locator("h1")).to_have_text("Style")
        preview_ready(page)
        shot(page, "02-style-rail-light")
        before = page.locator("#frame img[style*='opacity: 1']").first.get_attribute("src")
        page.locator(".style-card:has(b:text-is('List'))").click()
        expect(page.locator(".chip.dirty")).to_be_visible()
        preview_ready(page)
        after = page.locator("#frame img[style*='opacity: 1']").first.get_attribute("src")
        check(before != after, "the preview did not change when the style changed")
        shot(page, "03-style-list-light")
        page.locator(".style-card:has(b:text-is('Split'))").click()
        preview_ready(page)
        shot(page, "04-style-split-light")
        page.locator(".style-card:has(b:text-is('Clean'))").click()
        preview_ready(page)
        shot(page, "05-style-clean-light")
        page.locator(".style-card:has(b:text-is('Rail'))").click()
        preview_ready(page)

        # --- entries: order, per-entry edit
        page.get_by_role("button", name="Entries").first.click()
        expect(page.locator("h1")).to_have_text("Entries")
        rows = page.locator(".entry")
        check(rows.count() == 8, f"expected 8 entries, got {rows.count()}")
        page.get_by_role("button", name="Windows first", exact=True).click()
        expect(page.locator(".group-head").first).to_have_text("Windows")
        check("Windows" in page.locator(".entry").first.inner_text(), "Windows first did not put Windows on top")
        page.get_by_role("button", name="Free order", exact=True).click()
        # drag the Arch row above the first row
        arch = page.locator(".entry", has_text="Arch Linux")
        arch.drag_to(page.locator(".entry").first)
        check("Arch" in page.locator(".entry").first.inner_text(), "drag and drop did not move Arch to the top")
        # keyboard: Alt+ArrowDown moves it back down one place
        page.locator(".entry").first.focus()
        page.keyboard.press("Alt+ArrowDown")
        check("Arch" not in page.locator(".entry").first.inner_text(), "Alt+ArrowDown did not move the row")
        # select Fedora and customise it
        page.locator(".entry", has_text="Fedora").first.click()
        name = page.locator("#editor input[type=text]").first
        name.fill("Work laptop")
        name.press("Tab")
        check(
            "Work laptop" in page.locator(".entry").first.inner_text()
            or "Work laptop" in page.locator(".entries").inner_text(),
            "the new name is not shown in the list",
        )
        page.locator("#editor .swatch").nth(5).click()  # a colour
        preview_ready(page)
        shot(page, "06-entries-light")
        page.locator("#editor .switch", has_text="Hide this entry").locator(
            "input"
        ).click()  # the real checkbox covers the label
        check("hidden" in page.locator(".entries").inner_text(), "the hidden entry is not marked")
        page.locator("#editor .switch", has_text="Hide this entry").locator("input").click()  # show it again

        # --- colours: one colour for everything
        page.get_by_role("button", name="Colours").first.click()
        page.get_by_role("button", name="One colour for everything", exact=True).click()
        page.get_by_role("button", name="Lavender", exact=True).click()
        page.wait_for_selector(".palette-strip div")
        preview_ready(page)
        shot(page, "07-colours-light")

        # --- presets
        page.get_by_role("button", name="Presets").first.click()
        page.get_by_label("Preset name").fill("E2E look")
        page.get_by_role("button", name="Save preset", exact=True).click()
        expect(page.locator(".card.high h3", has_text="E2E look")).to_be_visible()
        shot(page, "08-presets-light")

        # --- apply: a slow fake apply so the progress dialog can be captured
        os.environ["FAKE_APPLY_SLEEP"] = "4"
        page.get_by_role("button", name="Apply to GRUB", exact=True).click()
        expect(page.locator("dialog[open] .sheet")).to_be_visible()
        page.wait_for_timeout(1200)
        shot(page, "09-apply-progress-light")
        page.locator("dialog .switch", has_text="Verbose log").locator("input").click()
        page.wait_for_timeout(300)
        shot(page, "10-apply-verbose-light")
        expect(page.locator("dialog[open] .steps")).to_contain_text("Material GRUB is updated", timeout=60000)
        shot(page, "11-apply-done-light")
        page.get_by_role("button", name="Close", exact=True).click()
        root = tmp / "root"
        conf = (root / "etc/material-grub.conf").read_text()
        check("STYLE=rail" in conf, "the conf was not written by the helper: " + conf)
        ov = json.loads((root / "etc/material-grub/overrides.json").read_text())
        check(ov["seed"] == {"mode": "single", "color": "#7E57C2"}, f"seed not saved: {ov['seed']}")
        check(any(r.get("name") == "Work laptop" for r in ov["entries"]), "the entry name was not saved")
        check(len(ov["order"]) > 0, "the new order was not saved")
        expect(page.locator(".chip.dirty")).to_have_count(0)

        # --- a failing apply is reported and rolled back
        before = (root / "etc/material-grub/overrides.json").read_text()
        os.environ["FAKE_APPLY_RC"] = "3"
        os.environ["FAKE_APPLY_SLEEP"] = "1"
        page.get_by_role("button", name="Colours").first.click()
        page.get_by_role("button", name="A colour per entry", exact=True).click()
        page.get_by_role("button", name="Apply to GRUB", exact=True).click()
        expect(page.locator("dialog[open] .steps")).to_contain_text("previous settings are back", timeout=60000)
        shot(page, "12-apply-failed-light")
        page.get_by_role("button", name="Close", exact=True).click()
        del os.environ["FAKE_APPLY_RC"]
        check(
            (root / "etc/material-grub/overrides.json").read_text() == before,
            "a failed apply did not restore the previous overrides",
        )

        # --- ventoy
        page.get_by_role("button", name="Ventoy").first.click()
        page.get_by_label("Mount point of the stick").fill(str(stick))
        page.get_by_role("button", name="Open", exact=True).click()
        expect(page.locator(".entry", has_text="Fedora-Workstation-44.iso")).to_be_visible()
        page.locator(".entry", has_text="Fedora-Workstation-44.iso").click()
        vname = page.locator("section.card.high input[type=text]").first
        vname.fill("Work laptop ISO")
        vname.press("Tab")
        shot(page, "13-ventoy-light")
        os.environ["FAKE_APPLY_SLEEP"] = "0"
        page.get_by_role("button", name="Write to the stick", exact=True).click()
        expect(page.locator("dialog[open] .steps")).to_contain_text("The stick is themed", timeout=120000)
        page.get_by_role("button", name="Close", exact=True).click()
        vj = json.loads((stick / "ventoy/ventoy.json").read_text())
        check(
            any(a["alias"] == "Work laptop ISO" for a in vj.get("menu_alias", [])), "the Ventoy alias was not written"
        )

        # --- update page (the GitHub answer is faked)
        page.route(
            "**/api/update/check",
            lambda r: r.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "current": "0.7.0",
                        "latest": "9.9.9",
                        "newer": True,
                        "url": "https://example.invalid/r",
                        "notes": "",
                    }
                ),
            ),
        )
        page.get_by_role("button", name="Update").first.click()
        page.get_by_role("button", name="Check for updates", exact=True).click()
        expect(page.get_by_text("v9.9.9 is available")).to_be_visible()
        shot(page, "14-update-light")

        # --- logs page
        page.get_by_role("button", name="Logs").first.click()
        expect(page.locator("#layout .logbox")).to_be_visible()

        # Chrome reports the finished streaming fetch of a job's event stream as aborted: not an error of the page
        errors = [e for e in errors if not ("/events" in e and "ERR_ABORTED" in e)]
        check(not errors, "browser errors: " + "; ".join(errors[:5]))
        ctx.close()

        # --- dark interface
        dctx = new_context(color_scheme="dark")
        d = dctx.new_page()
        derr = []
        d.on("console", lambda m: derr.append(m.text) if m.type == "error" else None)
        d.goto(url)
        d.wait_for_selector(".nav")
        d.wait_for_selector(".status-row")
        shot(d, "20-overview-dark")
        d.get_by_role("button", name="Entries").first.click()
        preview_ready(d)
        shot(d, "21-entries-dark")
        d.get_by_role("button", name="Colours").first.click()
        d.get_by_role("button", name="One colour for everything", exact=True).click()
        d.get_by_role("button", name="Tangerine", exact=True).click()
        preview_ready(d)
        shot(d, "22-colours-dark")
        check(not derr, "dark: browser errors: " + "; ".join(derr[:5]))
        dctx.close()

        # --- phone width: the bottom bar, no sideways scroll
        mctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="light")
        m = mctx.new_page()
        m.goto(url)
        m.wait_for_selector(".nav")
        m.wait_for_selector(".status-row")
        shot(m, "30-phone-overview")
        m.get_by_role("button", name="Entries").first.click()
        preview_ready(m)
        shot(m, "31-phone-entries")
        wide = m.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        if wide:
            culprits = m.evaluate(
                "[...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0, 5).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right))"
            )
            print("wider than the phone:", culprits)
            print(
                "chain:",
                m.evaluate(
                    "(() => { let e = document.querySelector('main section.card'); const o = []; while (e && e !== document.documentElement) { o.push(e.tagName + '.' + e.className + ' w=' + Math.round(e.getBoundingClientRect().width) + ' disp=' + getComputedStyle(e).display); e = e.parentElement; } return o; })()"
                ),
            )
        check(not wide, "the page scrolls sideways on a phone")
        mctx.close()

        # --- security as seen from a browser: another origin cannot read the API
        xctx = browser.new_context()
        x = xctx.new_page()
        x.goto("about:blank")
        res = x.evaluate(
            "async (u) => { try { const r = await fetch(u + '/api/state'); return 'status ' + r.status; } catch (e) { return 'blocked'; } }",
            base,
        )
        check(res in ("blocked", "status 403"), f"a foreign page could read /api/state: {res}")
        res = x.evaluate(
            "async (u) => { try { const r = await fetch(u + '/api/apply', {method: 'POST', body: '{}'}); return 'status ' + r.status; } catch (e) { return 'blocked'; } }",
            base,
        )
        check(res in ("blocked", "status 403"), f"a foreign page could POST /api/apply: {res}")
        xctx.close()
        browser.close()

    srv.shutdown()
    app.close()
    if problems:
        sys.exit("GUI E2E FAILED:\n  " + "\n  ".join(problems))
    print(f"gui e2e ok: {len(list(SHOTS.glob('*.png')))} screenshots in {SHOTS}")


if __name__ == "__main__":
    main()
