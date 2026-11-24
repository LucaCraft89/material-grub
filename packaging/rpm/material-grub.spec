# Builds from source: the RPM ships the sources; the theme is rendered on the target machine in %posttrans
# (install.sh --from-package), so nothing prebuilt is downloaded. COPR builds this spec from the tagged tarball.
Name:           material-grub
Version:        1.0.0
Release:        1%{?dist}
Summary:        Material 3 Expressive GRUB theme, built from source on your machine
License:        MIT
URL:            https://github.com/LucaCraft89/material-grub
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       grub2-tools
Requires:       grub2-tools-extra
Requires:       librsvg2-tools
Requires:       python3
Requires:       python3-pip
Requires:       python3-pillow

%description
Material 3 Expressive theme for GRUB with per-entry scenes, key hints and a plain-menu fallback.
The package contains the sources only; the theme is rendered when the package is installed or updated,
with the same safety nets as the installer (validate, roll back, notify).

%package gui
Summary:        Optional graphical editor for the Material GRUB theme
Requires:       %{name} = %{version}-%{release}
Requires:       python3-pillow
Requires:       polkit
Recommends:     librsvg2-tools

%description gui
A local web UI (opens in your browser) to switch styles, recolour, rename, reorder and hide boot entries, edit Ventoy
sticks, save presets and update, with a live preview. It never runs as root itself: changes go through polkit.
Not installed with the theme; install it only if you want it.

%prep
%autosetup -n %{name}-%{version}

%install
sh packaging/common/install-tree.sh . %{buildroot}
sh packaging/common/install-gui-tree.sh . %{buildroot}

%post
# first install and upgrade of the files only; the theme is built in %%posttrans, after the whole transaction
:

%posttrans
/usr/share/material-grub-src/install.sh --from-package || :

%preun
if [ $1 -eq 0 ]; then sh /usr/share/material-grub-src/install/uninstall.sh || :; fi

%files
%license LICENSE
%doc README.md
%config(noreplace) %{_sysconfdir}/material-grub.conf
%{_datadir}/material-grub-src

%files gui
%{_datadir}/material-grub-gui
%{_libexecdir}/material-grub-gui-helper
%{_datadir}/polkit-1/actions/org.material-grub.gui.policy
%{_datadir}/applications/material-grub-gui.desktop

%changelog
* Tue Nov 24 2026 LucaCraft89 <noreply@users.noreply.github.com> - 1.0.0-1
- Release 1.0.0.

* Wed Nov 18 2026 LucaCraft89 <noreply@users.noreply.github.com> - 0.7.1-1
- Release 0.7.1.

* Wed Nov 18 2026 LucaCraft89 <noreply@users.noreply.github.com> - 0.7.0-1
- Release 0.7.0.

* Wed Nov 18 2026 LucaCraft89 <noreply@users.noreply.github.com> - 0.6.0-1
- Release 0.6.0.

* Wed Nov 18 2026 LucaCraft89 <noreply@users.noreply.github.com> - 0.5.0-1
- Packaging.
