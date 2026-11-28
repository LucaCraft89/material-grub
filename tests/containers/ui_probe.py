"""Starts the INSTALLED editor (`material-boot ui`, from the core package, with this GRUB package) in a distro container and talks to it like a browser would: the token, the state,
a live preview PNG for every style, the security checks. stdlib only. usage: python3 gui_probe.py"""

import json
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

proc = subprocess.Popen(
    ["material-boot", "ui", "--no-browser", "--idle", "0"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
url = None
t = time.time()
while time.time() - t < 30 and url is None:
    line = proc.stdout.readline()
    m = re.search(r"(http://127\.0\.0\.1:\d+)/\?t=([\w-]+)", line)
    if m:
        base, token = m.group(1), m.group(2)
        url = base
if url is None:
    proc.kill()
    sys.exit("the editor did not start")


def call(method, path, body=None, auth=True, headers=None):
    h = {"X-MG-Token": token} if auth else {}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


fail = []
try:
    st, body, _ = call("GET", "/api/state")
    state = json.loads(body)
    print("state:", st, state["version"], len(state["entries"]), "entries", "demo" if state["demo"] else "real")
    if st != 200 or not state["installed"] or not state["entries"]:
        fail.append("state is empty or not installed")
    if call("GET", "/api/state", auth=False)[0] != 403:
        fail.append("the API answered without the token")
    if call("GET", "/api/state", headers={"Origin": "http://evil.example"})[0] != 403:
        fail.append("the API answered a foreign Origin")
    first = state["entries"][0]["class"]
    for style in ("rail", "clean", "list", "split"):
        st, png, hd = call(
            "POST",
            "/api/preview",
            {
                "draft": {"conf": {"STYLE": style}, "overrides": {"seed": {"mode": "single", "color": "#7E57C2"}}},
                "class": first,
                "scale": 0.4,
            },
        )
        ok = st == 200 and png[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = struct.unpack(">II", png[16:24]) if ok else (0, 0)
        print(f"preview {style}: {st} {w}x{h}")
        if not ok or w < 300:
            fail.append(f"preview {style} failed ({st})")
    if call("POST", "/api/apply", {"draft": {"conf": {"STYLE": "neon"}}})[0] != 400:
        fail.append("a bad draft was not refused")
    page = call("GET", "/", auth=False, headers={"Cookie": f"mg={token}"})
    if page[0] != 200 or b"Material Boot" not in page[1]:
        fail.append("the page did not load with the cookie")
    font = call("GET", "/fonts/GoogleSansFlex-VF.ttf")
    if font[0] != 200 or len(font[1]) < 100000:
        fail.append("the font is not served")
finally:
    proc.terminate()
if fail:
    sys.exit("EDITOR PROBE FAILED:\n  " + "\n  ".join(fail))
print("EDITOR PROBE OK")
