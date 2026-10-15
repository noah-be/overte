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
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


REVIEWED_REVISION = "52f1cc38180e96cdfd8049a4be93517961ae7dbd"
REVIEWED_BOUNDARY = "sha256:f2723395852e96ce2758bbf4126b844f57a2f29d6937cd86989b9404cc1d751f"

# Reviewed host control-plane files, not generic tests/** or tools/** patterns.
# In particular, E2E builds can compile tests/device source and fixtures.
# These files were not read by the app configure/build/package graph at the
# reviewed revision. The newly staged selector and its test have no app caller.
INDEPENDENT_HOST_PATHS = frozenset({
    ".github/sync-test-reuse.json",
    ".github/test-suites.json",
    "tests/ios-build-qualification-test.py",
    "tests/ios-input-selection-test.py",
    "tests/native-ci-test.py",
    "tests/repository-checks-test.py",
    "tests/workflow-contract-test.py",
    "tools/ios-build-qualification/inputs.py",
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
INDEPENDENT_DOCUMENTS = frozenset({
    "CONTRIBUTING.md", "README.md", "ios/README.md", "tests/PROJECT_TESTING.md",
})

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
    if entry.mode == "100644":
        if entry.path in INDEPENDENT_HOST_PATHS:
            return "independent-host"
        if entry.path in INDEPENDENT_DOCUMENTS or (
                entry.path.startswith("docs/") and PurePosixPath(entry.path).suffix == ".md"):
            return "independent-documentation"
    # Markdown in resources/scripts, executable documents and unknown inputs
    # remain application inputs. File extensions alone do not prove isolation.
    return "application-input"


def _boundary(snapshot: Snapshot) -> str:
    return _digest({"domain": _BOUNDARY_DOMAIN,
                    "entries": [entry.identity() for entry in snapshot.entries if _kind(entry) == "application-input"]})


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
                    "document_rule": "ordinary-docs/**/*.md", "nonregular_rule": "disable-all-exclusions",
                    "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def _identity(snapshot: Snapshot, policy: str) -> dict:
    nonregular = [entry.path for entry in snapshot.entries if entry.mode in {"120000", "160000"}]
    boundary = _boundary(snapshot)
    applicable = boundary == REVIEWED_BOUNDARY and not nonregular
    selected = [entry.identity() for entry in snapshot.entries
                if not applicable or _kind(entry) == "application-input"]
    return {"revision": snapshot.revision, "tree": snapshot.tree, "boundary": boundary,
            "exclusions_applicable": applicable, "nonregular_paths": nonregular,
            "fingerprint": _digest({"domain": _INPUT_DOMAIN, "policy": policy,
                                    "exclusions_applied": applicable, "entries": selected})}


def input_fingerprint(repository: Path | str, revision: str) -> dict:
    """Identify complete repository inputs; stale boundaries include EVERY entry."""
    return _identity(read_snapshot(repository, revision), _policy())


def candidate_plan(repository: Path | str, base: str, candidate: str) -> dict:
    """Classify every actual tree delta without accepting a caller path list.

    The eventual trusted caller must independently validate repository, target,
    exact event merge parents, owning host checks and final execution evidence.
    Empty inventories stay conservative; this is not a manual-build exemption.
    """
    previous, current = read_snapshot(repository, base), read_snapshot(repository, candidate)
    policy = _policy()
    base_identity, candidate_identity = _identity(previous, policy), _identity(current, policy)
    old, new = {entry.path: entry for entry in previous.entries}, {entry.path: entry for entry in current.entries}
    changes = []
    for path in sorted(old.keys() | new.keys()):
        before, after = old.get(path), new.get(path)
        if before == after:
            continue
        kinds = {_kind(entry) for entry in (before, after) if entry is not None}
        changes.append({"path": path, "old": before.identity() if before else None,
                        "new": after.identity() if after else None,
                        "kind": "application-input" if "application-input" in kinds else kinds.pop()})
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
    return {"schema": 1, "policy": policy, "reviewed_revision": REVIEWED_REVISION,
            "reviewed_boundary": REVIEWED_BOUNDARY, "base": base_identity, "candidate": candidate_identity,
            "exclusions_applicable": applicable, "changes": changes, "reason": reason,
            "requires_application_build": reason != "independent-host-or-documentation-only"}
