#!/usr/bin/env python3
"""Protect the failure-resilient full-client Xcode compiler checkpoint."""

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
    build = integrated.index("Build experimental full client")
    verify = integrated.index("Verify full-client compiler checkpoint activity")
    stop = integrated.index("Stop full-client compiler checkpoint server")
    free = integrated.index("Free space for the next compiler checkpoint")
    save = integrated.index("Save reusable full-client compiler checkpoint")
    prune = integrated.index("Prune superseded full-client compiler checkpoints")
    package = integrated.index("Package numbered unsigned client IPA")
    assert install < namespace < restore < start < configure < build < verify < stop < free < save < prune < package

    require(
        r"mozilla-actions/sccache-action@[0-9a-f]{40}\s+# v0\.0\.11[\s\S]*?version: v0\.17\.0[\s\S]*?disable_annotations: true",
        integrated,
        "the full-client cache must use pinned action and compiler-cache revisions",
    )
    require(r"SCCACHE_DIR:\s*\$\{\{ github\.workspace \}\}/build-ios/client-sccache", integrated, "the cache must stay in the bounded workspace path")
    require(r"SCCACHE_CACHE_SIZE:\s*2G", integrated, "the client cache must not evict toolchain checkpoints")
    require(r"SCCACHE_BASEDIRS:\s*\$\{\{ github\.workspace \}\}", integrated, "workspace paths must be normalized")
    require(r"SCCACHE_C_CUSTOM_CACHE_BUSTER=.*namespace", integrated, "toolchain identity must enter compiler keys")
    for identity in ("QT_HOST_KEY", "QT_IOS_KEY", "CONAN_KEY", "V8_KEY", "MOLTENVK_KEY"):
        if identity not in integrated[namespace:restore]:
            raise AssertionError(f"compiler namespace omits {identity}")

    restore_slice = integrated[restore:start]
    require(r"actions/cache/restore@[0-9a-f]{40}", restore_slice, "compiler restore action must be immutable")
    require(r"path: \$\{\{ github\.workspace \}\}/build-ios/client-sccache", restore_slice, "restore path must match the save path exactly")
    require(r"restore-keys:[\s\S]*client-sccache-key\.outputs\.prefix", restore_slice, "retries must restore the newest compatible generation")

    start_slice = integrated[start:configure]
    require(r"sccache --stop-server \|\| true", start_slice, "persistent runners need a fresh authenticated server")
    require(r"sccache --start-server", start_slice, "Xcode must not implicitly start and wait on the cache server")
    require(r"sccache --zero-stats", start_slice, "each build needs isolated cache statistics")

    configure_slice = integrated[configure:build]
    require(r'OVERTE_IOS_COMPILER_LAUNCHER="\$SCCACHE_PATH"', configure_slice, "configure must receive the pinned launcher")
    require(r"C_COMPILER_LAUNCHER.*project\.pbxproj", configure_slice, "the generated Xcode project must prove launcher wiring")
    require(r"xcodebuild -project.*-showBuildSettings[\s\S]*C_COMPILER_LAUNCHER = \$SCCACHE_PATH", configure_slice, "effective target settings must retain the launcher")
    require(r"id: full-client-build", integrated[build:verify], "checkpoint verification needs the named build outcome")

    verify_slice = integrated[verify:package]
    require(r"if:.*!cancelled\(\).*full-client-build\.outcome != 'skipped'", verify_slice, "stats must run after success or failure, but not cancellation")
    require(r"--show-stats --stats-format=json", verify_slice, "machine-readable cache evidence is required")
    for invariant in ("compile_requests", "cache_hits", "cache_misses", "cache_write_errors"):
        if invariant not in verify_slice:
            raise AssertionError(f"compiler checkpoint does not validate {invariant}")

    stop_slice = integrated[stop:free]
    require(r"if:.*!cancelled\(\).*full-client-build\.outcome != 'skipped'", stop_slice, "the server must stop after success or failure")
    require(r"sccache --stop-server", stop_slice, "cache writes must quiesce before snapshot")

    free_slice = integrated[free:save]
    require(r"sort_by\(\.createdAt\).*reverse.*\.\[1:\]", free_slice, "one fallback generation must remain while space is freed")
    require(r"select\(\.ref == env\.GITHUB_REF\)", free_slice, "pre-save cleanup must remain branch-local")

    save_slice = integrated[save:prune]
    require(r"actions/cache/save@[0-9a-f]{40}", save_slice, "compiler save action must be immutable")
    require(r"!cancelled\(\).*full-client-build\.outcome != 'skipped'", save_slice, "successful and failed builds must save, while cancellation must not")
    if "client-sccache-verify.outcome" in save_slice:
        raise AssertionError("partial compiler results must survive a failed statistics audit")
    require(r"continue-on-error: true", save_slice, "cache upload must not mask the compiler result")
    require(r"path: \$\{\{ github\.workspace \}\}/build-ios/client-sccache", save_slice, "save path must equal restore path")

    prune_slice = integrated[prune:package]
    require(r"client-sccache-key\.outputs\.prune_prefix", prune_slice, "pruning must cover obsolete compiler namespaces")
    require(r"sort_by\(\.createdAt\).*reverse.*\.\[2:\]", prune_slice, "only the two newest branch/architecture generations may remain")
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
    ):
        if setting not in build_script:
            raise AssertionError(f"Xcode compiler checkpoint omits {setting}")
    if "CMAKE_XCODE_ATTRIBUTE_CLANG_USE_RESPONSE_FILE" in build_script:
        raise AssertionError("sccache 0.17 must retain Xcode response files for the large graph")
    require(r"command -v \"\$compiler_launcher\"", build_script, "the launcher must resolve to an executable")

    print("Full-client sccache checkpoint contract passed")


if __name__ == "__main__":
    main()
