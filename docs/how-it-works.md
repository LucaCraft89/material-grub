# How it works (and what GRUB cannot do)

GRUB themes are static: no animation, no runtime recolouring, no blur, bitmap fonts only. This theme works
within those limits:

```
                    ┌────────────────────── at build time (your PC, once) ───────────────────────┐
 catalog.py ──► Material 3 palettes ──► scene renderer ──► dist/material-grub (scenes, fonts, tools)
                                                              │
                    ┌────────────── at every grub-mkconfig / kernel change (root) ──────────────┘
                    ▼
  05_material (grub.d) ─► picks resolution bundle, copies scenes, converts the BGRT logo
  material-grub-classes ─► names the entries, builds the BLS "default + Advanced" mirrors
  material-grub-scenes  ─► bakes info pills, gear/wrench hero and the rail into one PNG per entry
                    ▼
  GRUB ─► shows the PNG that belongs to the highlighted entry (via a unique per-entry class)
```

The central trick: a `boot_menu` that shows one full-screen item at a time, where each item's "icon" is a
whole scene. Selection changes swap the scene, which gives the whole-screen colour change.

**Not possible in GRUB, and therefore not in this theme**

| Wish | Reality |
|---|---|
| Animated colour transitions / spring motion | No animation engine; scene changes are instant. |
| Wavy (M3 Expressive) progress bar | The bar is a stretched 9-slice image; it is a flat rounded pill instead. |
| Countdown / raw-name text coloured per entry | Colours in `theme.txt` are global, so they are neutral. |
| Peeking neighbour entries | `boot_menu` only draws whole items. |
| Reading the UEFI logo live at boot | GRUB has no BGRT reader; it is converted whenever the config is regenerated. |
| One `theme.txt` for every resolution | Sizes are in pixels; a bundle per resolution is generated, GRUB scales the scenes. |


