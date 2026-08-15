#!/usr/bin/env python3
"""Protect the no-rebuild CoreSimulator installation diagnostic."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/ios-simulator-install-diagnostic.yml").read_text(encoding="utf-8")
RUN_TESTS = (ROOT / "ios/tests/run-tests.sh").read_text(encoding="utf-8")


assert re.search(r"^\s+workflow_dispatch:\s*$", WORKFLOW, re.MULTILINE)
assert "pull_request:" not in WORKFLOW
assert "push:" not in WORKFLOW
assert re.search(r"world_runtime_only:[\s\S]*type: boolean", WORKFLOW)
assert re.search(r"symbolicate_existing_crash:[\s\S]*type: boolean", WORKFLOW)
assert "inputs.source_run_id || '31818380576'" in WORKFLOW
assert "actions: read" in WORKFLOW and "contents: read" in WORKFLOW
assert "persist-credentials: false" in WORKFLOW
assert "runs-on: macos-15" in WORKFLOW
assert "CoreSimulatorService belongs to the host OS" in WORKFLOW
for line in WORKFLOW.splitlines():
    if line.lstrip().startswith("uses:"):
        assert re.search(r"@[0-9a-f]{40}(?:\s+#.*)?$", line), line

assert "actions/download-artifact@" in WORKFLOW
assert "run-id: ${{ env.SOURCE_RUN_ID }}" in WORKFLOW
assert 'source/artifacts/$SOURCE_CANDIDATE_NAME' in WORKFLOW
assert "downloaded artifact does not contain the requested simulator candidate" in WORKFLOW
assert "shasum -a 256" in WORKFLOW
assert "expected one available runtime" in WORKFLOW
for version, build in (("26.3", "17C529"),):
    assert version in WORKFLOW and build in WORKFLOW
assert "iPhone-16-Pro" in WORKFLOW
assert "simctl install" in WORKFLOW
assert "Foundation" in WORKFLOW and "foundation_bundle_identifier" in WORKFLOW
assert "foundation_raw_identifier" in WORKFLOW
assert 'codesign --force --deep --sign - --identifier "$identifier" --timestamp=none' in WORKFLOW
for case in ("control", "metadata-control", "overte-minimal"):
    assert case in WORKFLOW
assert "xcrun clang" in WORKFLOW and "UIApplicationMain" in WORKFLOW
assert "processed Overte metadata is not a valid install bundle" in WORKFLOW
assert "Overte Mach-O prevents minimal bundle installation" in WORKFLOW
assert "scripts/system/assets/images/tools/snap.svg" in WORKFLOW
assert "unexpected executable resources" in WORKFLOW
assert "mode & 0o111" in WORKFLOW
assert "os.chmod(snap, snap.stat().st_mode & ~0o111)" in WORKFLOW
assert 'mv "$normalized_app/resources" "$normalized_app/overte-resources"' in WORKFLOW
assert "full-original" in WORKFLOW and "full-normalized" in WORKFLOW
assert "original full bundle unexpectedly installed" in WORKFLOW
assert "normalizing the executable resource did not repair installation" in WORKFLOW
assert "PASS full Overte bundle installs after executable resource normalization" in WORKFLOW
assert re.search(
    r"sign_bundle full-normalized.*?"
    r"foundation_bundle_identifier=[$]BUNDLE_ID.*?"
    r"foundation_raw_identifier=[$]BUNDLE_ID",
    WORKFLOW,
    re.DOTALL,
)
assert "cmake --build" not in WORKFLOW and "build-ios.sh build" not in WORKFLOW
assert "retention-days: 14" in WORKFLOW

runtime = WORKFLOW[WORKFLOW.index("world-runtime-only:") :]
assert "if: ${{ inputs.world_runtime_only && !inputs.symbolicate_existing_crash }}" in runtime
assert "runs-on: macos-15" in runtime
assert "runs-on: macos-26" not in runtime
assert "Download exact preserved simulator candidate without rebuilding" in runtime
assert "verify-runtime-candidate.py" in runtime
assert "LATEST-OverteIOSClient.json" in runtime
assert "LATEST-OverteIOSClient.txt" in runtime
assert 'printf \'%s\\n\' "$SOURCE_CANDIDATE_NAME"' in runtime
assert "--mode simulator" in runtime
assert "--expected-source-revision \"$EXPECTED_SOURCE_REVISION\"" in runtime
assert "--expected-sha256 \"$EXPECTED_SHA256\"" in runtime
assert "/Applications/Xcode_16.4.app/Contents/Developer" in runtime
assert '"$xcode_build" == 16F6' in runtime
assert "com.apple.CoreSimulator.SimRuntime.iOS-18-5" in runtime
assert "expected exactly one available iOS 18.5 runtime" in runtime
assert "interface-world-simulator-smoke.sh" in runtime
assert "symbolicate-simulator-crash.py" in runtime
assert "*-crash-report.log" in runtime and "*-symbolicated-crash.json" in runtime
assert "Overte.app.dSYM/Contents/Resources/DWARF/Overte" in runtime
assert '"$crash" "$symbol_binary" "$symbolicated"' in runtime
assert "for family in iphone ipad" in runtime
assert "serverless -" in runtime and 'online "$ONLINE_DOMAIN"' in runtime
assert "validate-world-evidence-set.py" in runtime
assert "sanitize-ci-log.py" in runtime
assert "*-screenshot.json" in runtime and "*-runtime.json" in runtime
assert "world-evidence-set.json" in runtime
assert "Require successful preserved-candidate runtime evidence" in runtime
assert "cmake --build" not in runtime and "build-ios.sh build" not in runtime
assert RUN_TESTS.count("simulator-install-diagnostic-workflow-test.py") == 1

symbolicate = WORKFLOW[WORKFLOW.index("symbolicate-existing-crash:") :]
assert "if: ${{ inputs.symbolicate_existing_crash }}" in symbolicate
assert "runs-on: macos-15" in symbolicate
assert "Validate trusted candidate and crash producers" in symbolicate
assert 'crash_path != ".github/workflows/ios-simulator-install-diagnostic.yml"' in symbolicate
assert "Download exact preserved candidate" in symbolicate
assert "Download exact preserved crash report" in symbolicate
assert "shasum -a 256" in symbolicate
assert "symbolicate-simulator-crash.py" in symbolicate
assert "Overte.app.dSYM/Contents/Resources/DWARF/Overte" in symbolicate
assert "debugSymbols" in symbolicate
assert "ios-symbolicated-crash-${{ github.run_id }}" in symbolicate
assert "cmake --build" not in symbolicate and "build-ios.sh build" not in symbolicate

print("PASS no-rebuild CoreSimulator installation diagnostic workflow contract")
