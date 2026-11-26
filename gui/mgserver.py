"""The GUI's local web server: stdlib only, 127.0.0.1, one random port, a one-time token. Serves the web UI and a small JSON API.

Safety (a web page in your browser could try to talk to a local server, so the server does not trust the browser):
  - it listens on 127.0.0.1 only, and checks the Host header (DNS rebinding) and the Origin header;
  - the page is opened with a secret token in the link; it becomes a SameSite=Strict cookie, and every API call must also carry it in a header
    (a header cannot be sent cross-site without a CORS preflight, which this server never allows);
  - it never runs anything as root itself: changes go to the privileged helper (pkexec shows the system's own authentication dialog);
  - the helper accepts a fixed list of requests and validates every value again.
"""

import base64
import hmac
import http.server
import json
import mimetypes
import os
import re
import secrets
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import mgpaths

PKG, MODS = mgpaths.setup()
import mgcustom  # noqa: E402, F401  (imported early: a broken install fails at start, not on the first preview)
import mgoverrides  # noqa: E402
import mgplymouth  # noqa: E402
import mgpresets  # noqa: E402
import mgstate  # noqa: E402

WEB = mgpaths.HERE / "web"
RELEASES = "https://api.github.com/repos/LucaCraft89/material-grub/releases/latest"
MAX_BODY = 8 * 1024 * 1024
HELPER_INSTALLED = "/usr/libexec/material-grub-gui-helper"


def cfg_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "material-grub-gui"


def cache_dir():
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "material-grub-gui"


def helper_command():
    """How to run the privileged helper. MG_GUI_HELPER (a JSON list) replaces it for tests and for trying the GUI from a checkout without installing."""
    custom = os.environ.get("MG_GUI_HELPER")
    if custom:
        return json.loads(custom)
    if Path(HELPER_INSTALLED).is_file():
        return ["pkexec", HELPER_INSTALLED]
    return ["pkexec", sys.executable, str(mgpaths.HERE / "mghelper.py")]


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


class Job:
    """A running privileged request: its events (the installer's JSON event lines) are kept so a page that reconnects sees them all."""

    def __init__(self, jid):
        self.id, self.events, self.done = jid, [], False
        self.cv = threading.Condition()

    def add(self, ev):
        with self.cv:
            self.events.append(ev)
            if ev.get("event") == "done":
                self.done = True
            self.cv.notify_all()

    def wait(self, start, timeout=15):
        with self.cv:
            if len(self.events) <= start and not self.done:
                self.cv.wait(timeout)
            return self.events[start:], self.done


