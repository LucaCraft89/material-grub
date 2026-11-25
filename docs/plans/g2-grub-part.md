
## Implemented (what differs from the design above)

- `material-boot-part.json` and `install/part_grub.py` exist; hooks: `detect`, `plan`, `install`, `verify`, `uninstall`, `doctor` (no `migrate`: the engine runs GRUB's migration steps itself, in `after_install`).
- The hooks start `install/installer.py` as a child process (so the legacy and the unified entry points cannot drift). It is told it is run by the unified installer through `MATERIAL_BOOT_UNIFIED=1`: it then neither repeats the notice/policy/question nor writes the core's version into the state record (only `parts.grub`).
- Two small additions to the core (material-boot-core #16): `ctx.json` (a json run relays the engine's events through `ctx.progress`) and `record: false` in an install result (a part that only built something, `--grub-stage-only`, is not recorded as installed).
- `--ventoy` takes the stick's mount point as a value here (`--grub-ventoy PATH`); the engine's bare `--ventoy` (ask which stick) is still available through `install.sh`.
- A staged root (`--root`) is supported for `--grub-stage-only` and dry runs only: the engine writes to the real system otherwise, and the hook says so instead of pretending.
- Tested: `tests/test_grub_part.py`. The identical-files test builds the theme with `install.sh`'s engine, through the hook, and through `material-boot core install --only grub` on a staged root: the three trees are byte-identical (checked locally, about 2.5 minutes; skipped where `rsvg-convert` is missing). Verified by deliberately breaking the part and the engine (seven breakages, each fails a test).
- **Not verified:** a real (non-stage-only) install through the unified installer on a machine with GRUB; the QEMU boot of such an install; uninstall through the hook; `--progress json` end to end against the GUI. Those need the container/QEMU jobs and are the next step.
