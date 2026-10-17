#!/usr/bin/env python3
"""Dormant, conservative repository-input selection for the full iOS application.

Load this module from a trusted checkout. It never imports or executes candidate
code and reads complete immutable Git trees, including modes and gitlinks.
Independent host checks still need their own required execution; this module
does not select or waive them, qualify a build, or authorize IPA/artifact reuse.

Negative dependencies are valid only for the reviewed reader boundary below.
Every other tracked entry anchors that boundary, including unknown source,
build generators, workflows, tests/device instrumentation and package inputs.
Both trees must match it before any independent file can avoid an app build.
A source/reader change therefore disables later exclusions until trusted policy
is reviewed again, even if that earlier change already passed an app build.

Repository-input equality deliberately excludes Git commit metadata, build
dates and the external toolchain/runtime. Exact commit/tree provenance is
reported separately. An older IPA must never be presented as a fresh artifact
for a new source revision on the strength of this fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


# Protected apple-ios merge of the successful host-only workflow bootstrap.
# Its only tree delta from the previous anchor is the exact reviewed workflow.
REVIEWED_REVISION = "2fc894a0605103843b36653f250f854714a963ee"
REVIEWED_BOUNDARY = "sha256:8527f25d58c8ebf8eebab8a9e43517899b7afce2e511026d2873a69ab82f1794"

# Reviewed host control-plane files, not generic tests/** or tools/** patterns.
# In particular, E2E builds can compile tests/device source and fixtures.
# These exact files are outside the reviewed app configure/build/package graph.
# Keep application iOS workflows, toolchain readers and device contracts anchored.
# The exact generic device control-plane runner below is not an iOS launcher input;
# its device-control-plane-full and project-runner owners remain independently required.
# Independent required CI must still validate these files before any app waiver.
INDEPENDENT_HOST_PATHS = frozenset({
    # App-only negative dependencies. The iOS host launcher directly executes
    # the chat/Snapshot fixtures; admitting app omission never omits that host.
    '.github/workflows/issue-intake.yml',
    'tests/device/contracts/chat/test_chat_qml.py',
    'tests/device/contracts/snapshot/test_snapshot_native.py',
    'tests/device/contracts/snapshot/test_snapshot_qml.py',
    'tests/device/self_tests/test_android_adapter.py',
    'tests/device/self_tests/test_pico_property_eligibility.py',
    'tests/issue-intake-test.py',
    'tools/issue-intake/install.py',
    "tools/repository-health/check.py",
    '.github/workflows/documentation-checks.yml',
    '.github/workflows/documentation-push-owner.yml',
    'tools/test-evidence/source_admission.py',
    'tools/test-evidence/source-admission-test.py',
    'tools/repository-checks/workflows/producers/legacy/parent-qualification-metadata-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/protected-project-tests-metadata-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/repository-checks-metadata-v1.yml',
    ".github/dependency-security.md",
    ".github/test-suite-dependencies.json",
    "tools/test-evidence/affected-test.py",
    "tools/test-evidence/AFFECTED_SELECTION.md",
    'tools/repository-checks/workflows/producers/legacy/repository-checks-protected-ci-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/parent-qualification-postmerge-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/protected-project-tests-ci37-v1.yml',
    'tools/repository-checks/metadata_context.py',
    'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
    'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
    '.github/workflows/pr-metadata-context.yml',
    ".github/shared-sandbox.json",
    ".github/workflows/shared-sandbox-host-diagnostic.yml",
    "tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml",
    "tools/test-evidence/sandbox.py",
    "tools/test-evidence/sandbox-test.py",
    "tools/test-evidence/sandbox_host.py",
    "tools/test-evidence/sandbox-host-test.py",
    "tools/test-evidence/sandbox_host_fixture.py",
    "tools/test-evidence/sandbox_probe.py",
    "tools/test-evidence/sandbox_shared.py",
    "tools/test-evidence/producer_workflow.py",
    "tools/test-evidence/postmerge.py",
    "tests/run-unittest-suite.py",
    "tests/unittest-runner-test.py",
    ".github/ci37-runtime.json",
    "tools/test-evidence/ci_profile.py",
    "tools/test-evidence/runtime_ci.py",
    "tools/test-evidence/ci-profile-test.py",
    "tools/test-evidence/runtime-ci-test.py",
    "tools/test-evidence/ci-integration-test.py",
    "tools/repository-checks/workflows/producers/legacy/protected-project-tests-v1.yml",
    "tools/repository-checks/workflows/producers/legacy/protected-project-tests-postmerge-v1.yml",
    "tools/repository-checks/workflows/producers/protected-project-tests.yml",
    "tools/repository-checks/workflows/producers/repository-checks.yml",
    "tools/repository-checks/workflows/producers/parent-qualification.yml",
    "tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml",
    "tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml",
    ".github/workflows/android-required.yml",
    ".github/android-owner-transfer.json",
    "tests/android-owner-transfer-test.py",
    "tools/repository-checks/android_handoff.py",
    "tools/repository-checks/workflows/android-owned/android-required.yml",
    "tools/repository-checks/workflows/android-owned/handoff/.github/workflows/android-tests.yml",
    "tools/repository-checks/workflows/android-owned/handoff/.github/workflows/android-vr-tests.yml",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/android-workflow-contract-test.py",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/ci/test_ci_contract.py",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/ci/validate_ci_contract.py",
    "tools/repository-checks/workflows/android-owned/project-tests.yml",
    "tools/repository-checks/workflows/android-owned/repository-checks.yml",
    "tools/repository-checks/workflows/android-owned/handoff/android/phone/tests/phone-release-metadata-test.py",
    "tools/repository-checks/workflows/metadata-edits/codeql.yml",
    "tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml",
    "tools/repository-checks/workflows/metadata-edits/repository-checks.yml",
    "tools/repository-checks/workflows/metadata-edits/sync-test-reuse.yml",
    "tools/repository-checks/workflows/sync-ci-selection.yml",
    "tools/repository-checks/npm_consumers.py",
    "tools/repository-checks/npm-source-map-tests.cjs",
    "tools/repository-checks/npm-proxy-addr-tests.cjs",
    "tools/repository-checks/workflows/npm-consumers/browser-client.yml",
    "tools/repository-checks/workflows/npm-consumers/repository-checks.yml",
    "tools/repository-checks/codeql_results.py",
    "tools/repository-checks/workflows/codeql-results.yml",
    "tools/repository-checks/workflows/codeql-main.json",
    ".github/android-orchestration.json",
    ".github/attested-runtime.json",
    ".github/ios-host-orchestration.json",
    ".github/package-workflow-generations.json",
    ".github/workflows/browser-client-atomic-settings.yml",
    ".github/workflows/browser-client.yml",
    ".github/workflows/browser-direct-client.yml",
    ".github/workflows/dependency-releases.yml",
    "tests/android-build-inputs-test.py",
    "tests/android-orchestration-test.py",
    "tests/browser-cpu-selection-test.py",
    "tests/device/run_control_plane_tests.py",
    "tests/host-producer-preparation-test.py",
    "tests/host-selection-test.py",
    "tests/project-suite-self-test.py",
    "tools/branch-cleanup/adoption.py",
    "tools/ios-build-qualification/fixtures/host-launcher-52f.sh",
    "tools/ios-build-qualification/host-workflow.yml",
    "tools/ios-build-qualification/host.py",
    "tools/repository-checks/android-build-inputs.py",
    "tools/repository-checks/android-host-prepare.sh",
    "tools/repository-checks/android_gate.py",
    "tools/repository-checks/browser_cpu.py",
    "tools/repository-checks/host_selection.py",
    "tools/repository-checks/package_checks.py",
    "tools/repository-checks/tool_dependencies.py",
    "tools/repository-checks/workflows/android-required.yml",
    "tools/repository-checks/workflows/android/repository-checks-direct-browser.yml",
    "tools/repository-checks/workflows/android/repository-checks.yml",
    "tools/repository-checks/workflows/browser-client.yml",
    "tools/repository-checks/workflows/browser/repository-checks.yml",
    "tools/repository-checks/workflows/host/parent-qualification.yml",
    "tools/repository-checks/workflows/host/project-tests.yml",
    "tools/repository-checks/workflows/packages/parent-qualification.yml",
    "tools/repository-checks/workflows/packages/project-tests.yml",
    "tools/repository-checks/workflows/packages/repository-checks-direct.yml",
    "tools/repository-checks/workflows/packages/repository-checks.yml",
    "tools/repository-checks/workflows/packages/sync-validation.yml",
    "tools/repository-checks/workflows/producers/project-tests.yml",
    "tools/test-evidence/attested-test.py",
    "tools/test-evidence/attested.py",
    "tools/test-evidence/producer-api-test.py",
    "tools/test-evidence/producer-test.py",
    "tools/test-evidence/producer.py",
    "tools/test-evidence/producer_api.py",
    ".github/android-checks.json",
    ".github/codeql/codeql-config.yml",
    ".github/repository-checks.json",
    ".github/sync-test-reuse.json",
    ".github/test-suites.json",
    ".github/workflows/branch-cleanup.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/parent-qualification.yml",
    ".github/workflows/project-tests.yml",
    ".github/workflows/repository-checks.yml",
    ".github/workflows/repository-health.yml",
    ".github/workflows/sync-test-reuse.yml",
    ".github/workflows/sync-validation.yml",
    ".github/workflows/workflow-security.yml",
    "tests/android-ci-test.py",
    "tests/branch-cleanup-test.py",
    "tests/branch-policy-test.py",
    "tests/codeql-selection-test.py",
    "tests/ios-build-qualification-test.py",
    "tests/ios-input-selection-test.py",
    "tests/native-ci-test.py",
    "tests/repository-checks-test.py",
    "tests/repository-health-test.py",
    "tests/run-project-tests.py",
    "tests/workflow-contract-test.py",
    "tools/branch-cleanup/cleanup.py",
    "tools/branch-policy/check.py",
    "tools/ios-build-qualification/check.py",
    "tools/ios-build-qualification/inputs.py",
    "tools/native-tests/README.md",
    "tools/native-tests/check.py",
    "tools/repository-checks/android.py",
    "tools/repository-checks/check.py",
    "tools/repository-checks/codeql.py",
    "tools/repository-checks/workflows/browser-direct-client.yml",
    "tools/repository-checks/workflows/repository-checks.yml",
    "tools/sync-test-reuse/differential.py",
    "tools/sync-test-reuse/gate.py",
    "tools/sync-test-reuse/qualification.py",
    "tools/sync-test-reuse/test.py",
    "tools/test-evidence/execution-test.py",
    "tools/test-evidence/execution.py",
    "tools/test-evidence/inputs.py",
    "tools/test-evidence/qualification-producer-test.py",
    "tools/test-evidence/registry-test.py",
    "tools/test-evidence/run.py",
    "tools/test-evidence/runtime-test.py",
    "tools/test-evidence/runtime.py",
    "tools/test-evidence/test.py",
    "tools/test-evidence/validate-sync-test.py",
    "tools/test-evidence/validate-sync.py",
})
# The reviewed Doctor CLI, project self-test, health test and runner are executable in Git. No other
# executable host path, document or mode transition gets an implicit exemption.
INDEPENDENT_EXECUTABLE_HOST_PATHS = frozenset({
    "tools/repository-health/check.py",
    "tests/project-suite-self-test.py", "tests/repository-health-test.py", "tests/run-project-tests.py",
})
INDEPENDENT_DOCUMENTS = frozenset({
    "CONTRIBUTING.md", "README.md", "ios/README.md", "tests/PROJECT_TESTING.md",
})
# These locks are outside the reviewed iOS readers. Their bytes remain in normal
# application fingerprints. Only an independently required exact package owner
# can admit a changed lock; they are deliberately NOT independent-host paths.
NPM_PACKAGE_PROFILES = {
    "browser-client/package-lock.json": ("browser-client", "source-map-postcss-v1"),
    "script-archive/marketplace/S3Server/package-lock.json": (
        "script-archive/marketplace/S3Server", "proxy-addr-express-v1"),
}

_OBJECT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_MODES = {"100644": "blob", "100755": "blob", "120000": "blob", "160000": "commit"}
_BOUNDARY_DOMAIN = "overte-ios-repository-reader-boundary-v1"
_INPUT_DOMAIN = "overte-ios-repository-inputs-v1"


class InputError(ValueError):
    """A complete immutable input identity could not be established."""


@dataclass(frozen=True, order=True)
class Entry:
    path: str
    mode: str
    object_type: str
    oid: str

    def identity(self) -> dict:
        return {"path": self.path, "mode": self.mode, "type": self.object_type, "oid": self.oid}


@dataclass(frozen=True)
class Snapshot:
    revision: str
    tree: str
    entries: tuple[Entry, ...]


def _digest(value: object) -> str:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _git(repository: Path | str, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "--no-replace-objects", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *arguments],
            cwd=repository, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise InputError("cannot read the complete immutable Git tree") from error


def _path(value: str) -> None:
    path = PurePosixPath(value)
    if not value or value == "." or "\0" in value or "\\" in value or path.is_absolute() or str(path) != value \
            or any(part in {".", ".."} or part.casefold() == ".git" for part in path.parts):
        raise InputError("invalid immutable tree path")


def read_snapshot(repository: Path | str, revision: str) -> Snapshot:
    """Enumerate an exact commit, never a mutable ref or the current worktree.

    Replacement refs are disabled. Missing objects, malformed/incomplete tree
    output and paths that cannot be represented safely fail closed.
    """
    if not isinstance(revision, str) or not _OBJECT.fullmatch(revision):
        raise InputError("an exact immutable commit SHA is required")
    try:
        resolved = _git(repository, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
        if resolved != revision:
            raise InputError("revision must identify a commit directly")
        tree = _git(repository, "rev-parse", "--verify", "--end-of-options", revision + "^{tree}").decode().strip()
        if not _OBJECT.fullmatch(tree) or len(tree) != len(revision):
            raise InputError("invalid immutable root tree")
        raw = _git(repository, "ls-tree", "-rz", "--full-tree", tree)
        if raw and not raw.endswith(b"\0"):
            raise InputError("incomplete immutable tree inventory")
        entries, seen = [], set()
        for record in raw.split(b"\0")[:-1]:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split(" ")
            path = encoded_path.decode("utf-8", errors="strict")
            _path(path)
            if path in seen or _MODES.get(mode) != kind or not _OBJECT.fullmatch(oid) or len(oid) != len(revision):
                raise InputError("invalid or duplicate immutable tree entry")
            seen.add(path)
            entries.append(Entry(path, mode, kind, oid))
        return Snapshot(revision, tree, tuple(sorted(entries)))
    except (UnicodeError, ValueError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError("invalid immutable tree inventory") from error


def _kind(entry: Entry) -> str:
    expected = "100755" if entry.path in INDEPENDENT_EXECUTABLE_HOST_PATHS else "100644"
    if entry.path in INDEPENDENT_HOST_PATHS and entry.mode == expected:
        return "independent-host"
    if entry.mode == "100644":
        if entry.path in INDEPENDENT_DOCUMENTS or (
                entry.path.startswith("docs/") and PurePosixPath(entry.path).suffix == ".md"):
            return "independent-documentation"
    # Markdown in resources/scripts, executable documents and unknown inputs
    # remain application inputs. File extensions alone do not prove isolation.
    return "application-input"


def _boundary(snapshot: Snapshot) -> str:
    return _digest({"domain": _BOUNDARY_DOMAIN,
                    "entries": [entry.identity() for entry in snapshot.entries
                                if _kind(entry) == "application-input" and entry.path not in NPM_PACKAGE_PROFILES]})


def review_boundary(repository: Path | str, revision: str) -> dict:
    """Calculate a proposed anchor for human review; this does not approve it.

    Never automatically replace REVIEWED_BOUNDARY with a candidate's value.
    The current graph must be reviewed for new reads of excluded paths first.
    """
    snapshot = read_snapshot(repository, revision)
    return {"revision": snapshot.revision, "tree": snapshot.tree, "boundary": _boundary(snapshot)}


def _policy() -> str:
    # Bind both declarative rules and the actual trusted implementation.
    return _digest({"domain": _INPUT_DOMAIN, "reviewed_revision": REVIEWED_REVISION,
                    "reviewed_boundary": REVIEWED_BOUNDARY,
                    "host_paths": sorted(INDEPENDENT_HOST_PATHS), "documents": sorted(INDEPENDENT_DOCUMENTS),
                    "executable_host_paths": sorted(INDEPENDENT_EXECUTABLE_HOST_PATHS),
                    "conditional_npm_paths": NPM_PACKAGE_PROFILES,
                    "document_rule": "ordinary-docs/**/*.md", "nonregular_rule": "disable-all-exclusions",
                    "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def _identity(snapshot: Snapshot, policy: str, admitted_npm=()) -> dict:
    nonregular = [entry.path for entry in snapshot.entries if entry.mode in {"120000", "160000"}]
    boundary = _boundary(snapshot)
    ordinary_locks = all(entry.mode == "100644" and entry.object_type == "blob"
                         for entry in snapshot.entries if entry.path in NPM_PACKAGE_PROFILES)
    applicable = boundary == REVIEWED_BOUNDARY and not nonregular and ordinary_locks
    selected = [entry.identity() for entry in snapshot.entries
                if not applicable or (_kind(entry) == "application-input" and entry.path not in admitted_npm)]
    return {"revision": snapshot.revision, "tree": snapshot.tree, "boundary": boundary,
            "exclusions_applicable": applicable, "nonregular_paths": nonregular,
            "fingerprint": _digest({"domain": _INPUT_DOMAIN, "policy": policy,
                                    "exclusions_applied": applicable, "entries": selected})}


def input_fingerprint(repository: Path | str, revision: str) -> dict:
    """Identify complete repository inputs; stale boundaries include EVERY entry."""
    return _identity(read_snapshot(repository, revision), _policy())


def npm_selector():
    """Load the dependency definitions from this trusted policy, never candidate code."""
    path = Path(__file__).resolve().parents[2] / "tools/repository-checks/npm_consumers.py"
    if not path.is_file() or any(parent.is_symlink() for parent in (path, *path.parents)):
        raise InputError("trusted npm dependency selector unavailable")
    spec = importlib.util.spec_from_file_location("ios_trusted_npm_consumers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def npm_package_admission(repository, previous, current, package_owner):
    """Check immutable dependency evidence supplied by the required host caller.

    This validates data, not remote branch protection or successful execution.
    host.py independently establishes the mandatory owner before supplying its
    plan. The separate required repository aggregate verifies execution receipts.
    """
    old = {entry.path: entry for entry in previous.entries}
    new = {entry.path: entry for entry in current.entries}
    # host.resolve() and the later selector can load separate trusted dataclass
    # instances. Compare immutable entry values, not Python class identities.
    changed = sorted(path for path in NPM_PACKAGE_PROFILES
                     if (old[path].identity() if path in old else None)
                     != (new[path].identity() if path in new else None))
    if not changed or not isinstance(package_owner, dict):
        return None
    try:
        if package_owner.get("consumer_generation") is not True \
                or package_owner.get("unknown") is not False \
                or package_owner.get("base") != previous.revision \
                or package_owner.get("candidate") != current.revision \
                or package_owner.get("tree") != current.tree \
                or not isinstance(package_owner.get("policy"), dict) or not package_owner["policy"] \
                or not isinstance(package_owner.get("package_set"), list) \
                or any(project not in {value[0] for value in NPM_PACKAGE_PROFILES.values()}
                       for project in package_owner["package_set"]) \
                or len(set(package_owner["package_set"])) != len(package_owner["package_set"]) \
                or package_owner.get("plan") != _digest({key: value for key, value in package_owner.items()
                                                        if key != "plan"}).removeprefix("sha256:"):
            return None
        selected = npm_selector().select(repository, previous.revision, current.revision)
        if selected.get("unknown") is not False or package_owner.get("dependency_profiles") != selected:
            return None
        for path in changed:
            if any(path not in tree or tree[path].mode != "100644" or tree[path].object_type != "blob"
                   for tree in (old, new)):
                return None
            project, profile = NPM_PACKAGE_PROFILES[path]
            item = selected["projects"][project]
            if item["changed_paths"] != [path]:
                return None
            # Complete package validation owns other lock graph changes too.
            # Both immutable iOS reader boundaries are still required; this
            # grants no package PASS, app artifact or native reuse authority.
            focused = item["profile"] in {profile, "full"} and item["required"] is True \
                and project in package_owner["package_set"]
            formatting = item["profile"] == "none" and item["required"] is False \
                and item["reason"] == "reviewed-lockfile-format-only" \
                and project not in package_owner["package_set"]
            if not (focused or formatting):
                return None
        return {"reason": "required-reviewed-npm-consumers", "changedPaths": changed,
                "base": {"revision": previous.revision, "tree": previous.tree},
                "candidate": {"revision": current.revision, "tree": current.tree},
                "packagePlan": package_owner["plan"], "packagePolicy": package_owner["policy"],
                "dependencyPlan": selected["plan"],
                "projects": {NPM_PACKAGE_PROFILES[path][0]: selected["projects"][NPM_PACKAGE_PROFILES[path][0]]
                             for path in changed}}
    except (InputError, OSError, ValueError, TypeError, KeyError, AttributeError, ImportError):
        return None


def candidate_plan(repository: Path | str, base: str, candidate: str, *, package_owner=None) -> dict:
    """Classify every actual tree delta without accepting a caller path list.

    The eventual trusted caller must independently validate repository, target,
    exact event merge parents, owning host checks and final execution evidence.
    Empty inventories stay conservative; this is not a manual-build exemption.
    """
    previous, current = read_snapshot(repository, base), read_snapshot(repository, candidate)
    policy = _policy()
    npm = npm_package_admission(repository, previous, current, package_owner)
    admitted = npm["changedPaths"] if npm is not None else ()
    base_identity, candidate_identity = (_identity(snapshot, policy, admitted) for snapshot in (previous, current))
    old, new = {entry.path: entry for entry in previous.entries}, {entry.path: entry for entry in current.entries}
    changes = []
    for path in sorted(old.keys() | new.keys()):
        before, after = old.get(path), new.get(path)
        if before == after:
            continue
        kinds = {_kind(entry) for entry in (before, after) if entry is not None}
        changes.append({"path": path, "old": before.identity() if before else None,
                        "new": after.identity() if after else None,
                        "kind": "independent-npm-package" if path in admitted else
                            "application-input" if "application-input" in kinds else kinds.pop()})
    applicable = base_identity["exclusions_applicable"] and candidate_identity["exclusions_applicable"]
    if not changes:
        reason = "empty-change-inventory"
    elif base_identity["nonregular_paths"] or candidate_identity["nonregular_paths"]:
        reason = "unproven-symlink-or-gitlink-closure"
    elif any(change["kind"] == "application-input" for change in changes):
        reason = "application-inputs-changed"
    elif not applicable:
        reason = "reader-boundary-not-reviewed"
    else:
        reason = "independent-host-or-documentation-only"
    result = {"schema": 1, "policy": policy, "reviewed_revision": REVIEWED_REVISION,
            "reviewed_boundary": REVIEWED_BOUNDARY, "base": base_identity, "candidate": candidate_identity,
            "exclusions_applicable": applicable, "changes": changes, "reason": reason,
            "requires_application_build": reason != "independent-host-or-documentation-only"}
    if npm is not None:
        result["package_ownership"] = npm
    return result
