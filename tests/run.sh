#!/bin/sh
# Fast checks that need no root, QEMU or network: sh -n tests/run.sh   (CI runs this plus the installer matrix and a boot test)
set -eu
cd "$(dirname "$0")/.."
export MATERIAL_OVERRIDES=/nonexistent/material-grub/overrides.json   # the tests must not read the overrides of the machine they run on
echo "== shell syntax"
for f in install.sh install/*.sh install/material-grub install/05_material install/15_material_menu install/90_material_system tests/run.sh packaging/common/*.sh tests/containers/*.sh; do sh -n "$f" && echo "ok $f"; done
echo "== python syntax"
python3 -m py_compile scripts/*.py install/bin/material-grub-* install/bin/*.py install/*.py tests/*.py gui/*.py gui/material-grub-gui && echo ok
echo "== front end syntax"
if command -v node >/dev/null 2>&1; then for f in gui/web/*.js; do node --check "$f" && echo "ok $f"; done; else echo "skip node (not installed)"; fi
echo "== lint (when ruff / shellcheck are installed; CI always runs them)"
if command -v ruff >/dev/null 2>&1; then ruff check . && ruff format --check . && echo "ok ruff"; else echo "skip ruff (not installed)"; fi
if command -v shellcheck >/dev/null 2>&1; then shellcheck -x --severity=warning install.sh install/*.sh install/05_material install/15_material_menu install/90_material_system tests/run.sh packaging/common/*.sh && echo "ok shellcheck"; else echo "skip shellcheck (not installed)"; fi
echo "== unit tests"
python3 tests/test_core_link.py
python3 tests/test_mgrub.py
python3 tests/test_overrides.py
python3 tests/test_presets.py
python3 tests/test_palette.py
python3 tests/test_panel.py
python3 tests/test_custom.py
python3 tests/test_customise.py
python3 tests/test_cli.py
python3 tests/test_plugins.py
python3 tests/test_grub_part.py
python3 tests/test_upgrade.py
python3 tests/test_gui_server.py
python3 tests/test_monitors.py
python3 tests/test_tui.py
python3 tests/test_ventoy.py
python3 tests/test_mgtheme.py
python3 tests/test_grubscript.py
python3 tests/test_safety.py
python3 tests/test_dryrun.py
python3 tests/test_installer.py
python3 tests/test_doctor.py
python3 tests/test_preview.py
python3 tests/test_windows.py
python3 scripts/gen_distro_table.py --check
echo "== pipeline test (needs a built package)"
python3 tests/test_pipeline.py
