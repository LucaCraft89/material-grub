# Packaging

The packages ship **sources only**. The theme is never prebuilt: it is rendered on the target machine, in the package's
post-install step, by `install.sh --from-package` (the same code as the installer, with the same safety nets: the new `grub.cfg` is
validated with `grub-script-check`, rolled back if it is not valid, and a failure is reported in the journal, with `wall` and in
`/var/lib/material-grub/last-error`, but the package transaction never fails). Building needs network access once (pinned, hashed
Python requirements from PyPI).

| Format | Files | Post-install step |
|---|---|---|
| Arch | `packaging/arch/PKGBUILD`, `material-grub.install`, `material-grub.hook` | `post_install` / `post_upgrade`; a pacman hook re-applies after kernel changes |
| Fedora / RHEL (COPR) | `packaging/rpm/material-grub.spec` | `%posttrans`; `/etc/material-grub.conf` is `%config(noreplace)` |
| Debian / Ubuntu | `packaging/debian/debian/` (copied to `./debian` for the build), `packaging/debian/kernel-hook` | `postinst configure`; kernel hooks in `/etc/kernel/postinst.d` and `postrm.d` |

`packaging/common/install-tree.sh` copies the sources to `/usr/share/material-grub-src` for all three.

## Cutting a release

1. `python3 scripts/bump_version.py X.Y.Z` (updates `VERSION`, the PKGBUILD, the spec and the Debian changelog; `--check` verifies they agree).
2. Tag `vX.Y.Z` and publish the GitHub release (the source tarball is the one GitHub generates).
3. Arch: put the real sums in `sha256sums` (`makepkg -g`) and push to the AUR (registrations are closed for now, so the PKGBUILD is only tested in CI).
4. Fedora: trigger the COPR build from the tag (COPR builds the SRPM itself). Debian/Ubuntu: see the apt repository notes below.
5. The CI jobs `package-arch`, `package-rpm` and `package-deb` build the packages from the checked-out tree on every PR.

## Local builds

```sh
git archive --prefix=material-grub-$(cat VERSION)/ -o material-grub-$(cat VERSION).tar.gz HEAD
# Arch (as a normal user, in an Arch container):  MG_SOURCE=file://$PWD/material-grub-X.Y.Z.tar.gz makepkg -f
# Fedora: rpmbuild -ba --define "_sourcedir $PWD" packaging/rpm/material-grub.spec
# Debian: cp -a packaging/debian/debian debian && dpkg-buildpackage -us -uc -b
```

## Updates

The scriptlets run the installer (`install.sh --from-package`), so a package install or upgrade gets the same detection and update steps as a source install: it notices an existing install (also one made from source, which it takes over), keeps the settings, backs up what it changes and records itself in `/var/lib/material-grub/state.json` (see [install.md](install.md#updating-and-existing-installs)).

A plain `dnf upgrade`, `pacman -Syu` or `apt upgrade` installs the new sources and runs the same post-install step: backup of `grub.cfg` and
`/etc/default/grub` in `/var/backups/material-grub`, theme rendered into a new directory and swapped in, classes applied, validation,
rollback on failure. `/etc/material-grub.conf` is never overwritten. The repositories that serve the updates are set up by the maintainer
(COPR project, apt repository with a signing key; the AUR when registrations reopen).

## The editor

The graphical editor used to be a second package, `material-grub-gui`. Since 1.2.0 it is `material-boot ui` and ships in the **material-boot-core** package, which obsoletes `material-grub-gui` (rpm `Obsoletes`, deb `Replaces`/`Breaks`, Arch `replaces`). This repository no longer builds a GUI package.

