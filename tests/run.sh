#!/bin/sh
# Fast checks that need no root, QEMU or network: sh -n tests/run.sh   (CI runs this plus the installer matrix and a boot test)
set -eu
cd "$(dirname "$0")/.."
echo "== shell syntax"
for f in install.sh install/*.sh install/05_material install/15_material_menu install/90_material_system tests/run.sh; do sh -n "$f" && echo "ok $f"; done
echo "== python syntax"
python3 -m py_compile scripts/*.py install/bin/material-grub-* install/bin/*.py install/*.py tests/*.py && echo ok
echo "== unit tests"
python3 tests/test_mgrub.py
python3 tests/test_monitors.py
python3 tests/test_tui.py
echo "== pipeline test (needs a built package)"
python3 tests/test_pipeline.py
