#!/usr/bin/env python3
"""Phone-owned offline consumer of SH-004 v001. Never runs or certifies a device."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests/device/schema"))
from result_binding import validate as validate_shared
from terminal_evidence import EvidenceError, read_document, require

# Reviewed scope, never the observed successful subset. These are original
# Shared catalog IDs; no new adapter, capability or cross-platform schema.
SUITES = {
    "smoke": ("launch-smoke",),
    "permission-recovery": ("launch-smoke", "permission-recovery"),
    "tablet-e2e": ("launch-smoke", "tablet-e2e"),
    "text-input-smoke": ("launch-smoke", "text-input"),
    "domain-smoke": ("launch-smoke", "domain-enter"),
    "interaction-smoke": ("launch-smoke", "scene", "world-interaction"),
    "audio-controls": ("launch-smoke", "audio-controls"),
    "sound-smoke": ("launch-smoke", "sound-playback"),
    "network-fault-recovery": ("launch-smoke", "domain-enter", "network-fault-recovery"),
    "lifecycle-under-load": ("launch-smoke", "scene", "lifecycle-under-load"),
    "stability": ("launch-smoke", "idle-soak"),
}
PLANS = {
    "emulator": ("smoke", "permission-recovery", "tablet-e2e", "text-input-smoke"),
    "core": ("smoke", "domain-smoke", "interaction-smoke", "tablet-e2e",
             "text-input-smoke", "audio-controls", "sound-smoke",
             "network-fault-recovery", "lifecycle-under-load", "permission-recovery", "stability"),
}
ADAPTERS = ("android-phone-adb", "appium-android")


def verify_phone_results(result_root: Path, source_sha: str, artifact_sha: str,
                         adapter: str, milestone: str) -> list[dict]:
    require(milestone in PLANS and adapter in ADAPTERS, "PHONE_SCOPE")
    result_root = Path(result_root)
    require(result_root.is_dir() and not result_root.is_symlink(), "PHONE_RESULT_ROOT")
    catalog, _ = read_document(ROOT / "tests/device/catalog.json")
    results = []
    for suite in PLANS[milestone]:
        required = SUITES[suite]
        declared = {entry["id"] for entry in catalog["modules"] if suite in entry["suites"]}
        require(declared == set(required), "PHONE_CATALOG_DRIFT")
        directory = result_root / suite
        require(directory.is_dir() and not directory.is_symlink(), "PHONE_SUITE_DIRECTORY")
        bound = validate_shared(directory, source_sha, artifact_sha, adapter,
                                "android", list(required), milestone == "core")
        run, _ = read_document(directory / "run-manifest.json")
        require(run["suite"] == suite, "PHONE_SUITE_MISMATCH")
        if suite == "stability":
            require(run["durationSeconds"] >= 1800, "PHONE_CORE_DURATION")
        results.append(bound)
    return results


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default errors can echo private argument values or paths.
        self.exit(2, "PHONE_RESULT_ARGUMENTS_REJECTED\n")


def main(argv=None):
    parser = PrivateParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--result-root", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-artifact-sha256", required=True)
    parser.add_argument("--expected-adapter", required=True, choices=ADAPTERS)
    parser.add_argument("--milestone", required=True, choices=tuple(PLANS))
    args = parser.parse_args(argv)
    try:
        verify_phone_results(args.result_root, args.expected_source_sha,
                             args.expected_artifact_sha256, args.expected_adapter, args.milestone)
    except (EvidenceError, OSError, TypeError, KeyError, ValueError, RecursionError):
        print("PHONE_RESULTS_REJECTED", file=sys.stderr)
        return 1
    print("PHONE_RESULTS_BOUND_NOT_ACCEPTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
