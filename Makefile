PY   ?= .venv/bin/python
RES  ?= 1920x1080

.PHONY: venv package screenshots install uninstall clean
venv:            ## create the build virtualenv
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
package:         ## render scenes + per-resolution bundles into dist/material-grub (a few minutes)
	$(PY) scripts/package.py
screenshots:     ## boot the theme in QEMU/OVMF and write docs/screenshots/*.png
	$(PY) scripts/make_screenshots.py
install: package ## install on this machine (needs sudo); RES=1920x1200 make install
	sudo sh install/install.sh --res $(RES)
uninstall:       ## remove the theme and hooks (needs sudo)
	sudo sh install/uninstall.sh
clean:
	rm -rf build dist theme-*