class App:
    def __init__(self, token, port, idle=0):
        self.token, self.port, self.idle = token, port, idle
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.jobs = {}
        self.lock = threading.Lock()
        self.last_ping = time.time()
        self.staging = cache_dir() / "icons"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.previewer = None
        self.pv_lock = threading.Lock()
        self.job_busy = False

    def previewer_(self):
        with self.pv_lock:
            if self.previewer is None:
                import mgpreview

                self.previewer = mgpreview.Previewer(PKG)
            return self.previewer

    def close(self):
        if self.previewer is not None:
            self.previewer.close()

    def sync_staging(self):
        """The icons folder of the system, mirrored into the user's staging folder (the preview and the apply step read pictures from there)."""
        src = mgoverrides.icon_dir()
        try:
            for f in src.iterdir():
                if f.suffix.lower() in mgoverrides.IMAGE_EXT and not (self.staging / f.name).exists():
                    (self.staging / f.name).write_bytes(f.read_bytes())
        except OSError:
            pass

    # -------- jobs
    def start_job(self, request):
        with self.lock:
            if self.job_busy:
                raise RuntimeError("another change is still running")
            self.job_busy = True
        jid = secrets.token_hex(6)
        job = Job(jid)
        self.jobs[jid] = job
        threading.Thread(target=self._run_job, args=(job, request), daemon=True).start()
        return job

    def start_callable(self, fn):
        """Like start_job, but `fn(emit)` runs in-process (Ventoy sticks are written as the user: no root involved)."""
        with self.lock:
            if self.job_busy:
                raise RuntimeError("another change is still running")
            self.job_busy = True
        job = Job(secrets.token_hex(6))
        self.jobs[job.id] = job

        def run():
            try:
                fn(job.add)
            except Exception as e:
                job.add({"event": "error", "msg": str(e), "code": 1})
                job.add({"event": "done", "rc": 1, "ok": False})
            finally:
                with self.lock:
                    self.job_busy = False

        threading.Thread(target=run, daemon=True).start()
        return job

    def _run_job(self, job, request):
        try:
            cmd = helper_command()
            job.add({"event": "info", "msg": "Asking the system for permission..."})
            p = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace"
            )
            err = []
            t = threading.Thread(target=lambda: err.extend(p.stderr.readlines()), daemon=True)
            t.start()
            p.stdin.write(json.dumps(request))
            p.stdin.close()
            for line in p.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if not isinstance(ev, dict) or "event" not in ev:
                        raise ValueError
                except ValueError:
                    ev = {"event": "log", "text": line, "level": "info"}
                if ev.get("event") == "done":
                    continue  # the real "done" is sent below, after the exit status is known
                job.add(ev)
            rc = p.wait()
            t.join(2)
            if rc in (126, 127) or (rc != 0 and not any(e.get("event") == "error" for e in job.events)):
                tail = " ".join(x.strip() for x in err[-3:])
                refused = rc in (126, 127)
                job.add(
                    {
                        "event": "error",
                        "msg": "The system did not allow it (the authentication was cancelled or refused)."
                        if refused
                        else f"The helper stopped with status {rc}. {tail}",
                        "code": rc,
                    }
                )
            for x in err:
                if x.strip() and rc != 0:
                    job.add({"event": "log", "text": x.rstrip(), "level": "warn"})
            job.add({"event": "done", "rc": rc, "ok": rc == 0})
        except Exception as e:  # never leave the page waiting forever
            job.add({"event": "error", "msg": f"could not start the helper: {e}", "code": 1})
            job.add({"event": "done", "rc": 1, "ok": False})
        finally:
            with self.lock:
                self.job_busy = False

    def apply_request(self, draft, plymouth_cmdline=False):
        clean, errs = mgstate.check_draft(draft)
        if errs:
            raise ValueError("; ".join(errs))
        icons = {}
        for r in clean["overrides"]["entries"]:
            ic = r.get("icon", "")
            if ic.startswith("file:") and (self.staging / ic[5:]).is_file():
                icons[ic[5:]] = base64.b64encode((self.staging / ic[5:]).read_bytes()).decode()
        return {
            "verb": "apply",
            "conf": clean["conf"],
            "overrides": clean["overrides"],
            "icons": icons,
            "plymouth_cmdline": plymouth_cmdline,
        }


