"""Boot the built package in QEMU + OVMF and check what GRUB really draws. usage: python3 tests/boot_smoke.py [WxH] [dark|light] [rail|clean|list] [rail|clean|list]
Needs: dist/material-grub (built for that resolution), qemu-system-x86_64, OVMF, grub-mkimage, Pillow. Env: BOOT_WAIT (raise it without KVM)."""
import os, shutil, subprocess, sys
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import make_screenshots as M
res = sys.argv[1] if len(sys.argv) > 1 else "1920x1080"; scheme = sys.argv[2] if len(sys.argv) > 2 else "dark"; style = sys.argv[3] if len(sys.argv) > 3 else "rail"
conf = ROOT / f"build/smoke-{style}.conf"; conf.parent.mkdir(exist_ok=True); conf.write_text(f"STYLE={style}\n"); os.environ["MATERIAL_CONF"] = str(conf)   # never read the real /etc/material-grub.conf
w, h = map(int, res.split("x")); tree = ROOT / "build/ci-tree"; M.build_tree(res, tree)
subprocess.run([sys.executable, ROOT / "scripts/qemu_tree.py", tree, res, "down", "down"], check=True, env={**os.environ, "BOOT_WAIT": os.environ.get("BOOT_WAIT", "20"), "KEY_WAIT": os.environ.get("KEY_WAIT", "3")})
out = ROOT / "build/ci-shots"; out.mkdir(exist_ok=True); shots = []
for i, n in enumerate(("fedora", "advanced", "windows")):
    shutil.copy(ROOT / f"build/tree-{i}.png", out / f"{scheme}-{style}-{res}-{n}.png"); shots.append(Image.open(out / f"{scheme}-{style}-{res}-{n}.png").convert("RGB"))
fail = []
for im, n in zip(shots, ("fedora", "advanced", "windows")):
    if im.size != (w, h): fail.append(f"{n}: screen is {im.size}, expected {(w, h)} (GRUB did not set the mode or the theme failed to load)")
    if max(ImageStat.Stat(im.resize((96, 54))).stddev) < 12: fail.append(f"{n}: image is nearly uniform (theme not drawn)")
    lum = sum(ImageStat.Stat(im.resize((32, 18))).mean) / 3
    if (scheme == "dark") != (lum < 128): fail.append(f"{n}: luminance {lum:.0f} does not match the {scheme} scheme")
for a, b, label in ((0, 1, "fedora vs advanced"), (0, 2, "fedora vs windows")):
    if ImageChops.difference(shots[a], shots[b]).getbbox() is None: fail.append(f"{label}: identical screenshots (selection did not change the scene)")
if fail: sys.exit("BOOT SMOKE TEST FAILED:\n  " + "\n  ".join(fail))
print(f"boot smoke test ok ({res}, {scheme}, {style}): shots in {out}")
