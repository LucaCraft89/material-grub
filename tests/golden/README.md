Real `grub-mkconfig` output used as golden input for the GRUB script scanner.

- `debian.cfg`, `ubuntu.cfg`, `arch.cfg`, `fedora.cfg`: generated in the distro's own container (Debian stable, Ubuntu 24.04, Arch, Fedora) with fake kernels in `/boot`
  and a stub `grub-probe`; only the OS name was substituted where the container has no `/etc/os-release` name. `fedora.cfg` uses `blscfg` (the entries in `bls/` stand in for `/boot/loader/entries`).
- `*.annotated.cfg`: what `material-grub-classes` produced from them with the regex-based version of 0.5.0, which is the reference the parser must keep reproducing.