def install_kind():
    return "package" if Path("/usr/share/material-grub-src").is_dir() else "source"


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "material-grub-gui"
    protocol_version = "HTTP/1.1"
    app = None

    def log_message(self, fmt, *args):  # quiet: the terminal shows the link, not every request
        if os.environ.get("MG_GUI_DEBUG"):
            sys.stderr.write("gui: " + fmt % args + "\n")

    # ---------------------------------------------------------------- helpers
    def send(self, code, body=b"", ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def fail(self, code, msg):
        self.send(code, {"error": msg})

    def cookie_ok(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "mg" and hmac.compare_digest(v, self.app.token):
                return True
        return False

    def header_ok(self):
        return hmac.compare_digest(self.headers.get("X-MG-Token", ""), self.app.token)

    def host_ok(self):
        return self.headers.get("Host", "") in self.app.hosts

    def origin_ok(self):
        o = self.headers.get("Origin")
        return o is None or o in {f"http://{h}" for h in self.app.hosts}

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("the request is too large")
        return self.rfile.read(n)

    def json_body(self):
        try:
            return json.loads(self.body() or b"{}")
        except ValueError:
            raise ValueError("the request is not valid JSON") from None

    # ---------------------------------------------------------------- dispatch
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_DELETE(self):
        self.route("DELETE")

    def do_OPTIONS(self):  # no CORS: a preflight is always refused
        self.fail(403, "cross-origin requests are not allowed")

    def route(self, method):
        try:
            if not self.host_ok():
                return self.fail(403, "unexpected Host header")
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            path = u.path
            if method == "GET" and path == "/":
                return self.index(q)
            if not (self.cookie_ok() or self.header_ok()):
                return self.fail(403, "not authorised: open the link printed by material-grub-gui")
            if method != "GET" and not (self.header_ok() and self.origin_ok()):
                return self.fail(403, "missing or wrong token")
            if method == "GET" and path.startswith("/api/") and not self.origin_ok():
                return self.fail(403, "cross-origin requests are not allowed")
            if method == "GET" and not path.startswith("/api/"):
                return self.static(path)
            fn, groups = ROUTES.get((method, path)), ()
            if fn is None:
                for (m, pat), f in PATTERNS:
                    hit = re.fullmatch(pat, path) if m == method else None
                    if hit:
                        fn, groups = f, hit.groups()
                        break
            if fn is None:
                return self.fail(404, "no such request")
            return fn(self, q, groups)
        except ValueError as e:
            return self.fail(400, str(e))
        except BrokenPipeError:
            return None
        except Exception as e:  # a bug must not kill the server or leak a traceback to the page
            sys.stderr.write(f"gui: {method} {self.path}: {e!r}\n")
            return self.fail(500, "internal error")

    # ---------------------------------------------------------------- pages
    def index(self, q):
        app = self.app
        if q.get("t", [""])[0]:
            if not hmac.compare_digest(q["t"][0], app.token):
                return self.fail(403, "wrong token")
            return self.send(
                302,
                b"",
                "text/plain",
                {
                    "Location": "/"
                    + (
                        "#" + q["view"][0]
                        if re.fullmatch(r"[a-z]{3,12}(:[A-Za-z0-9/_.%-]{1,200})?", q.get("view", [""])[0])
                        else ""
                    ),
                    "Set-Cookie": f"mg={app.token}; HttpOnly; SameSite=Strict; Path=/",
                },
            )
        if not self.cookie_ok():
            return self.send(
                403,
                "<h1>Material GRUB</h1><p>Open the link printed in the terminal by <code>material-grub-gui</code>.</p>",
                "text/html; charset=utf-8",
            )
        html = (WEB / "index.html").read_text().replace("__MG_TOKEN__", app.token)
        return self.send(200, html, "text/html; charset=utf-8")

    def static(self, path):
        name = path.lstrip("/")
        if name.startswith("fonts/"):
            for d in (PKG / "fonts" if PKG else None, mgpaths.REPO / "fonts"):
                f = d / name[6:] if d else None
                if f and f.name == "GoogleSansFlex-VF.ttf" and f.is_file():
                    return self.send(200, f.read_bytes(), "font/ttf")
            return self.fail(404, "no such file")
        f = (WEB / name).resolve()
        if WEB.resolve() not in f.parents or not f.is_file() or f.name == "index.html":
            return self.fail(404, "no such file")
        return self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")


# -------------------------------------------------------------------- API
def api_state(h, q, g):
    h.app.sync_staging()
    st = mgstate.read_state(PKG)
    st["icons"] = sorted({*st["icons"], *(f.name for f in h.app.staging.iterdir() if f.is_file())})
    st["install_kind"] = install_kind()
    st["presets"] = [{"name": n, **info} for n, info in mgpresets.listing(cfg_dir() / "overrides.json")]
    return h.send(200, st)


def api_status(h, q, g):
    import cmd_doctor

    d = cmd_doctor.Doctor()
    d.run(Path(cmd_doctor.__file__).resolve())
    return h.send(200, d.summary())


def api_ping(h, q, g):
    h.app.last_ping = time.time()
    return h.send(200, {"ok": True})


def api_preview(h, q, g):
    req = h.json_body()
    draft, errs = mgstate.check_draft(req.get("draft", {}))
    if errs:
        return h.fail(400, "; ".join(errs))
    ents, menu, _ = mgstate.entries()
    if not any(e["class"] == req.get("class") for e in ents):
        ents, menu = [e for e in ents], menu
    pv = h.app.previewer_()
    try:
        png = pv.render(
            ents,
            menu,
            draft,
            req.get("class", ""),
            req.get("dark", True) is not False,
            req.get("scale", 0.5),
            req.get("aspect", "16x9"),
            icon_dir=h.app.staging,
        )
    except (KeyError, StopIteration):
        return h.fail(400, "unknown entry")
    return h.send(200, png, "image/png")


def api_icon_upload(h, q, g):
    name = q.get("name", [""])[0]
    if not mgoverrides._icon_ok("file:" + name):
        return h.fail(
            400, "the file name must be letters, digits, - _ . and end in .png .jpg .jpeg .svg .webp .gif or .bmp"
        )
    raw = h.body()
    if not raw or len(raw) > 4 * 1024 * 1024:
        return h.fail(400, "the picture must be between 1 byte and 4 MB")
    if name.lower().endswith(".svg"):
        if b"<svg" not in raw[:65536].lower():
            return h.fail(400, "that is not an SVG file")
    else:
        import io

        from PIL import Image

        try:
            im = Image.open(io.BytesIO(raw))
            im.verify()
            if im.width * im.height > 50_000_000:
                return h.fail(400, "the picture is too large")
        except Exception:
            return h.fail(400, "that is not a readable picture")
    (h.app.staging / name).write_bytes(raw)
    return h.send(200, {"name": name})


def api_icon_get(h, q, g):
    f = h.app.staging / urllib.parse.unquote(g[0])
    if not mgoverrides._icon_ok("file:" + f.name) or not f.is_file():
        return h.fail(404, "no such picture")
    im = mgcustom.load_image(f, 256)
    if im is None:
        return h.fail(415, "cannot read that picture")
    import io

    im.thumbnail((256, 256))
    out = io.BytesIO()
    im.save(out, "PNG")
    return h.send(200, out.getvalue(), "image/png")


def api_palette(h, q, g):
    import mgpalette

    seed = q.get("seed", [""])[0]
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", seed):
        return h.fail(400, "seed must look like #RRGGBB")
    return h.send(200, {"dark": mgpalette.scheme(seed, True), "light": mgpalette.scheme(seed, False)})


def api_glyph(h, q, g):
    name = urllib.parse.unquote(g[0])
    f = PKG / "glyphs" / f"{name}.png" if PKG and re.fullmatch(r"[a-z0-9_-]{1,40}", name) else None
    if f is None or not f.is_file():
        return h.fail(404, "no such icon")
    return h.send(200, f.read_bytes(), "image/png", {"Cache-Control": "max-age=3600"})


# ---------------------------------------------------------------- Ventoy (written as the user: a mounted stick belongs to them)
def ventoy_path(path):
    import ventoy_sticks

    p = Path(path or "")
    if not p.is_absolute() or not p.is_dir() or not ventoy_sticks.check(str(p)):
        raise ValueError("that is not the mount point of a Ventoy data partition")
    p = p.resolve()
    if not os.access(p / "ventoy", os.W_OK) and (p / "ventoy").is_dir():
        raise ValueError("the stick is read-only for you: remount it or run the GUI with enough permissions")
    return p


def api_ventoy_sticks(h, q, g):
    import ventoy_sticks

    return h.send(200, {"sticks": ventoy_sticks.detect()})


def api_ventoy_state(h, q, g):
    import cmd_ventoy
    import mgrub

    stick = ventoy_path(q.get("path", [""])[0])
    rules = mgrub.load_rules(PKG)
    conf = mgrub.load_conf(str(stick / "ventoy/material-grub.conf"))
    ov, problems = mgoverrides.load(stick / cmd_ventoy.OVERRIDES)
    files = [
        {"path": r, "name": Path(r).name, "key": cmd_ventoy.key_of(Path(r).name, rules)} for r in cmd_ventoy.scan(stick)
    ]
    icons_dir = stick / cmd_ventoy.ICONS
    icons = (
        sorted(f.name for f in icons_dir.iterdir() if f.suffix.lower() in mgoverrides.IMAGE_EXT)
        if icons_dir.is_dir()
        else []
    )
    themes = (
        sorted(d.name[len("material_") :] for d in (stick / cmd_ventoy.THEMES).glob("material_*") if d.is_dir())
        if (stick / cmd_ventoy.THEMES).is_dir()
        else []
    )
    avail = sorted(p.name for p in (PKG / "res").iterdir()) if PKG and (PKG / "res").is_dir() else ["1920x1080"]
    return h.send(
        200,
        {
            "path": str(stick),
            "conf": {k: conf[k] for k in ("STYLE", "COOKIE", "LOGO", "HINTS", "RAW_NAME", "TIMEOUT", "MODE")},
            "overrides": ov,
            "problems": problems,
            "files": files,
            "icons": icons,
            "installed": themes,
            "resolutions": avail,
            "styles": ["list", "full"],
        },
    )


def api_ventoy_icon(h, q, g):
    import cmd_ventoy

    stick = ventoy_path(q.get("path", [""])[0])
    name = q.get("name", [""])[0]
    if not mgoverrides._icon_ok("file:" + name):
        return h.fail(400, "the file name must be letters, digits, - _ . and end in a picture extension")
    raw = h.body()
    if not raw or len(raw) > 4 * 1024 * 1024:
        return h.fail(400, "the picture must be between 1 byte and 4 MB")
    if not name.lower().endswith(".svg"):
        import io

        from PIL import Image

        try:
            im = Image.open(io.BytesIO(raw))
            im.verify()
        except Exception:
            return h.fail(400, "that is not a readable picture")
    elif b"<svg" not in raw[:65536].lower():
        return h.fail(400, "that is not an SVG file")
    d = stick / cmd_ventoy.ICONS
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(raw)
    return h.send(200, {"name": name})


def api_ventoy_icon_get(h, q, g):
    import cmd_ventoy

    stick = ventoy_path(q.get("path", [""])[0])
    name = q.get("name", [""])[0]
    f = stick / cmd_ventoy.ICONS / name
    if not mgoverrides._icon_ok("file:" + name) or not f.is_file():
        return h.fail(404, "no such picture")
    im = mgcustom.load_image(f, 256)
    if im is None:
        return h.fail(415, "cannot read that picture")
    import io

    im.thumbnail((256, 256))
    out = io.BytesIO()
    im.save(out, "PNG")
    return h.send(200, out.getvalue(), "image/png")


def api_ventoy_apply(h, q, g):
    import cmd_ventoy
    import mgrub

    req = h.json_body()
    stick = ventoy_path(req.get("path", ""))
    draft, errs = mgstate.check_draft({"conf": {}, "overrides": (req.get("draft") or {}).get("overrides", {})})
    if errs:
        return h.fail(400, "; ".join(errs))
    conf = (req.get("draft") or {}).get("conf", {})
    allowed = ("STYLE", "COOKIE", "LOGO", "HINTS", "RAW_NAME", "TIMEOUT", "MODE")
    if not isinstance(conf, dict) or any(k not in allowed or not mgrub._conf_ok(k, str(v)) for k, v in conf.items()):
        return h.fail(400, "the options are not valid")
    res = str(req.get("res", "1920x1080"))
    if not re.fullmatch(r"\d{3,5}x\d{3,5}(,\d{3,5}x\d{3,5})*", res):
        return h.fail(400, "bad resolution")

    def run(emit):
        emit({"event": "step", "n": 1, "total": 3, "msg": "Saving your settings on the stick"})
        mgrub.write_conf(stick / "ventoy/material-grub.conf", {k: str(v) for k, v in conf.items()})
        mgoverrides.save(draft["overrides"], stick / cmd_ventoy.OVERRIDES)
        emit({"event": "ok", "msg": "settings saved"})
        emit({"event": "step", "n": 2, "total": 3, "msg": "Drawing the theme and updating ventoy.json"})
        p = subprocess.Popen(
            [sys.executable, str(MODS / "material-grub-ventoy"), str(stick), "--pkg", str(PKG), "--res", res],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        with p.stdout:
            for line in p.stdout:
                if line.strip():
                    emit({"event": "log", "text": line.rstrip(), "level": "info"})
        rc = p.wait()
        if rc != 0:
            emit({"event": "error", "msg": "the Ventoy tool failed (see the log)", "code": rc})
            emit({"event": "done", "rc": rc, "ok": False})
            return
        emit({"event": "step", "n": 3, "total": 3, "msg": "Done"})
        emit({"event": "ok", "msg": "The stick is themed. Eject it safely before unplugging."})
        emit({"event": "done", "rc": 0, "ok": True})

    try:
        job = h.app.start_callable(run)
    except RuntimeError as e:
        return h.fail(409, str(e))
    return h.send(200, {"job": job.id})


def api_plymouth_preview(h, q, g):
    """A still of the Plymouth boot splash for the unsaved draft: {draft, screen: boot|password|shutdown, size: "1280x720"}. 404 when the part is not installed."""
    if not mgstate.plymouth_info()["installed"]:
        return h.fail(404, "the Plymouth part is not installed")
    req = h.json_body()
    draft, errs = mgstate.check_draft(req.get("draft", {}))
    if errs:
        return h.fail(400, "; ".join(errs))
    screen, size = req.get("screen", "boot"), req.get("size", "1280x720")
    if screen not in mgplymouth.SCREENS:
        return h.fail(400, "unknown screen")
    try:
        mgplymouth.parse_size(size)
        png = mgplymouth.still(MODS, draft, screen, size, icon_dirs=(cfg_icons(), h.app.staging))
    except ValueError as e:
        return h.fail(400, str(e))
    except RuntimeError as e:
        return h.fail(500, str(e))
    return h.send(200, png, "image/png")


def api_plymouth_run(h, q, g):
    """Apply or remove the boot splash alone: {action: apply|remove, cmdline: bool}, as a job with the usual progress events."""
    req = h.json_body()
    if req.get("action") not in ("apply", "remove"):
        return h.fail(400, "the action must be apply or remove")
    if not mgstate.plymouth_info()["installed"]:
        return h.fail(404, "the Plymouth part is not installed")
    try:
        job = h.app.start_job({"verb": "plymouth", "action": req["action"], "cmdline": req.get("cmdline") is True})
    except RuntimeError as e:
        return h.fail(409, str(e))
    return h.send(200, {"job": job.id})


def cfg_icons():
    """Where the installed pictures for custom entries live (the helper writes them there)."""
    return Path(os.environ.get("MG_HELPER_ROOT") or "/") / "etc/material-grub/icons"


def api_apply(h, q, g):
    req = h.json_body()
    try:
        job = h.app.start_job(h.app.apply_request(req.get("draft", {}), req.get("plymouth_cmdline") is True))
    except RuntimeError as e:
        return h.fail(409, str(e))
    return h.send(200, {"job": job.id})


def api_update_check(h, q, g):
    cur = mgstate.installed_version(PKG) or "0"
    try:
        r = urllib.request.Request(
            RELEASES, headers={"User-Agent": "material-grub-gui", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(r, timeout=8) as resp:
            data = json.loads(resp.read(1_000_000))
        latest = str(data.get("tag_name", "")).lstrip("v")
        return h.send(
            200,
            {
                "current": cur,
                "latest": latest,
                "newer": version_tuple(latest) > version_tuple(cur),
                "url": data.get("html_url", ""),
                "notes": str(data.get("body", ""))[:4000],
            },
        )
    except Exception as e:
        return h.send(200, {"current": cur, "error": f"could not reach GitHub ({type(e).__name__})"})


def api_update_run(h, q, g):
    try:
        job = h.app.start_job({"verb": "update"})
    except RuntimeError as e:
        return h.fail(409, str(e))
    return h.send(200, {"job": job.id})


def api_job_events(h, q, g):
    job = h.app.jobs.get(g[0])
    if job is None:
        return h.fail(404, "no such job")
    h.send_response(200)
    h.send_header("Content-Type", "text/event-stream")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Transfer-Encoding", "chunked")
    h.end_headers()

    def chunk(data):
        h.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
        h.wfile.flush()

    i = 0
    while True:
        evs, done = job.wait(i)
        for ev in evs:
            chunk(b"data: " + json.dumps(ev).encode() + b"\n\n")
        i += len(evs)
        if done and not evs:
            h.wfile.write(b"0\r\n\r\n")
            h.wfile.flush()
            return None
        if not evs and not done:
            chunk(b": keep-alive\n\n")


def api_preset_save(h, q, g):
    req = h.json_body()
    draft, errs = mgstate.check_draft(req.get("draft", {}))
    if errs:
        return h.fail(400, "; ".join(errs))
    data = mgpresets.make(req.get("name", ""), draft["conf"], draft["overrides"], h.app.staging)
    mgpresets.save(data["name"], cfg_dir() / "overrides.json", data=data)
    return h.send(200, {"name": data["name"]})


def api_preset_load(h, q, g):
    name = urllib.parse.unquote(g[0])
    try:
        data = mgpresets.load(name, cfg_dir() / "overrides.json")
    except (OSError, ValueError):
        return h.fail(404, "no such preset")
    return preset_to_draft(h, data)


def preset_to_draft(h, data):
    clean, errs = mgpresets.validate(data)
    if clean is None:
        return h.fail(400, "; ".join(errs))
    for n, raw in clean["icons"].items():
        (h.app.staging / n).write_bytes(raw)
    return h.send(200, {"name": clean["name"], "draft": {"conf": clean["conf"], "overrides": clean["overrides"]}})


def api_preset_import(h, q, g):
    return preset_to_draft(h, h.json_body())


def api_preset_export(h, q, g):
    name = urllib.parse.unquote(g[0])
    try:
        data = mgpresets.load(name, cfg_dir() / "overrides.json")
    except (OSError, ValueError):
        return h.fail(404, "no such preset")
    return h.send(200, data, headers={"Content-Disposition": f'attachment; filename="{name}.json"'})


def api_preset_delete(h, q, g):
    try:
        mgpresets.delete(urllib.parse.unquote(g[0]), cfg_dir() / "overrides.json")
    except (OSError, ValueError):
        return h.fail(404, "no such preset")
    return h.send(200, {"ok": True})


ROUTES = {
    ("GET", "/api/state"): api_state,
    ("GET", "/api/status"): api_status,
    ("GET", "/api/ping"): api_ping,
    ("GET", "/api/palette"): api_palette,
    ("GET", "/api/ventoy/sticks"): api_ventoy_sticks,
    ("GET", "/api/ventoy/state"): api_ventoy_state,
    ("POST", "/api/ventoy/icon"): api_ventoy_icon,
    ("GET", "/api/ventoy/icon"): api_ventoy_icon_get,
    ("POST", "/api/ventoy/apply"): api_ventoy_apply,
    ("POST", "/api/preview"): api_preview,
    ("POST", "/api/plymouth/preview"): api_plymouth_preview,
    ("POST", "/api/plymouth/run"): api_plymouth_run,
    ("POST", "/api/icon"): api_icon_upload,
    ("POST", "/api/apply"): api_apply,
    ("POST", "/api/update/check"): api_update_check,
    ("POST", "/api/update/run"): api_update_run,
    ("POST", "/api/presets/save"): api_preset_save,
    ("POST", "/api/presets/import"): api_preset_import,
}
PATTERNS = [
    (("GET", r"/api/icon/([^/]+)"), api_icon_get),
    (("GET", r"/api/glyph/([^/]+)"), api_glyph),
    (("GET", r"/api/jobs/([0-9a-f]{12})/events"), api_job_events),
    (("POST", r"/api/presets/load/([^/]+)"), api_preset_load),
    (("GET", r"/api/presets/export/([^/]+)"), api_preset_export),
    (("DELETE", r"/api/presets/([^/]+)"), api_preset_delete),
]


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def make_server(port=0, idle=0):
    token = secrets.token_urlsafe(24)
    srv = Server(("127.0.0.1", port), Handler)
    srv.app = Handler.app = App(token, srv.server_address[1], idle)
    return srv


def serve(port=0, idle=120, open_browser=True):
    srv = make_server(port, idle)
    app = srv.app
    url = f"http://127.0.0.1:{app.port}/?t={app.token}"
    print(f"Material GRUB GUI: {url}")
    print("Leave this terminal open; close the browser tab (or press Ctrl+C here) to stop.", flush=True)
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
    if idle:

        def watchdog():
            while True:
                time.sleep(5)
                if time.time() - app.last_ping > idle and not app.job_busy:
                    print("no browser connected for a while: stopping", flush=True)
                    os._exit(0)

        threading.Thread(target=watchdog, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
    return 0
