#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Deliberately performs no Conan/Gradle build. It only validates the existing
# outputs and atomically publishes the content-bound readiness sentinel.
"$script_dir/tests/verify-phone-16k-dependencies.sh" --write-sentinel \
    "$script_dir/conan/phone-16k-debug" \
    "$script_dir/conan/phone-nonqt-16k-debug" \
    "$script_dir/conan/phone-nonqt-16k-debug/.phone-16k-dependencies.ready"
