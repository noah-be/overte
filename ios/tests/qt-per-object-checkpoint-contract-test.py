#!/usr/bin/env python3
"""Protect bounded disk-only persistence of cacheable Qt compilations."""

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
    'SCCACHE_MULTILEVEL_CHAIN: disk',
    'SCCACHE_MULTILEVEL_WRITE_ERROR_POLICY: l0',
):
    if setting not in WORKFLOW:
        raise SystemExit(f"missing fail-closed disk-only checkpoint setting: {setting}")
for forbidden in (
    "SCCACHE_GHA_",
    "ACTIONS_RESULTS_URL",
    "ACTIONS_CACHE_URL",
    "ACTIONS_RUNTIME_TOKEN",
):
    if forbidden in WORKFLOW:
        raise SystemExit(f"disk-only Qt checkpoint retains forbidden GHA state: {forbidden}")

key_start = WORKFLOW.index("Select deterministic cache key")
key_end = WORKFLOW.index("Restore validated Qt host tools")
key_slice = WORKFLOW[key_start:key_end]
if "SCCACHE_GHA_VERSION" in key_slice or "remote_namespace=" in key_slice:
    raise SystemExit("deterministic cache keys must not enable a remote sccache backend")

probe_start = WORKFLOW.index("Verify local compiler cache before the long build")
probe_end = WORKFLOW.index("Restore validated Qt host tools")
probe_slice = WORKFLOW[probe_start:probe_end]
if not key_start < probe_start < probe_end:
    raise SystemExit("local cache probe must run after key selection and before long work")
for invariant in (
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "sccache /usr/bin/clang",
    "requests_executed",
    "cache_writes",
    "cache_write_errors",
    "sccache --stop-server",
):
    if invariant not in probe_slice:
        raise SystemExit(f"local checkpoint preflight omits {invariant}")
for forbidden in ("multi_level", "write_failures", "remote"):
    if forbidden in probe_slice.lower():
        raise SystemExit(f"local checkpoint preflight retains remote expectation: {forbidden}")

install = WORKFLOW[WORKFLOW.index("Install source-build prerequisites"):
                   WORKFLOW.index("Verify or download pinned Qt source archive")]
if "brew install cmake ninja sccache" in install:
    raise SystemExit("unpinned Homebrew sccache bypasses the pinned checkpoint action")

report = WORKFLOW.index("Report compiler-cache statistics")
verify = WORKFLOW.index("Verify successful Qt build used the local compiler cache")
diagnostics = WORKFLOW.index("Upload compiler stall diagnostics")
stop = WORKFLOW.index("Stop compiler-cache server before recovery snapshot")
save = WORKFLOW.index("Save compiler recovery cache after a build failure")
if not report < verify < diagnostics < stop < save:
    raise SystemExit("checkpoint verification/diagnostics/local recovery ordering drifted")
verify_slice = WORKFLOW[verify:diagnostics]
for invariant in (
    "report-sccache-stats.py",
    "--require-activity",
):
    if invariant not in verify_slice:
        raise SystemExit(f"local checkpoint verification omits {invariant}")
if "--max-remote" in verify_slice:
    raise SystemExit("local checkpoint verification retains a remote threshold")

print("Qt per-object checkpoint contract valid: disk-only activity plus local failure recovery")
