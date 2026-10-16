#!/usr/bin/env python3
"""Dormant Android APK repository-input planning, never build or reuse evidence.

Run this reviewed helper from a trusted checkout. Candidate files are immutable
Git data. Nothing here executes Gradle, CMake, Conan, npm, a candidate script or
a workflow. Both complete trees must match a reviewed reader boundary before
an exact independent host/document/npm path may avoid a source rebuild.

External dependency bytes, generated inputs, toolchains, flags, signing,
package metadata and actual APK contents remain unobserved. In particular, an
old APK must never be attributed to the candidate SHA using this comparison.
Only the reviewed device Debug variants below are described; emulator, release,
F-Droid and arbitrary Gradle/property configurations require separate review.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys


ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "tools/ios-build-qualification/inputs.py"
# Reuse only the exact-commit, replacement-disabled complete Git reader. Its
# iOS classification, anchors and build decisions do not apply to Android.
_SPEC = importlib.util.spec_from_file_location("trusted_android_apk_inventory", INVENTORY_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("trusted immutable Git inventory is unavailable")
inventory = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = inventory
_SPEC.loader.exec_module(inventory)
InputError = inventory.InputError


VARIANTS = {
    "phone": {
        "reviewed_revision": "277bad9119c9ee16f4bbb3038cedeb6625741d34",
        "reviewed_boundary": "sha256:19d40cdb79406d0441f74c32368163af59a4007d188bc916489ceb1a14412fd0",
        "contract": "phone-device-debug-arm64-16k-v1",
        "application_id": "io.github.noah_be.overte.phone",
        "abi": "arm64-v8a", "configuration": "Debug", "compile_sdk": 36,
        "min_sdk": 26, "target_sdk": 36, "ndk_version": "27.3.13750724",
        "dependency_contract": "verified-phone-16k-sentinel-and-contents",
        "workflow": ".github/workflows/android-phone-build.yml",
        "entrypoint": "android/phone/build.sh",
        "gradle_task": ":phoneInterface:assembleDebug",
    },
    "pico": {
        "reviewed_revision": "410847ff312553de81f9f8ff7e32029b22495603",
        "reviewed_boundary": "sha256:ba33330b0ec27872f823305c6b98c135b3dc4e59963429f195e62a6ded8d94e9",
        "contract": "pico-device-debug-arm64-source-graph-v1",
        "application_id": "org.overte.pico",
        "abi": "arm64-v8a", "configuration": "Debug", "compile_sdk": 36,
        "min_sdk": 26, "target_sdk": 35, "ndk_version": "27.3.13750724",
        "dependency_contract": "explicit-bound-pico-source-graph-and-runtime-bytes",
        "workflow": ".github/workflows/pico4-build.yml",
        "entrypoint": "android/vr/pico/build.sh",
        "gradle_task": ":picoInterface:assembleDebug",
    },
}

# Exact reviewed host-control files are independent of APK configure/build/
# package readers, even when an existing workflow separately runs their tests.
# Do not turn this into tests/**, tools/**, .github/** or all *.json exemptions.
INDEPENDENT_HOST_PATHS = {
    ".github/test-suite-dependencies.json": "100644",
    "tools/test-evidence/affected-test.py": "100644",
    ".github/android-checks.json": "100644",
    ".github/codeql/codeql-config.yml": "100644",
    ".github/repository-checks.json": "100644",
    ".github/sync-test-reuse.json": "100644",
    ".github/test-suites.json": "100644",
    ".github/workflows/codeql.yml": "100644",
    ".github/workflows/parent-qualification.yml": "100644",
    ".github/workflows/project-tests.yml": "100644",
    ".github/workflows/repository-checks.yml": "100644",
    ".github/workflows/sync-test-reuse.yml": "100644",
    ".github/workflows/sync-validation.yml": "100644",
    ".github/workflows/workflow-security.yml": "100644",
    "tests/android-build-inputs-test.py": "100644",
    "tests/android-ci-test.py": "100644",
    "tests/codeql-selection-test.py": "100644",
    "tests/repository-checks-test.py": "100644",
    "tests/run-project-tests.py": "100755",
    "tests/workflow-contract-test.py": "100644",
    "tools/ios-build-qualification/inputs.py": "100644",
    "tools/repository-checks/android-build-inputs.py": "100644",
    "tools/repository-checks/android.py": "100644",
    "tools/repository-checks/check.py": "100644",
    "tools/repository-checks/codeql.py": "100644",
    "tools/repository-checks/workflows/browser-direct-client.yml": "100644",
    "tools/repository-checks/workflows/repository-checks.yml": "100644",
    "tools/sync-test-reuse/differential.py": "100644",
    "tools/sync-test-reuse/gate.py": "100644",
    "tools/sync-test-reuse/qualification.py": "100644",
    "tools/sync-test-reuse/test.py": "100644",
    "tools/test-evidence/execution-test.py": "100644",
    "tools/test-evidence/execution.py": "100644",
    "tools/test-evidence/inputs.py": "100644",
    "tools/test-evidence/qualification-producer-test.py": "100644",
    "tools/test-evidence/registry-test.py": "100644",
    "tools/test-evidence/run.py": "100644",
    "tools/test-evidence/runtime-test.py": "100644",
    "tools/test-evidence/runtime.py": "100644",
    "tools/test-evidence/test.py": "100644",
    "tools/test-evidence/validate-sync-test.py": "100644",
    "tools/test-evidence/validate-sync.py": "100644",
}
INDEPENDENT_DOCUMENTS = {"README.md", "CONTRIBUTING.md", "tests/PROJECT_TESTING.md"}
# These standalone npm projects are outside both reviewed Android app graphs.
# Android returns before tools/server-console configuration, so the JSDoc npm
# graph is not constructed either. Packaged scripts/** metadata stays relevant.
INDEPENDENT_NPM_PATHS = frozenset({
    "android/common/tests/javascript/package.json",
    "browser-client/package.json", "browser-client/package-lock.json",
    "browser-direct-client/package.json", "browser-direct-client/package-lock.json",
    "script-archive/marketplace/S3Server/package.json",
    "script-archive/marketplace/S3Server/package-lock.json",
    "server-console/package.json", "server-console/package-lock.json",
    "tests/mocha/package.json", "tests/mocha/package-lock.json",
    "tools/jsdoc/package.json", "tools/jsdoc/package-lock.json",
    "tools/jsdoc/hifi-jsdoc-template/package.json",
})
UNOBSERVED = (
    "sdk-ndk-jdk-gradle-cmake-host-tools-and-effective-flags",
    "conan-packages-qt-runtime-and-source-graph-bytes",
    "native-versus-dependency-versus-packaging-incremental-closure",
    "generated-files-local-overrides-and-workspace-cleanliness",
    "apk-version-source-metadata-signing-and-packaged-content",
    "required-independent-host-security-and-product-checks",
)
_DOMAIN = "overte-android-apk-repository-inputs-v1"


def _digest(value):
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _variant(name):
    if not isinstance(name, str) or name not in VARIANTS:
        raise InputError("unsupported Android APK variant")
    return VARIANTS[name]


def _kind(entry):
    if INDEPENDENT_HOST_PATHS.get(entry.path) == entry.mode and entry.object_type == "blob":
        return "independent-host"
    if entry.mode == "100644" and entry.object_type == "blob":
        if entry.path in INDEPENDENT_NPM_PATHS:
            return "independent-npm"
        if entry.path in INDEPENDENT_DOCUMENTS or (
                entry.path.startswith("docs/") and PurePosixPath(entry.path).suffix == ".md"):
            return "independent-documentation"
    return "application-input"


def _boundary(snapshot, variant):
    return _digest({"domain": _DOMAIN + "-reader-boundary", "variant": variant,
                    "entries": [entry.identity() for entry in snapshot.entries
                                if _kind(entry) == "application-input"]})


def review_boundary(repository, revision, variant):
    """Compute a review proposal, never approve a new reader or source graph."""
    _variant(variant)
    snapshot = inventory.read_snapshot(repository, revision)
    return {"revision": snapshot.revision, "tree": snapshot.tree,
            "boundary": _boundary(snapshot, variant)}


def _policy(variant):
    return _digest({"domain": _DOMAIN, "variant": variant, "contract": _variant(variant),
                    "host_paths": INDEPENDENT_HOST_PATHS,
                    "npm_paths": sorted(INDEPENDENT_NPM_PATHS), "documents": sorted(INDEPENDENT_DOCUMENTS),
                    "document_rule": "ordinary-docs/**/*.md",
                    "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "inventory_implementation": hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest()})


def _identity(snapshot, variant, policy):
    nonregular = [entry.path for entry in snapshot.entries if entry.mode not in {"100644", "100755"}]
    boundary = _boundary(snapshot, variant)
    applicable = boundary == _variant(variant)["reviewed_boundary"] and not nonregular
    selected = [entry.identity() for entry in snapshot.entries
                if not applicable or _kind(entry) == "application-input"]
    return {"revision": snapshot.revision, "tree": snapshot.tree, "boundary": boundary,
            "exclusions_applicable": applicable, "nonregular_paths": nonregular,
            "source_fingerprint": _digest({"domain": _DOMAIN, "policy": policy,
                                           "exclusions_applied": applicable, "entries": selected})}


def input_fingerprint(repository, revision, variant):
    """Identity of repository inputs only, with exact commit/tree provenance."""
    _variant(variant)
    return _identity(inventory.read_snapshot(repository, revision), variant, _policy(variant))


def candidate_plan(repository, base, candidate, variant):
    """Plan from complete exact Git commits; unknown readers request a rebuild.

    Missing/incomplete Git inventory raises InputError. A caller must require
    verification on that error, never interpret a missing plan as a waiver.
    Caller path lists, branch names and candidate policy files are not inputs.
    """
    contract = _variant(variant)
    previous = inventory.read_snapshot(repository, base)
    current = inventory.read_snapshot(repository, candidate)
    policy = _policy(variant)
    before = _identity(previous, variant, policy)
    after = _identity(current, variant, policy)
    old, new = {entry.path: entry for entry in previous.entries}, {entry.path: entry for entry in current.entries}
    changes = []
    for path in sorted(old.keys() | new.keys()):
        if old.get(path) == new.get(path):
            continue
        kinds = {_kind(entry) for entry in (old.get(path), new.get(path)) if entry is not None}
        changes.append({"path": path, "old": old[path].identity() if path in old else None,
                        "new": new[path].identity() if path in new else None,
                        "kind": "application-input" if "application-input" in kinds else kinds.pop()})
    applicable = before["exclusions_applicable"] and after["exclusions_applicable"]
    if not changes:
        reason = "empty-change-inventory-requires-verification"
    elif before["nonregular_paths"] or after["nonregular_paths"]:
        reason = "unproven-symlink-or-gitlink-closure"
    elif any(change["kind"] == "application-input" for change in changes):
        reason = "application-inputs-changed"
    elif not applicable:
        reason = "reader-boundary-not-reviewed"
    else:
        reason = "independent-host-documents-or-npm-only"
    return {"schema": 1, "variant": variant, "contract": dict(contract), "policy": policy,
            "base": before, "candidate": after, "exclusions_applicable": applicable,
            "changes": changes, "reason": reason,
            "requires_source_build": reason != "independent-host-documents-or-npm-only",
            "verification_required": list(UNOBSERVED), "build_evidence": "not-provided",
            "artifact_reuse": "not-authorized", "workflow_dispatch": "not-performed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--variant", choices=tuple(VARIANTS), required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(candidate_plan(args.repository, args.base, args.candidate, args.variant), sort_keys=True))
        return 0
    except (InputError, OSError) as error:
        print("Android APK input planning unavailable; verification required: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
