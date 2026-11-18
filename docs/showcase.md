# Showcase: customised menus and the GUI

Every picture on this page is produced by the test suite: the menus are real GRUB screenshots (QEMU + OVMF, see `tests/boot_features.py`), the GUI shots come from a real browser run (`tests/gui_e2e.py`). Both run in CI on every change. How to do it yourself: [usage.md](usage.md), [customising.md](customising.md), [gui.md](gui.md).

## One colour for the whole theme

`material-grub colour '#7E57C2'` (or the installer's *Colours* step, or the GUI): every entry uses the Material 3 palette of one seed colour. Here lavender, in the four styles.

<table>
<tr>
<td><img src="screenshots/features/single-rail.png" alt="One colour, rail"></td>
<td><img src="screenshots/features/single-clean.png" alt="One colour, clean"></td>
</tr>
<tr>
<td><img src="screenshots/features/single-list.png" alt="One colour, list"></td>
<td><img src="screenshots/features/single-split.png" alt="One colour, split"></td>
</tr>
</table>

## Per-entry colour and name

Fedora renamed "Work laptop" and recoloured tangerine, everything else untouched. The name is drawn by the theme; GRUB's own entry titles are not changed (the raw title stays at the bottom).

<table>
<tr>
<td><img src="screenshots/features/custom-entry-rail.png" alt="Custom entry, rail"></td>
<td><img src="screenshots/features/custom-entry-list.png" alt="Custom entry, list"></td>
</tr>
</table>

## Windows first (and hiding entries)

`"groups": ["windows", "linux", "system"]` reorders the real GRUB menu, not only the pictures. Hiding removes entries from the menu (here Windows and Ubuntu are hidden in the second picture's menu).

<table>
<tr>
<td><img src="screenshots/features/windows-first-rail.png" alt="Windows first, rail"></td>
<td><img src="screenshots/features/windows-first-split.png" alt="Windows first, split"></td>
</tr>
<tr>
<td><img src="screenshots/features/windows-first-list.png" alt="Windows first, list"></td>
<td><img src="screenshots/features/hidden-rail.png" alt="Windows and Ubuntu hidden"></td>
</tr>
</table>

## No firmware logo? The penguin

On machines whose firmware has no boot logo (virtual machines, many desktops) the cookie gets the Linux penguin instead of staying empty. With a real logo (BGRT), that is drawn instead.

<table>
<tr>
<td><img src="screenshots/features/penguin-rail.png" alt="Penguin in the cookie, rail"></td>
<td><img src="screenshots/features/penguin-clean.png" alt="Penguin in the cookie, clean"></td>
</tr>
</table>

## Ventoy: your own name, colour and icon per image

Tested on real Ventoy 1.1.18 (QEMU + OVMF) in both styles and both modes, with the customisation made by hand or in the GUI's *Ventoy* page. Here: Fedora is "Work laptop", tangerine, with a picture of the user's own (the green square), everything else untouched; and the same stick in one colour.

<table>
<tr>
<td><img src="screenshots/ventoy-custom/list-custom.png" alt="Ventoy list style, custom image"></td>
<td><img src="screenshots/ventoy-custom/full-custom.png" alt="Ventoy full-screen style, custom image"></td>
</tr>
<tr>
<td><img src="screenshots/ventoy-custom/snapshot-custom.png" alt="Ventoy snapshot list, custom row"></td>
<td><img src="screenshots/ventoy-custom/single-colour.png" alt="Ventoy, one colour for the whole stick"></td>
</tr>
<tr>
<td><img src="screenshots/ventoy-custom/gui-editor.png" alt="The GUI's Ventoy page while customising an image"></td>
<td><img src="screenshots/ventoy-custom/gui-written-stick.png" alt="The stick as the GUI wrote it, booted in Ventoy"></td>
</tr>
</table>

Ventoy 1.1.18 does not show a `menu_alias` in its list (not even on a plain stick), so the custom name is drawn on the image's screen (and in the row of the snapshot list), while the plain list keeps the file name.

## The GUI

A local web UI in your browser (`material-grub gui`), Material 3 Expressive with a forest-green seed and Google Sans Flex. The live preview on the right is drawn by the same code that writes your real menu.

| | |
|---|---|
| ![Overview](screenshots/gui/overview-light.png) Overview and health checks | ![Entries](screenshots/gui/entries.png) Entries: drag and drop, per-entry editor, live preview |
| ![Colours](screenshots/gui/colours.png) One seed colour or a colour per entry, 32 presets | ![Style list](screenshots/gui/style-list.png) The four styles with a live preview |
| ![Apply](screenshots/gui/apply-verbose.png) Apply: progress with the wavy bar and a verbose log | ![Failed](screenshots/gui/apply-failed.png) A failing apply is reported and your settings come back |
| ![Presets](screenshots/gui/presets.png) Presets | ![Ventoy](screenshots/gui/ventoy.png) Ventoy sticks: per-image name, colour and icon |
| ![Dark overview](screenshots/gui/overview-dark.png) Dark interface | ![Dark entries](screenshots/gui/entries-dark.png) Dark interface, entries |

On a phone the sidebar becomes a bottom bar:

<table>
<tr>
<td><img src="screenshots/gui/phone-overview.png" alt="Phone, overview" width="260"></td>
<td><img src="screenshots/gui/phone-entries.png" alt="Phone, entries" width="260"></td>
</tr>
</table>
