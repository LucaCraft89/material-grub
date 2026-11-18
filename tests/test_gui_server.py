"""The GUI server over real HTTP on 127.0.0.1: authentication, Host/Origin checks, state, preview, uploads, presets and an apply job through the
real helper (as a normal user, in a scratch root, with a fake `material-grub apply`). Needs a built package + Pillow. usage: python3 tests/test_gui_server.py"""

import http.client
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
ENTRIES = [
    {
        "class": "mg_aaaaaaaaaa",
        "key": "fedora",
        "kind": "kernel",
        "level": "top",
        "title": "Fedora Linux 6.1",
        "kver": "6.1",
    },
    {"class": "mg_bbbbbbbbbb", "key": "windows11", "kind": "plain", "level": "top", "title": "Windows Boot Manager"},
]


@unittest.skipUnless((PKG / "subtitles.json").is_file(), "no built package with subtitles.json")
class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        (t / "state").mkdir()
        (t / "state/entries.json").write_text(json.dumps(ENTRIES))
        (t / "state/menu.json").write_text(json.dumps([{"level": "top", "items": [e["class"] for e in ENTRIES]}]))
        (t / "mg.conf").write_text("STYLE=rail\n")
        fake = t / "apply.sh"
        fake.write_text("#!/bin/sh\necho applying the menu\nexit ${FAKE_APPLY_RC:-0}\n")
        fake.chmod(0o755)
        cls.env = {
            "MATERIAL_PKG": str(PKG),
            "MATERIAL_STATE_DIR": str(t / "state"),
            "MATERIAL_CONF": str(t / "mg.conf"),
            "MATERIAL_OVERRIDES": str(t / "root/etc/material-grub/overrides.json"),
            "XDG_CONFIG_HOME": str(t / "cfg"),
            "XDG_CACHE_HOME": str(t / "cache"),
            "MG_HELPER_ROOT": str(t / "root"),
            "MG_HELPER_APPLY": str(fake),
            "MG_GUI_HELPER": json.dumps([sys.executable, str(ROOT / "gui/mghelper.py")]),
        }
        cls.saved = {k: os.environ.get(k) for k in cls.env}
        os.environ.update(cls.env)
        sys.path.insert(0, str(ROOT / "gui"))
        import mgserver

        cls.mgserver = mgserver
        cls.srv = mgserver.make_server(0)
        cls.app = cls.srv.app
        cls.port = cls.app.port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.t = t

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.app.close()
        cls.srv.server_close()
        for k, v in cls.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None, auth=True, host=None, raw=False):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        h = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
        if auth:
            h.setdefault("X-MG-Token", self.app.token)
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        if data is not None and "Content-Type" not in h:
            h["Content-Type"] = "application/json"
        c.request(method, path, data, h)
        r = c.getresponse()
        payload = r.read()
        c.close()
        return r.status, (payload if raw else (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)), r

    # ------------------------------------------------------------ security
    def test_index_needs_the_token_then_a_cookie(self):
        st, body, _ = self.req("GET", "/", auth=False)
        self.assertEqual(st, 403)
        st, _, r = self.req("GET", "/?t=wrong", auth=False)
        self.assertEqual(st, 403)
        st, _, r = self.req("GET", f"/?t={self.app.token}", auth=False)
        self.assertEqual((st, r.getheader("Location")), (302, "/"))
        cookie = r.getheader("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        st, body, _ = self.req("GET", "/", auth=False, headers={"Cookie": f"mg={self.app.token}"})
        self.assertEqual(st, 200)
        self.assertIn(self.app.token.encode(), body)  # the page gets the token for its API calls
        self.assertNotIn(b"__MG_TOKEN__", body)

    def test_api_refuses_without_token_wrong_host_and_foreign_origin(self):
        self.assertEqual(self.req("GET", "/api/state", auth=False)[0], 403)
        self.assertEqual(self.req("GET", "/api/state", headers={"X-MG-Token": "nope"})[0], 403)
        self.assertEqual(self.req("GET", "/api/state", host="evil.example:80")[0], 403)  # DNS rebinding
        self.assertEqual(self.req("GET", "/api/state", headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/ping", {}, headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("OPTIONS", "/api/apply", auth=False)[0], 403)  # no CORS preflight ever succeeds
        st, _, r = self.req("GET", "/api/ping", headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(st, 200)
        self.assertNotIn("Access-Control-Allow-Origin", dict(r.getheaders()))

    def test_cookie_alone_cannot_change_things(self):
        st, _, _ = self.req("POST", "/api/ping", {}, auth=False, headers={"Cookie": f"mg={self.app.token}"})
        self.assertEqual(st, 403)  # a cross-site form post would carry the cookie but not the header

    def test_static_files_are_confined(self):
        for p in ("/../mgserver.py", "/%2e%2e/mgserver.py", "/fonts/../../x", "/fonts/other.ttf"):
            self.assertIn(self.req("GET", p)[0], (403, 404, 400), p)
        st, body, r = self.req("GET", "/fonts/GoogleSansFlex-VF.ttf", raw=True)
        self.assertEqual((st, r.getheader("Content-Type")), (200, "font/ttf"))
        self.assertIn("script-src 'self'", r.getheader("Content-Security-Policy"))

    # ------------------------------------------------------------ API
    def test_state(self):
        st, d, _ = self.req("GET", "/api/state")
        self.assertEqual(st, 200)
        self.assertEqual([e["class"] for e in d["entries"]], ["mg_aaaaaaaaaa", "mg_bbbbbbbbbb"])
        self.assertEqual((d["conf"]["STYLE"], d["demo"], len(d["seeds"])), ("rail", False, 32))
        self.assertIn("fedora", d["catalog"])
        self.assertIn(d["overrides"]["seed"]["mode"], ("multi", "single"))  # the apply test may have written one first

    def test_preview_png_and_validation(self):
        draft = {
            "conf": {"STYLE": "list"},
            "overrides": {"entries": [{"match": {"key": "fedora"}, "color": "#E95420", "name": "Hi"}]},
        }
        st, png, r = self.req(
            "POST", "/api/preview", {"draft": draft, "class": "mg_aaaaaaaaaa", "scale": 0.25}, raw=True
        )
        self.assertEqual((st, r.getheader("Content-Type")), (200, "image/png"))
        from PIL import Image

        self.assertEqual(Image.open(io.BytesIO(png)).size, (480, 270))
        bad = {"draft": {"conf": {"STYLE": "neon"}}, "class": "mg_aaaaaaaaaa"}
        self.assertEqual(self.req("POST", "/api/preview", bad)[0], 400)

    def test_icon_upload_and_thumbnail(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGBA", (40, 40), (10, 200, 10, 255)).save(buf, "PNG")
        st, d, _ = self.req("POST", "/api/icon?name=mine.png", buf.getvalue(), headers={"Content-Type": "image/png"})
        self.assertEqual((st, d["name"]), (200, "mine.png"))
        st, png, r = self.req("GET", "/api/icon/mine.png", raw=True)
        self.assertEqual((st, r.getheader("Content-Type")), (200, "image/png"))
        for name, body in (
            ("../x.png", buf.getvalue()),
            ("a.exe", b"MZ"),
            ("bad.png", b"not a picture"),
            ("big.png", b"x" * (5 * 1024 * 1024)),
            ("e.svg", b"<html>"),
        ):
            self.assertEqual(
                self.req("POST", "/api/icon?name=" + name, body, headers={"Content-Type": "application/octet-stream"})[
                    0
                ],
                400,
                name,
            )

    def test_presets_roundtrip(self):
        draft = {"conf": {"STYLE": "split"}, "overrides": {"seed": {"mode": "single", "color": "#7E57C2"}}}
        self.assertEqual(self.req("POST", "/api/presets/save", {"name": "My look", "draft": draft})[0], 200)
        self.assertEqual(self.req("POST", "/api/presets/save", {"name": "../evil", "draft": draft})[0], 400)
        st, d, _ = self.req("GET", "/api/state")
        self.assertEqual([p["name"] for p in d["presets"]], ["My look"])
        st, d, _ = self.req("POST", "/api/presets/load/My%20look", {})
        self.assertEqual((st, d["draft"]["overrides"]["seed"]["color"]), (200, "#7E57C2"))
        st, exp, _ = self.req("GET", "/api/presets/export/My%20look")
        self.assertEqual(self.req("POST", "/api/presets/import", dict(exp, name="Imported"))[0], 200)
        self.assertEqual(
            self.req("POST", "/api/presets/import", {"preset": 1, "name": "x", "conf": {"EVIL": "1"}})[0], 400
        )
        self.assertEqual(self.req("DELETE", "/api/presets/My%20look")[0], 200)
        self.assertEqual(self.req("POST", "/api/presets/load/My%20look", {})[0], 404)

    def events(self, jid):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        c.request(
            "GET", f"/api/jobs/{jid}/events", headers={"Host": f"127.0.0.1:{self.port}", "X-MG-Token": self.app.token}
        )
        r = c.getresponse()
        out = []
        for line in r.read().decode().splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
        return out

    def test_apply_job_streams_events_and_writes_through_the_helper(self):
        draft = {
            "conf": {"STYLE": "list", "HINTS": "off"},
            "overrides": {
                "seed": {"mode": "single", "color": "#7E57C2"},
                "entries": [{"match": {"key": "fedora"}, "name": "Mine"}],
            },
        }
        st, d, _ = self.req("POST", "/api/apply", {"draft": draft})
        self.assertEqual(st, 200)
        ev = self.events(d["job"])
        kinds = [e["event"] for e in ev]
        self.assertEqual(kinds[-1], "done")
        self.assertTrue(ev[-1]["ok"], ev)
        self.assertIn("step", kinds)
        self.assertTrue(any(e.get("text") == "applying the menu" for e in ev))
        root = self.t / "root"
        self.assertIn("STYLE=list", (root / "etc/material-grub.conf").read_text())
        self.assertEqual(
            json.loads((root / "etc/material-grub/overrides.json").read_text())["seed"]["color"], "#7E57C2"
        )

    def test_apply_failure_restores_and_reports(self):
        root = self.t / "root"
        before = (root / "etc/material-grub.conf").read_text() if (root / "etc/material-grub.conf").exists() else ""
        os.environ["FAKE_APPLY_RC"] = "3"
        try:
            st, d, _ = self.req("POST", "/api/apply", {"draft": {"conf": {"STYLE": "clean"}, "overrides": {}}})
            ev = self.events(d["job"])
        finally:
            del os.environ["FAKE_APPLY_RC"]
        self.assertFalse(ev[-1]["ok"])
        self.assertTrue(any(e["event"] == "error" and "previous settings are back" in e["msg"] for e in ev), ev)
        after = (root / "etc/material-grub.conf").read_text() if (root / "etc/material-grub.conf").exists() else ""
        self.assertEqual(after, before)

    # ------------------------------------------------------------ Ventoy
    def stick(self):
        d = Path(tempfile.mkdtemp(dir=self.t))
        (d / "ventoy").mkdir()
        (d / "ISO").mkdir()
        (d / "ISO/Fedora-Workstation-44.iso").write_bytes(b"")
        return d

    def test_ventoy_state_rejects_non_sticks(self):
        self.assertEqual(self.req("GET", "/api/ventoy/state?path=/etc")[0], 400)
        self.assertEqual(self.req("GET", "/api/ventoy/state?path=relative")[0], 400)

    def test_ventoy_state_icon_and_apply(self):
        d = self.stick()
        st, s, _ = self.req("GET", "/api/ventoy/state?path=" + str(d))
        self.assertEqual(st, 200)
        self.assertEqual([f["name"] for f in s["files"]], ["Fedora-Workstation-44.iso"])
        self.assertEqual(s["files"][0]["key"], "fedora")
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGBA", (32, 32), (200, 0, 0, 255)).save(buf, "PNG")
        self.assertEqual(
            self.req(
                "POST",
                f"/api/ventoy/icon?path={d}&name=logo.png",
                buf.getvalue(),
                headers={"Content-Type": "image/png"},
            )[0],
            200,
        )
        self.assertEqual(
            self.req(
                "POST",
                f"/api/ventoy/icon?path={d}&name=../x.png",
                buf.getvalue(),
                headers={"Content-Type": "image/png"},
            )[0],
            400,
        )
        draft = {
            "conf": {"STYLE": "list"},
            "overrides": {"entries": [{"match": {"title": "Fedora"}, "name": "Mine", "icon": "file:logo.png"}]},
        }
        st, j, _ = self.req("POST", "/api/ventoy/apply", {"path": str(d), "draft": draft, "res": "1920x1080"})
        self.assertEqual(st, 200, j)
        ev = self.events(j["job"])
        self.assertTrue(ev[-1]["ok"], ev[-6:])
        vj = json.loads((d / "ventoy/ventoy.json").read_text())
        self.assertTrue(vj["menu_class"][0]["class"].startswith("mgu_"))
        self.assertEqual(vj["menu_alias"][0]["alias"], "Mine")
        self.assertIn("STYLE=list", (d / "ventoy/material-grub.conf").read_text())
        for bad in ({"conf": {"STYLE": "neon"}}, {"overrides": {"seed": {"mode": "x"}}}):
            self.assertEqual(self.req("POST", "/api/ventoy/apply", {"path": str(d), "draft": bad})[0], 400)
        self.assertEqual(
            self.req("POST", "/api/ventoy/apply", {"path": str(d), "draft": draft, "res": "1920x1080; rm -rf /"})[0],
            400,
        )

    def test_apply_rejects_bad_drafts_before_any_helper_runs(self):
        self.assertEqual(self.req("POST", "/api/apply", {"draft": {"conf": {"STYLE": "neon"}}})[0], 400)
        self.assertEqual(
            self.req(
                "POST",
                "/api/apply",
                {"draft": {"overrides": {"entries": [{"match": {"key": "x"}, "icon": "file:../../etc/passwd"}]}}},
            )[0],
            400,
        )


if __name__ == "__main__":
    unittest.main()
