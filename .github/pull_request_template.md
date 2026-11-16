## What and why

<!-- One or two sentences. Link the issue (Fixes #N). -->

## Type

- [ ] New or changed distro (`scripts/catalog.py`, see docs/adding-a-distro.md)
- [ ] Installer / GRUB hooks
- [ ] Rendering / layout
- [ ] Docs

## How it was tested

- [ ] `make package` builds
- [ ] `make screenshots` (QEMU + OVMF), screenshot attached for visual changes (dark; light too if colours changed)
- [ ] Installer run in a container with `--stage-only` (distro: ...)
- [ ] Tested on real hardware (distro, GRUB version, resolution): ...

**Not verified:** <!-- be explicit, e.g. "did not boot a real BLS system" -->

## Checklist

- [ ] README / CHANGELOG ("Unreleased") updated if behaviour changed
- [ ] New third-party assets are listed in THIRD_PARTY.md with their licence
- [ ] No "Google" / "Google Sans" in generated font names (see fonts/README.md)
