#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"

# Deliberately performs no Conan/Gradle build. It only validates the existing
# outputs and atomically publishes the content-bound readiness sentinel.
"$android_root/phone/tests/verify-phone-16k-dependencies.sh" --write-sentinel \
    "$android_root/common/conan/phone-16k-debug" \
    "$android_root/common/conan/phone-nonqt-16k-debug" \
    "$android_root/common/conan/phone-nonqt-16k-debug/.phone-16k-dependencies.ready"
