#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# For the disposable F-Droid buildserver VM only; never run on a developer host.
set -eu
[ "${1:-}" = --fdroid-buildserver ] || { echo 'Select --fdroid-buildserver explicitly' >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo 'F-Droid sudo stage required' >&2; exit 2; }
printf '%s\n' 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20260904T000000Z/ unstable main' > /etc/apt/sources.list.d/overte-fdroid.list
printf '%s\n' 'Package: *' 'Pin: release a=unstable' 'Pin-Priority: 90' > /etc/apt/preferences.d/overte-fdroid
apt-get update
apt-get install -y --no-install-recommends ca-certificates cmake=3.31.6-2 git make patch perl python3-pip python3-venv tar xz-utils util-linux iproute2
apt-get install -y --no-install-recommends -t unstable gcc-15=15.3.0-3 g++-15=15.3.0-3 ninja-build=1.13.2-1 openjdk-17-jdk-headless=17.0.20.1+1-1
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-15 150
update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-15 150
python3 -m venv /opt/overte-fdroid/conan
/opt/overte-fdroid/conan/bin/pip install --no-cache-dir 'conan==2.25.2'
