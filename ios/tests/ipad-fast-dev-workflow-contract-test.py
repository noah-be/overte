#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAST = (ROOT / ".github/workflows/ios-ipad-fast-dev.yml").read_text(encoding="utf-8")
INTEGRATED = (ROOT / ".github/workflows/ios-integrated.yml").read_text(encoding="utf-8")
QT_SOURCE = (ROOT / ".github/workflows/ios-qt-source.yml").read_text(encoding="utf-8")

assert "workflow_dispatch:" in FAST
assert "'fix/ios/ipad-fast-dev-*'" in FAST and "pull_request:" not in FAST
assert "contains(github.event.head_commit.message, '[ipad-fast]')" in FAST
assert "ios-qt-source.yml" in FAST and "ios-integrated.yml" in FAST
assert FAST.count("fast_dev: true") == 2
assert "bundle_id: org.overte.interface.sideload.b456" in FAST
assert "iphonesimulator" not in FAST
assert "inputs.fast_dev" in INTEGRATED and "inputs.fast_dev" in QT_SOURCE
assert "ios/build-ios.sh package-client --platform device --configuration Release" in INTEGRATED
assert "ios/tools/normalize-sideload-ipa.py" in INTEGRATED
assert '"$output_root/current.ipa"' in INTEGRATED
assert "overte-ipad-fast-dev-${{ github.run_id }}" in INTEGRATED

print("manual iPad fast-dev workflow builds one stable-ID current.ipa without simulator jobs")
