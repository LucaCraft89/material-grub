"""Compatibility name: this module moved to material-boot-core (material_boot.scenes). The old name stays so that every importer keeps working."""

import sys

import mgcore  # noqa: F401  (puts the core on sys.path)
from material_boot import scenes

sys.modules[__name__] = scenes
