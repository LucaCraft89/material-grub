Container helpers (no VM, no real disks).

- `probe`: a stub `grub-probe` so `grub-mkconfig` runs in a container.
- `dry_run.sh DISTRO`: runs `install.sh --dry-run` against a fake `/boot` and checks that the system is unchanged afterwards.
  Example: `podman run --rm -v "$PWD:/src:ro,z" -v "$PWD/build/out:/out:z" debian:stable sh /src/tests/containers/dry_run.sh debian`
  (build the package first: `python scripts/package.py --res 1920x1080`).
