#!/usr/bin/env python3
"""Protect the no-rebuild CoreSimulator installation diagnostic."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/ios-simulator-install-diagnostic.yml").read_text(encoding="utf-8")
RUN_TESTS = (ROOT / "ios/tests/run-tests.sh").read_text(encoding="utf-8")
SMOKE = (ROOT / "ios/ci/interface-world-simulator-smoke.sh").read_text(encoding="utf-8")
LLDB = (ROOT / "ios/ci/interface-world-simulator-lldb.sh").read_text(encoding="utf-8")


assert re.search(r"^\s+workflow_dispatch:\s*$", WORKFLOW, re.MULTILINE)
assert "pull_request:" not in WORKFLOW
assert "push:" not in WORKFLOW
assert re.search(r"world_runtime_only:[\s\S]*type: boolean", WORKFLOW)
assert re.search(r"lldb_runtime_only:[\s\S]*type: boolean", WORKFLOW)
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
assert "if: ${{ (inputs.world_runtime_only || inputs.lldb_runtime_only) && !inputs.symbolicate_existing_crash }}" in runtime
assert "runs-on: macos-26" in runtime
assert "Download exact preserved simulator candidate without rebuilding" in runtime
assert "verify-runtime-candidate.py" in runtime
assert "LATEST-OverteIOSClient.json" in runtime
assert "LATEST-OverteIOSClient.txt" in runtime
assert 'printf \'%s\\n\' "$SOURCE_CANDIDATE_NAME"' in runtime
assert "--mode simulator" in runtime
assert "--expected-source-revision \"$EXPECTED_SOURCE_REVISION\"" in runtime
assert "--expected-sha256 \"$EXPECTED_SHA256\"" in runtime
assert "/Applications/Xcode_26.5.app/Contents/Developer" in runtime
assert '"$xcode_build" == 17F42' in runtime
assert "com.apple.CoreSimulator.SimRuntime.iOS-26-5" in runtime
assert "expected exactly one available iOS 26.5 runtime" in runtime
assert "interface-world-simulator-smoke.sh" in runtime
assert "processIdentifier == $launch_pid" in SMOKE
assert 'OVERTE_IOS_WORLD_STACK_SAMPLE_SECONDS:-0' in SMOKE
assert 'OVERTE_IOS_WORLD_LAUNCH_TIMEOUT_SECONDS:-180' in SMOKE
assert 'run_bounded "application launch" "$launch_timeout"' in SMOKE
assert "OVERTE_IOS_WORLD_SYMBOL_BUNDLE" in SMOKE
for snapshot_command in (
    "--attach-pid \"$launch_pid\"",
    "thread backtrace all -c 64",
    "OVERTE_IOS_STACK_SNAPSHOT_COMPLETE",
    "process detach",
    'kill -CONT "$launch_pid"',
):
    assert snapshot_command in SMOKE
assert "runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff'" in SMOKE
assert "runtime_log_contains 'OVERTE_IOS_VULKAN_PRESENT[[:space:]]+output_ready=1'" in SMOKE
assert "$(date +%s) >= sample_deadline" in SMOKE
assert 'OVERTE_IOS_WORLD_STACK_SAMPLE_SECONDS: "900"' in runtime
assert 'OVERTE_IOS_WORLD_MVK_TRACE_VULKAN_CALLS: "6"' not in runtime
assert "OVERTE_IOS_WORLD_MVK_SYNCHRONOUS_QUEUE_SUBMITS" not in runtime
assert 'export OVERTE_IOS_WORLD_SYMBOL_BUNDLE="$symbol_bundle"' not in runtime
assert "Capture preserved candidate SIGSEGV with LLDB" in runtime
assert "interface-world-simulator-lldb.sh" in runtime
assert 'if: ${{ inputs.lldb_runtime_only }}' in runtime
assert "OVERTE_IOS_LLDB_ATTACH_AFTER_WORLD_GATE: ${{ inputs.lldb_wait_for_debugger && '0' || '1' }}" in runtime
assert "OVERTE_IOS_LLDB_WAIT_FOR_DEBUGGER: ${{ inputs.lldb_wait_for_debugger && '1' || '0' }}" in runtime
assert "OVERTE_IOS_LLDB_INTERRUPT_AFTER_SECONDS: ${{ inputs.lldb_interrupt_after_seconds }}" in runtime
assert 'OVERTE_IOS_LLDB_ATTACH_DELAY_SECONDS: "0"' in runtime
assert "symbol_bundle=$symbol_bundle" in runtime
assert "the preserved candidate has no matching dSYM" in runtime
assert "Require captured LLDB crash and keep runtime acceptance red" in runtime
assert "captured_sigsegv|captured_interrupt" in runtime
assert "runtime acceptance remains failed" in runtime
assert "symbolicate-simulator-crash.py" in runtime
assert "*-overte-crash-report.log" in runtime and "*-symbolicated-crash.json" in runtime
assert "${stem}-overte-crash-report.log" in SMOKE
assert "${stem}-simmetalhost-crash-report.log" in SMOKE
assert "Overte.app.dSYM/Contents/Resources/DWARF/Overte" in runtime
assert '"$crash" "$symbol_binary" "$symbolicated"' in runtime
assert 'if ! python3 ios/tools/symbolicate-simulator-crash.py' in runtime
assert "preserving sanitized raw crash diagnostics" in runtime
assert 'rm -f "$symbolicated"' in runtime
assert "*-moltenvk-shaders" in runtime
assert "prepare-moltenvk-diagnostics.py" in runtime
assert "MoltenVK diagnostics failed validation and will not be uploaded" in runtime
assert "for family in iphone ipad" in runtime
assert "serverless -" in runtime and 'online "$ONLINE_DOMAIN"' in runtime
assert "validate-world-evidence-set.py" in runtime
assert "sanitize-ci-log.py" in runtime
assert "*-screenshot.json" in runtime and "*-runtime.json" in runtime
assert "world-evidence-set.json" in runtime
assert "Require successful preserved-candidate runtime evidence" in runtime
assert "cmake --build" not in runtime and "build-ios.sh build" not in runtime
assert RUN_TESTS.count("simulator-install-diagnostic-workflow-test.py") == 1
assert RUN_TESTS.count("interface-world-simulator-lldb-test.py") == 1

for required in (
    "xcrun dwarfdump --uuid",
    "OVERTE_IOS_LLDB_ATTACH_DELAY_SECONDS",
    "OVERTE_IOS_LLDB_ATTACH_ATTEMPTS",
    "OVERTE_IOS_LLDB_ATTACH_AFTER_WORLD_GATE",
    "OVERTE_IOS_LLDB_WORLD_GATE_TIMEOUT_SECONDS",
    "OVERTE_IOS_LLDB_WAIT_FOR_DEBUGGER",
    "OVERTE_IOS_LLDB_INTERRUPT_AFTER_SECONDS",
    "OVERTE_IOS_LLDB_STARTUP_TRACE",
    "SIMCTL_CHILD_MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0",
    "SIMCTL_CHILD_MVK_CONFIG_TRACE_VULKAN_CALLS=6",
    "startup-trace.lldb",
    "OVERTE_LLDB_TRACE resume_entry",
    "OVERTE_LLDB_TRACE sandbox_entry",
    "OVERTE_LLDB_TRACE qt_exit",
    "OVERTE_LLDB_TRACE application_destructor",
    "OVERTE_LLDB_STARTUP_TRACE_COMPLETE",
    "--source-on-crash",
    "thread backtrace all -c 256",
    "thread backtrace -c 128",
    "OVERTE_LLDB_CRASH_CAPTURE_COMPLETE",
    "capture_status=\"captured_sigsegv\"",
    "capture_status=\"captured_interrupt\"",
    "capture_status=\"traced_process_exit\"",
):
    assert required in LLDB, required
assert 'OVERTE_IOS_LLDB_ATTACH_DELAY_SECONDS:-1' in LLDB
assert 'OVERTE_IOS_LLDB_ATTACH_AFTER_WORLD_GATE:-0' in LLDB
assert 'OVERTE_IOS_LLDB_INTERRUPT_AFTER_SECONDS:-0' in LLDB
assert 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' in LLDB
assert 'log stream --style compact --level info' in LLDB
assert "frame variable" not in LLDB
assert "target variable" not in LLDB
assert "memory read" not in LLDB
assert "process save-core" not in LLDB
assert "simctl io" not in LLDB
assert "validate-world" not in LLDB

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
