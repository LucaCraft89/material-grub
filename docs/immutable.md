# Immutable systems (ostree / bootc: Silverblue, Kinoite, Bazzite, uCore, ...) - experimental

When `/run/ostree-booted` exists, `install.sh` switches to an immutable layout (it explains it and asks first; `--yes` skips the question, `--immutable` forces it):

- Nothing is written under `/usr`. The package, a Python venv (only if Pillow is missing) and the post-processing script live in `/var/lib/material-grub`; the units go in `/etc/systemd/system`.
- No `grub2-mkconfig` ever runs on these systems, so the `/etc/grub.d` hooks would never execute. Instead the **static `/boot/grub2/grub.cfg`** is edited directly (`install/bin/material-grub-static`): a theme block, the Restart/Shut down entries and the usual structured BLS menu. An untouched copy is kept in `/var/backups/material-grub`, and `--uninstall` restores it.
- Build tools (`grub-mkfont`, `rsvg-convert`) are never layered with `rpm-ostree`. If they are missing, the package is built in a throw-away `podman` container; or build it elsewhere with `./install.sh --stage-only --dist-out DIR` and install with `--pkg DIR/material-grub`.
- ostree replaces `/boot/loader` on every deployment, so the BLS mirrors live in `/boot/grub2/material` instead. ostree writes the next deployment's entry at **shutdown**, so `material-grub-finalize.service` refreshes the mirrors after `ostree-finalize-staged`. A raw **All boot entries** submenu (the live, unmirrored list) is always added as a safety net.
- `bootupctl update` rewrites `grub.cfg`; the path unit notices and re-applies the theme.

What was tested: the whole flow in a container with a read-only `/usr` and a simulated static `grub.cfg` and `/boot/loader` swap (install, refresh after a deployment swap, re-apply after a `grub.cfg` rewrite, uninstall, idempotency), the resulting `grub.cfg` booted in QEMU/OVMF, and the unit files with `systemd-analyze verify`. **Not tested:** a real ostree/bootc boot, `ostree-finalize-staged` ordering at shutdown, SELinux labels on `/var/lib/material-grub`, `bootupctl update`, a read-only `/boot`.

