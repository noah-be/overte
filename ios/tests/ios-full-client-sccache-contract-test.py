#!/usr/bin/env python3
"""Protect the disk-only, failure-resilient Xcode compiler checkpoint."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ios-integrated.yml"
BUILD_SCRIPT = ROOT / "ios/build-ios.sh"


def require(pattern: str, text: str, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(message)


def main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    integrated = workflow[workflow.index("  integrated-configure:") :]
    build_script = BUILD_SCRIPT.read_text(encoding="utf-8")

    install = integrated.index("Install pinned full-client compiler checkpoint")
    namespace = integrated.index("Select full-client compiler cache namespace")
    restore = integrated.index("Restore compatible full-client compiler checkpoint")
    start = integrated.index("Start full-client compiler checkpoint")
    configure = integrated.index("Configure experimental full client graph")
    smoke = integrated.index("Verify Xcode compiler checkpoint before full build")
    build = integrated.index("Build experimental full client")
    verify = integrated.index("Verify full-client compiler checkpoint activity")
    stop = integrated.index("Stop full-client compiler checkpoint server")
    free = integrated.index("Free space for the next compiler checkpoint")
    save = integrated.index("Save reusable full-client compiler checkpoint")
    prune = integrated.index("Prune superseded full-client compiler checkpoints")
    package = integrated.index("Package numbered unsigned client IPA")
    assert install < namespace < restore < start < configure < smoke < build < verify < stop < free < save < prune < package

    require(
        r"mozilla-actions/sccache-action@[0-9a-f]{40}\s+# v0\.0\.11[\s\S]*?version: v0\.17\.0[\s\S]*?disable_annotations: true",
        integrated,
        "the full-client cache must use pinned action and compiler-cache revisions",
    )
    for forbidden in (
        "SCCACHE_GHA_",
        "ACTIONS_RESULTS_URL",
        "ACTIONS_CACHE_URL",
        "ACTIONS_RUNTIME_TOKEN",
    ):
        if forbidden in integrated:
            raise AssertionError(f"disk-only compiler caching retains forbidden GHA state: {forbidden}")
    require(r"SCCACHE_DIR:\s*\$\{\{ github\.workspace \}\}/build-ios/client-sccache", integrated, "the cache must stay in the bounded workspace path")
    require(r"SCCACHE_CACHE_SIZE:\s*512M", integrated, "the client cache must leave room for validated toolchain checkpoints")
    require(r'SCCACHE_IDLE_TIMEOUT:\s*"0"', integrated, "the cache server must survive long non-compiler Xcode phases")
    for disk_setting in (
        'SCCACHE_CLIENT_SIDE: "1"',
        "SCCACHE_MULTILEVEL_CHAIN: disk",
        "SCCACHE_MULTILEVEL_WRITE_ERROR_POLICY: l0",
    ):
        if disk_setting not in integrated:
            raise AssertionError(f"disk-only object persistence omits {disk_setting}")
    require(r"SCCACHE_BASEDIRS:\s*\$\{\{ github\.workspace \}\}", integrated, "workspace paths must be normalized")
    require(r"SCCACHE_C_CUSTOM_CACHE_BUSTER=.*namespace", integrated, "toolchain identity must enter compiler keys")
    for identity in ("QT_HOST_KEY", "QT_IOS_KEY", "CONAN_KEY", "V8_KEY", "MOLTENVK_KEY"):
        if identity not in integrated[namespace:restore]:
            raise AssertionError(f"compiler namespace omits {identity}")
    if "SCCACHE_GHA_VERSION" in integrated[namespace:restore]:
        raise AssertionError("the deterministic toolchain namespace must not enable a GHA backend")

    restore_slice = integrated[restore:start]
    require(r"actions/cache/restore@[0-9a-f]{40}", restore_slice, "compiler restore action must be immutable")
    require(r"path: \$\{\{ github\.workspace \}\}/build-ios/client-sccache", restore_slice, "restore path must match the save path exactly")
    require(r"restore-keys:[\s\S]*client-sccache-key\.outputs\.prefix", restore_slice, "retries must restore the newest compatible generation")

    start_slice = integrated[start:configure]
    require(r"sccache --stop-server \|\| true", start_slice, "persistent runners need a fresh cache server")
    require(r"sccache --start-server", start_slice, "Xcode must not implicitly start and wait on the cache server")
    require(r"sccache --zero-stats", start_slice, "each build needs isolated cache statistics")

    configure_slice = integrated[configure:smoke]
    require(r'compiler_launcher="\$GITHUB_WORKSPACE/ios/ci/xcode-compiler-launcher\.sh"', configure_slice, "configure must select the watchdog launcher")
    require(r'OVERTE_IOS_COMPILER_LAUNCHER="\$compiler_launcher"', configure_slice, "configure must receive the watchdog launcher")
    require(r"C_COMPILER_LAUNCHER.*project\.pbxproj", configure_slice, "the generated Xcode project must prove launcher wiring")
    require(r"xcodebuild -project.*-showBuildSettings[\s\S]*C_COMPILER_LAUNCHER = \$compiler_launcher", configure_slice, "effective target settings must retain the launcher")
    for setting in (
        "CLANG_ENABLE_MODULES = NO",
        "COMPILER_INDEX_STORE_ENABLE = NO",
        "CLANG_USE_RESPONSE_FILE = NO",
    ):
        if setting not in configure_slice:
            raise AssertionError(f"effective Xcode settings omit {setting}")

    smoke_slice = integrated[smoke:build]
    require(r"ios/tests/fixtures/xcode-sccache", smoke_slice, "a real Xcode compile must prove launcher activity before the full build")
    require(r"OVERTE_SCCACHE_LOCAL_PROBE=\$\{GITHUB_RUN_ID\}_\$\{GITHUB_RUN_ATTEMPT\}", smoke_slice, "every run must force a unique local cache write")
    require(r"sccache --zero-stats[\s\S]*cmake --build[\s\S]*sccache --show-stats --stats-format=json", smoke_slice, "the smoke compile needs isolated machine-readable statistics")
    if smoke_slice.count("sccache --zero-stats") != 2:
        raise AssertionError("the full build must start with clean statistics after the Xcode smoke")
    require(r"requests < 1 or cacheable < 1[\s\S]*Xcode compiler checkpoint smoke did not reach sccache", smoke_slice, "a bypassed launcher must fail before the long build")
    for local_evidence in ("cache_writes", "cache_write_errors"):
        if local_evidence not in smoke_slice:
            raise AssertionError(f"the preflight does not prove local object persistence: {local_evidence}")
    for forbidden in ("multi_level", "write_failures", "remote GHA cache"):
        if forbidden in smoke_slice:
            raise AssertionError(f"the local preflight retains a remote-cache expectation: {forbidden}")
    require(r"id: full-client-build", integrated[build:verify], "checkpoint verification needs the named build outcome")

    build_slice = integrated[build:verify]
    require(r"python3 ios/ci/runner-telemetry\.py[\s\S]*--phase client-build", build_slice, "the long Xcode build needs supervised runner telemetry")
    require(r"--output-log build-ios/ci-raw-diagnostics/xcode-build\.log", build_slice, "the complete compiler output must survive a failed build")
    require(r"--compiler-live-log", build_slice, "every compiler invocation must have a live watchdog channel")

    launcher = (ROOT / "ios/ci/xcode-compiler-launcher.sh").read_text(encoding="utf-8")
    require(r"compiler-watchdog\.py[\s\S]*-- \"\$@\"", launcher,
            "every Xcode source compile must enter the watchdog with the real compiler")
    if re.search(r'compiler-watchdog\.py[\s\S]*-- \"\$SCCACHE_PATH\"', launcher):
        raise AssertionError("the launcher must not recursively pass sccache as the compiler")
    require(r'configured_cache = os\.environ\.get\("SCCACHE_PATH"\)[\s\S]*executable\.insert\(0, cache\)',
            (ROOT / "ios/ci/compiler-watchdog.py").read_text(encoding="utf-8"),
            "the watchdog must insert the pinned compiler cache exactly once")

    verify_slice = integrated[verify:package]
    require(r"if:.*!cancelled\(\).*full-client-build\.outcome != 'skipped'", verify_slice, "stats must run after success or failure, but not cancellation")
    require(r"--show-stats --stats-format=json", verify_slice, "machine-readable cache evidence is required")
    for invariant in ("requests_executed", "compile_requests", "cache_hits", "cache_misses", "cache_write_errors"):
        if invariant not in verify_slice:
            raise AssertionError(f"compiler checkpoint does not validate {invariant}")
    require(r"if write_errors:[\s\S]*::warning::sccache reported[\s\S]*local checkpoint will still be archived", verify_slice,
            "a partial cache write failure must remain visible without discarding valid local objects")
    if "raise SystemExit(f\"sccache reported {write_errors} cache write errors\")" in verify_slice:
        raise AssertionError("a partial remote write failure must not suppress the local recovery checkpoint")
    if integrated.count('stats.get("requests_executed", stats.get("compile_requests", 0))') != 2:
        raise AssertionError("both smoke and final verification must understand the sccache 0.17 statistics schema")
    require(r'cache_root = pathlib\.Path\("build-ios/client-sccache"\)[\s\S]*cache_bytes[\s\S]*requests < 1:[\s\S]*cache_files', verify_slice, "expired live statistics must fall back to validating the durable on-disk cache")

    stop_slice = integrated[stop:free]
    require(r"if:.*!cancelled\(\).*full-client-build\.outcome != 'skipped'", stop_slice, "the server must stop after success or failure")
    require(r"sccache --stop-server \|\| true", stop_slice, "an already idle server must not block the durable snapshot")

    free_slice = integrated[free:save]
    require(r"sort_by\(\.createdAt\).*reverse.*\.\[1:\]", free_slice, "one fallback generation must remain while space is freed")
    require(r"select\(\.ref == env\.GITHUB_REF\)", free_slice, "pre-save cleanup must remain branch-local")

    save_slice = integrated[save:prune]
    require(r"actions/cache/save@[0-9a-f]{40}", save_slice, "compiler save action must be immutable")
    require(r"!cancelled\(\).*full-client-build\.outcome != 'skipped'", save_slice, "successful and failed builds must save, while cancellation must not")
    require(r"client-sccache-verify\.outcome == 'success'", save_slice, "empty or corrupt compiler checkpoints must never be archived")
    require(r"continue-on-error: true", save_slice, "cache upload must not mask the compiler result")
    require(r"path: \$\{\{ github\.workspace \}\}/build-ios/client-sccache", save_slice, "save path must equal restore path")

    prune_slice = integrated[prune:package]
    require(r"client-sccache-key\.outputs\.prune_prefix", prune_slice, "pruning must cover obsolete compiler namespaces")
    require(r"sort_by\(\.createdAt\).*reverse.*\.\[1:\]", prune_slice, "only the newest branch/architecture generation may remain")
    require(r"select\(\.ref == env\.GITHUB_REF\)", prune_slice, "pruning must not touch another branch")
    integrated_job_header = integrated[: integrated.index("steps:")]
    require(r"permissions:[\s\S]*actions: write[\s\S]*contents: read", integrated_job_header, "only the pruning job needs Actions write scope")
    if "actions: write" in workflow[: workflow.index("jobs:")]:
        raise AssertionError("Actions write scope must not apply to unrelated jobs")

    bootstrap = (ROOT / ".github/workflows/ios-bootstrap.yml").read_text(encoding="utf-8")
    caller = bootstrap[bootstrap.index("  integrated-ios-after-qt:") : bootstrap.index("  host-contracts:")]
    require(r"permissions:[\s\S]*actions: write[\s\S]*contents: read", caller, "the reusable caller must pass the pruning scope")
    if "actions: write" in bootstrap[: bootstrap.index("jobs:")]:
        raise AssertionError("PR and simulator jobs must retain read-only workflow permissions")

    if re.search(r"actions/cache/(?:restore|save)@[0-9a-f]{40}[\s\S]{0,300}build-ios/device", integrated):
        raise AssertionError("the stale CMake/Xcode device tree must never be cached")
    if "build-ios/device/CMakeCache.txt" in workflow:
        raise AssertionError("CMakeCache.txt must not enter cache or artifact policy")

    for setting in (
        "CMAKE_XCODE_ATTRIBUTE_C_COMPILER_LAUNCHER",
        "CMAKE_XCODE_ATTRIBUTE_CLANG_ENABLE_MODULES=NO",
        "CMAKE_XCODE_ATTRIBUTE_COMPILER_INDEX_STORE_ENABLE=NO",
        "CMAKE_XCODE_ATTRIBUTE_CLANG_USE_RESPONSE_FILE=NO",
    ):
        if setting not in build_script:
            raise AssertionError(f"Xcode compiler checkpoint omits {setting}")
    require(r"command -v \"\$compiler_launcher\"", build_script, "the launcher must resolve to an executable")

    print("Full-client disk-only sccache checkpoint contract passed")


if __name__ == "__main__":
    main()
