#!/usr/bin/env python3
"""Protect immediate remote persistence of every cacheable Qt compilation."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/ios-qt-source.yml").read_text(encoding="utf-8")


def require(pattern: str, message: str) -> None:
    if re.search(pattern, WORKFLOW, re.MULTILINE | re.DOTALL) is None:
        raise SystemExit(message)


require(r"mozilla-actions/sccache-action@[0-9a-f]{40}\s+# v0\.0\.11[\s\S]*?version: v0\.17\.0",
        "Qt per-object checkpoint must use pinned sccache action and version")
for setting in (
    'SCCACHE_BASEDIRS: ${{ github.workspace }}',
    'SCCACHE_CLIENT_SIDE: "1"',
    'SCCACHE_MULTILEVEL_CHAIN: disk,gha',
    'SCCACHE_MULTILEVEL_WRITE_ERROR_POLICY: all',
):
    if setting not in WORKFLOW:
        raise SystemExit(f"missing fail-closed per-object checkpoint setting: {setting}")

key_start = WORKFLOW.index("Select deterministic cache key")
key_end = WORKFLOW.index("Restore validated Qt host tools")
key_slice = WORKFLOW[key_start:key_end]
for variable in ("SCCACHE_GHA_CACHE_TO", "SCCACHE_GHA_CACHE_FROM"):
    if f'echo "{variable}=$remote_namespace" >> "$GITHUB_ENV"' not in key_slice:
        raise SystemExit(f"{variable} is not exported from the deterministic namespace")
if 'remote_namespace="overte-qt-objects-v1-${ios_base}"' not in key_slice:
    raise SystemExit("remote per-object namespace is not tied to the exact iOS toolchain plan")
if "GITHUB_RUN_ID" in key_slice[key_slice.index("remote_namespace="):]:
    raise SystemExit("remote per-object namespace must survive runs of the same toolchain plan")

install = WORKFLOW[WORKFLOW.index("Install source-build prerequisites"):
                   WORKFLOW.index("Verify or download pinned Qt source archive")]
if "brew install cmake ninja sccache" in install:
    raise SystemExit("unpinned Homebrew sccache bypasses the pinned checkpoint action")

report = WORKFLOW.index("Report compiler-cache statistics")
verify = WORKFLOW.index("Verify successful Qt build was remotely checkpointed")
diagnostics = WORKFLOW.index("Upload compiler stall diagnostics")
stop = WORKFLOW.index("Stop compiler-cache server before recovery snapshot")
save = WORKFLOW.index("Save compiler recovery cache after a build failure")
if not report < verify < diagnostics < stop < save:
    raise SystemExit("checkpoint verification/diagnostics/local recovery ordering drifted")
verify_slice = WORKFLOW[verify:diagnostics]
for invariant in ("compile_requests", "cache_hits", "cache_misses", "cache_write_errors"):
    if invariant not in verify_slice:
        raise SystemExit(f"remote checkpoint verification omits {invariant}")

print("Qt per-object checkpoint contract valid: immediate remote plus local failure recovery")
