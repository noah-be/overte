#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# For the disposable F-Droid buildserver VM only; never run on a developer host.
set -eu
[ "${1:-}" = --fdroid-buildserver ] || { echo 'Select --fdroid-buildserver explicitly' >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo 'F-Droid sudo stage required' >&2; exit 2; }
apt-get update
apt-get install -y --no-install-recommends ca-certificates gcc g++ cmake ninja-build openjdk-21-jdk-headless git make patch perl python3-pip python3-venv tar xz-utils util-linux iproute2
python3 -m venv /opt/overte-fdroid/conan
/opt/overte-fdroid/conan/bin/pip install --no-cache-dir 'conan==2.25.2'
