"""Single source of truth: entries (distros + system actions), seeds, and GRUB class aliases.
src: 'si' = brand hex from Simple Icons (CC0); 'proposed' = hand-picked, needs review."""

FL = "assets/font-logos/%s.svg"  # relative to the repository root (see ROOT below); the glyph sources
MS = "assets/material-symbols/%s.svg"
# key, title, subtitle, glyph path, seed, src, extra class aliases (lowercase; key itself is always an alias)
D = [
    ("fedora", "Fedora", "Fedora Linux", FL % "fedora", "#294172", "chosen", ["fedora-asahi-remix"]),
    ("nobara", "Nobara", "Nobara Linux", FL % "nobara", "#5B5BD6", "proposed", []),
    ("bazzite", "Bazzite", "Gaming OS", None, "#8A4FFF", "proposed", ["steamos", "chimeraos"]),
    (
        "ubuntu",
        "Ubuntu",
        "Ubuntu Linux",
        FL % "ubuntu",
        "#E95420",
        "si",
        ["xubuntu", "lubuntu", "ubuntu-mate", "ubuntu_budgie"],
    ),
    ("kubuntu", "Kubuntu", "Kubuntu Linux", FL % "kubuntu", "#0079C1", "si", []),
    ("debian", "Debian", "GNU/Linux", FL % "debian", "#A80030", "chosen", []),
    ("devuan", "Devuan", "GNU+Linux", FL % "devuan", "#6B6FA8", "proposed", []),
    (
        "kali",
        "Kali Linux",
        "Security",
        FL % "kali-linux",
        "#557C94",
        "si",
        ["kali-linux", "kali_linux", "kali_gnu_linux"],
    ),
    ("parrot", "Parrot OS", "Security", FL % "parrot", "#15E0ED", "si", ["parrot-os", "parrot_security"]),
    ("tails", "Tails", "Amnesic system", FL % "tails", "#56347C", "si", []),
    ("mxlinux", "MX Linux", "Midweight", FL % "mxlinux", "#3D6EA8", "proposed", ["mx", "mx-linux", "mx_linux"]),
    ("deepin", "Deepin", "Deepin Linux", FL % "deepin", "#007CFF", "si", ["deepin-linux"]),
    ("zorin", "Zorin OS", "Zorin OS", FL % "zorin", "#15A6F0", "si", ["zorin-os", "zorinos"]),
    (
        "linuxmint",
        "Linux Mint",
        "From freedom came elegance",
        FL % "linuxmint",
        "#87CF3E",
        "si",
        ["mint", "linux_mint", "linux-mint"],
    ),
    (
        "elementary",
        "elementary OS",
        "elementary OS",
        FL % "elementary",
        "#64BAFF",
        "si",
        ["elementaryos", "elementary-os"],
    ),
    ("pop", "Pop!_OS", "Pop!_OS", FL % "pop-os", "#48B9C7", "si", ["pop_os", "pop-os", "popos", "pop!_os", "pop_"]),
    ("arch", "Arch Linux", "Rolling release", FL % "archlinux", "#00A6B2", "chosen", ["archlinux", "arch_linux"]),
    ("endeavouros", "EndeavourOS", "Arch-based", FL % "endeavour", "#7F7FFF", "si", ["endeavour", "endeavour_os"]),
    ("manjaro", "Manjaro", "Arch-based", FL % "manjaro", "#35BF5C", "si", ["manjaro-linux", "manjaro_linux"]),
    ("garuda", "Garuda Linux", "Arch-based", FL % "garuda", "#8C4FD8", "proposed", ["garuda-linux", "garuda_linux"]),
    ("artix", "Artix Linux", "Arch-based, no systemd", FL % "artix", "#10A0CC", "si", ["artix-linux", "artix_linux"]),
    ("arcolinux", "ArcoLinux", "Arch-based", FL % "arcolinux", "#3B8DD9", "proposed", []),
    ("archcraft", "Archcraft", "Arch-based", FL % "archcraft", "#4C8BF5", "proposed", []),
    ("cachyos", "CachyOS", "Arch-based, optimized", FL % "cachyos", "#2BB5A0", "proposed", ["cachy", "cachy_os"]),
    ("biglinux", "BigLinux", "BigLinux", FL % "biglinux", "#2E7DD7", "proposed", []),
    (
        "opensuse",
        "openSUSE",
        "openSUSE",
        FL % "opensuse",
        "#73BA25",
        "si",
        ["suse", "opensuse-leap", "opensuse-tumbleweed", "opensuse_leap", "opensuse_tumbleweed", "sles", "sled"],
    ),
    ("nixos", "NixOS", "Declarative Linux", FL % "nixos", "#5277C3", "si", ["nix"]),
    ("gentoo", "Gentoo", "Gentoo Linux", FL % "gentoo", "#54487A", "si", []),
    ("void", "Void Linux", "Void Linux", FL % "void", "#478061", "si", ["void-linux", "void_linux"]),
    ("alpine", "Alpine", "Alpine Linux", FL % "alpine", "#0D597F", "si", ["alpine-linux", "alpine_linux"]),
    ("slackware", "Slackware", "Slackware Linux", FL % "slackware", "#5A7FB5", "proposed", []),
    ("solus", "Solus", "Solus", FL % "solus", "#5294E2", "si", []),
    ("mageia", "Mageia", "Mageia Linux", FL % "mageia", "#2397D4", "proposed", []),
    ("puppy", "Puppy Linux", "Puppy Linux", FL % "puppy", "#C68A3A", "proposed", ["puppy-linux"]),
    ("vanilla", "Vanilla OS", "Vanilla OS", FL % "vanilla", "#F5A623", "proposed", ["vanilla-os", "vanillaos"]),
    ("sabayon", "Sabayon", "Sabayon Linux", FL % "sabayon", "#3D5AFE", "proposed", []),
    ("openwrt", "OpenWrt", "OpenWrt", FL % "openwrt", "#00B5E2", "si", []),
    ("postmarketos", "postmarketOS", "postmarketOS", FL % "postmarketos", "#00A651", "proposed", []),
    ("qubes", "Qubes OS", "Reasonably secure", FL % "qubesos", "#3874D8", "si", ["qubesos", "qubes-os"]),
    ("neon", "KDE neon", "KDE neon", FL % "kde-neon", "#1D99F3", "si", ["kde-neon", "kde_neon"]),
    ("rocky", "Rocky Linux", "Rocky Linux", FL % "rocky-linux", "#10B981", "si", ["rocky-linux", "rocky_linux"]),
    ("almalinux", "AlmaLinux", "AlmaLinux", FL % "almalinux", "#0F4266", "proposed", ["alma", "almalinux_os"]),
    ("centos", "CentOS", "CentOS", FL % "centos", "#7A3E9D", "proposed", ["centos-stream", "centos_stream"]),
    ("rhel", "Red Hat", "Red Hat Enterprise Linux", FL % "redhat", "#EE0000", "si", ["redhat", "red_hat", "red-hat"]),
    ("freebsd", "FreeBSD", "FreeBSD", FL % "freebsd", "#AB2B28", "si", []),
    ("openbsd", "OpenBSD", "OpenBSD", FL % "openbsd", "#F2CA30", "si", []),
    ("guix", "GNU Guix", "Guix System", FL % "gnu-guix", "#A42E2B", "si", ["gnu-guix", "guix-system"]),
    (
        "raspberrypi",
        "Raspberry Pi OS",
        "Raspberry Pi OS",
        FL % "raspberry-pi",
        "#A22846",
        "si",
        ["raspbian", "raspios", "raspberry-pi"],
    ),
    ("tux", "Linux", "Generic Linux", FL % "tux", "#FFB300", "chosen", ["gnu-linux", "unknown", "os", "gnu"]),
    (
        "windows11",
        "Windows 11",
        "Boot Manager",
        MS % "window",
        "#0078D4",
        "chosen",
        ["windows", "win", "microsoft", "windows_boot_manager"],
    ),
    ("windows10", "Windows 10", "Boot Manager", MS % "window", "#1E88E5", "proposed", ["win10"]),
    ("firmware", "Firmware", "UEFI settings", MS % "memory", "#7E57C2", "chosen", ["efi", "uefi", "uefi-firmware"]),
    ("reboot", "Restart", "Reboot the machine", MS % "restart_alt", "#2E9E5B", "chosen", ["restart"]),
    ("shutdown", "Shut down", "Power off", MS % "power_settings_new", "#C62828", "chosen", ["poweroff", "halt"]),
]
# Scene-only entries: built like the others (scene, palette, glyph) but NOT part of D, so they never match an entry title on a PC and are not in the gallery.
# "iso": the grey disc scene Ventoy shows for a file it cannot place (the PC fallback stays Tux).
# "pnlug": Pordenone Linux User Group (Ventoy only, matched on the ISO name in any letter case); its scene shows the association's own logo (vendor/pnlug), the glyph is only the Tux used in small places. Seed: the logo's red.
X = [
    ("iso", "Disk image", "Unrecognised image", MS % "album", "#8B8E94", "chosen", []),
    ("pnlug", "PNLug", "Pordenone Linux User Group", None, "#C22020", "chosen", []),
]
ENTRIES = [(k, t, s, g or FL % "tux") for k, t, s, g, *_ in D + X]
SEEDS = {"base": "#0B3D2E", **{k: seed for k, _, _, _, seed, *_ in D + X}}
CLASSES = {k: [k] + [a for a in al if a != k] for k, *_, al in D + X}

# The glyphs that are not catalog entries (the rail's gear, the kernel tag, Ventoy's folder/back/play): name -> SVG.
EXTRA_GLYPHS = {
    "gear": MS % "settings",
    "wrench": MS % "build",
    "kernel": MS % "terminal",
    "tag": MS % "tag",
    "folder": MS % "folder",
    "back": MS % "arrow_back",
    "play": MS % "play_arrow",
}
# Words that say nothing about the distro; they never become a title rule. The same set as material-grub's mgrub.GENERIC (which moves here later and
# then imports it from this file; until then a drift shows up as a different rules.json in the build comparison).
GENERIC = {"os", "gnu", "gnu-linux", "unknown", "win", "mx", "nix", "linux"}
