#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$script_dir/port-contract-test.py"
python3 "$script_dir/build-cli-test.py"
python3 "$script_dir/bundle-metadata-test.py"
python3 "$script_dir/device-results-validator-test.py"
python3 "$script_dir/conan-graph-audit-test.py"
python3 "$script_dir/ios-header-guard-test.py"
python3 "$script_dir/compatibility-debt-test.py"
python3 "$script_dir/sbom-test.py"
python3 "$script_dir/pending-deep-link-test.py"
python3 "$script_dir/overte-address-test.py"
python3 "$script_dir/lifecycle-state-test.py"
python3 "$script_dir/entity-integration-inventory-test.py"
python3 "$script_dir/entity-integration-cmake-gate-test.py"
python3 "$script_dir/entity-gate-telemetry-test.py"
python3 "$script_dir/../tools/tests/test-prepare-qt-ios.py"
python3 "$script_dir/../tools/tests/test-build-qt-ios-from-source.py"
bash -n "$script_dir/../build-ios.sh"
cmake -P "$script_dir/qt-compat-test.cmake"
cmake -P "$script_dir/find-moltenvk-test.cmake"
