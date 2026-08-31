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
require(r"Export remote compiler checkpoint credentials[\s\S]*?"
        r"actions/github-script@[0-9a-f]{40}\s+# v9\.0\.0[\s\S]*?"
        r"process\.env\.ACTIONS_RESULTS_URL[\s\S]*?"
        r"process\.env\.ACTIONS_RUNTIME_TOKEN[\s\S]*?"
        r"core\.setSecret\(runtimeToken\)[\s\S]*?"
        r'core\.exportVariable\("SCCACHE_GHA_CACHE_URL", cacheUrl\)[\s\S]*?'
        r'core\.exportVariable\("SCCACHE_GHA_RUNTIME_TOKEN", runtimeToken\)',
        "Qt per-object checkpoint must securely export ephemeral GHA cache credentials")
for setting in (
    'SCCACHE_BASEDIRS: ${{ github.workspace }}',
    'SCCACHE_CLIENT_SIDE: "1"',
    'SCCACHE_MULTILEVEL_CHAIN: disk,gha',
    'SCCACHE_MULTILEVEL_WRITE_ERROR_POLICY: all',
    'SCCACHE_GHA_ENABLED: "true"',
):
    if setting not in WORKFLOW:
        raise SystemExit(f"missing fail-closed per-object checkpoint setting: {setting}")

key_start = WORKFLOW.index("Select deterministic cache key")
key_end = WORKFLOW.index("Restore validated Qt host tools")
key_slice = WORKFLOW[key_start:key_end]
if 'echo "SCCACHE_GHA_VERSION=$remote_namespace" >> "$GITHUB_ENV"' not in key_slice:
    raise SystemExit("SCCACHE_GHA_VERSION is not exported from the deterministic namespace")
if 'remote_namespace="overte-qt-objects-v1-${ios_base}"' not in key_slice:
    raise SystemExit("remote per-object namespace is not tied to the exact iOS toolchain plan")
namespace_line = next(line for line in key_slice.splitlines() if "remote_namespace=" in line)
if "GITHUB_RUN_ID" in namespace_line or "GITHUB_RUN_ATTEMPT" in namespace_line:
    raise SystemExit("remote per-object namespace must survive runs of the same toolchain plan")

probe_start = WORKFLOW.index("Verify remote compiler checkpoint before the long build")
probe_end = WORKFLOW.index("Restore validated Qt host tools")
probe_slice = WORKFLOW[probe_start:probe_end]
if not key_start < probe_start < probe_end:
    raise SystemExit("remote checkpoint probe must run after namespace selection and before long work")
for invariant in (
    "SCCACHE_GHA_CACHE_URL",
    "SCCACHE_GHA_RUNTIME_TOKEN",
    "SCCACHE_GHA_ENABLED",
    "SCCACHE_GHA_VERSION",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "sccache /usr/bin/clang",
    "requests_executed",
    "cache_writes",
    "cache_write_errors",
    "multi_level",
    "write_failures",
    "sccache --stop-server",
):
    if invariant not in probe_slice:
        raise SystemExit(f"remote checkpoint preflight omits {invariant}")

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
for invariant in (
    "report-sccache-stats.py",
    "--require-activity",
    "--max-remote-write-failure-rate 0.01",
    "--max-remote-write-failures 32",
):
    if invariant not in verify_slice:
        raise SystemExit(f"remote checkpoint verification omits {invariant}")

print("Qt per-object checkpoint contract valid: immediate remote plus local failure recovery")
