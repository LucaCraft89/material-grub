#!/bin/sh
# Builds a package of the core from the checked-out tree inside a distro container.   usage: sh build_pkg.sh rpm|deb|arch
# /src: the repository (read-only)   /out: receives the package
set -e
fmt=$1
V=$(cat /src/VERSION)
W=/tmp/build; rm -rf $W; mkdir -p $W
tar -C /src --exclude=./dist --exclude=./build --exclude=./.git --exclude='__pycache__' --exclude=./.ruff_cache --transform "s,^\.,material-boot-core-$V," -czf $W/material-boot-core-$V.tar.gz .
cd $W
case $fmt in
  rpm)
    dnf install -y -q rpm-build tar gzip >/dev/null
    rpmbuild -ba --define "_sourcedir $W" --define "_topdir $W/rpmbuild" /src/packaging/rpm/material-boot-core.spec >/dev/null
    cp $W/rpmbuild/RPMS/noarch/*.rpm /out/ ;;
  deb)
    apt-get update -qq >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debhelper dpkg-dev >/dev/null 2>&1
    tar xzf material-boot-core-$V.tar.gz; cd material-boot-core-$V
    cp -a packaging/debian/debian debian
    dpkg-buildpackage -us -uc -b >/tmp/dpkg.log 2>&1 || { tail -30 /tmp/dpkg.log; exit 1; }
    cp $W/*.deb /out/ ;;
  arch)
    pacman -Syu --noconfirm --needed base-devel >/dev/null 2>&1
    useradd -m builder; mkdir -p $W/pkg; cp /src/packaging/arch/* $W/pkg/; chown -R builder $W
    su builder -c "cd $W/pkg && MB_SOURCE=file://$W/material-boot-core-$V.tar.gz makepkg -f -d --noconfirm --skipinteg 2>&1 | tail -25"
    cp $W/pkg/*.pkg.tar.* /out/ ;;
esac
ls -la /out
