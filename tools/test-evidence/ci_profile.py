#!/usr/bin/env python3
"""Finite, dormant CI37 source admission without executing candidate code.

This deliberately conservative generation binds the complete immutable tree,
including import shadows, discovery membership, subprocess implementations and
native registration inputs. Only a few reviewed data leaves may change bytes.
It does not claim a complete dynamic call graph or supply runtime evidence.
The protected runner must independently capture the actual CI37 environment.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import stat

import inputs


ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/ci37-runtime.json"
PINNED_SOURCE = ".github/android-orchestration.json"
ENVIRONMENT_SCHEMA = 2
PROFILE = "ubuntu24-ci37-v1"
# Source-only preparation. Neither changing JSON nor a caller-selected suite
# list can activate this profile. No CLI or workflow override is provided.
SOURCE_READY = False
SUITES = (
    "producer-proof", "producer-api", "dependency-releases", "project-runner",
    "python-test-runner", "repository-checks", "android-build-inputs",
    "codeql-selection", "ios-build-qualification", "ios-input-selection",
    "repository-policy", "policy-consistency", "documentation-contracts",
    "repository-doctor", "repository-maintenance", "branch-policy",
    "branch-name-guard", "branch-cleanup", "sync-test-reuse",
    "workflow-action-pins", "release-bundle", "workflow-contracts",
    "repository-health", "issue-intake", "project-coverage", "documentation",
    "native-ci-policy", "native-registration", "source-layout", "test-evidence",
    "android-ci", "browser-cpu-selection", "host-producer-preparation",
    "attested-runtime", "android-orchestration", "host-selection",
    "android-owner-transfer",
)
_PRODUCT_QUICK = frozenset({
    "codeql-remediation", "javascript-behavior", "server-console-behavior",
    "device-result-schema", "device-jenkins", "desktop-input-protocol",
    "performance-contracts",
})
_HOST_SUITES = frozenset({
    "device-control-plane-full", "safe-landing-lifecycle", "embedded-web-policy",
    "embedded-web-qml", "web-entity-visibility", "places-native-qml",
    "account-auth-dispatch", "lod-preferences", "goto-dialog-script",
    "recorded-voice-native", "recorded-voice-qml", "snapshot-native", "snapshot-qml",
    "document-tree-native", "obj-material-native", "shared-script-behavior",
})
_REASONS = frozenset({"reviewed-ci-only-inputs", "reviewed-ci-and-package-owners"})
_PACKAGE_LOCKS = frozenset({
    "browser-client/package-lock.json", "script-archive/marketplace/S3Server/package-lock.json",
})
# Keep membership and ordinary mode/type for these exact documentation leaves.
# The fixed documentation validator reads Markdown links/headings as data; the
# policy display check compares a generated text block in PROJECT_TESTING.md.
# Neither executes documentation snippets. All workflow bytes remain bound:
# reviewed suite implementations do execute some YAML run snippets.
# Additions and every neighboring path remain bound.
_VARIABLE_DATA = frozenset({
    "README.md", "tests/PROJECT_TESTING.md", "docs/BRANCH_WORKFLOW.md",
})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema", "enabled", "profile", "epoch", "suites", "definition_digest", "generation_digest",
    "not_before", "max_age_seconds",
})


class CIProfileError(ValueError):
    """The finite CI37 source/profile contract is unavailable; use the full owner."""


def _require(condition, message):
    if not condition:
        raise CIProfileError(message)


def _digest(value):
    return "sha256:" + hashlib.sha256(inputs._canonical(value)).hexdigest()


def _validate_policy(value):
    _require(isinstance(value, dict) and set(value) == _FIELDS, "unsupported CI37 policy fields")
    _require(type(value["schema"]) is int and value["schema"] == 1
             and type(value["enabled"]) is bool and value["profile"] == PROFILE,
             "unsupported CI37 policy profile")
    _require(isinstance(value["epoch"], str)
             and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", value["epoch"]),
             "unsupported CI37 policy epoch")
    _require(isinstance(value["not_before"], str)
             and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value["not_before"]),
             "CI37 policy requires a fixed UTC admission boundary")
    try:
        datetime.fromisoformat(value["not_before"][:-1] + "+00:00")
    except ValueError:
        raise CIProfileError("CI37 policy admission boundary is invalid") from None
    _require(type(value["max_age_seconds"]) is int and 0 < value["max_age_seconds"] <= 259200,
             "unsupported CI37 validity policy")
    _require(value["suites"] == list(SUITES), "CI37 policy must retain the exact ordered inventory")
    for name in ("definition_digest", "generation_digest"):
        _require(isinstance(value[name], str) and _DIGEST.fullmatch(value[name]),
                 "missing reviewed CI37 generation identity")
    return value


def load_policy(root=ROOT):
    """Read the fixed trusted policy, including its disabled preparation state."""
    path = Path(root)
    try:
        for component in Path(POLICY).parts:
            path /= component
            _require(not path.is_symlink(), "CI37 trusted policy must not contain aliases")
        _require(path.is_file() and path.stat().st_size <= 32_000, "CI37 trusted policy is unavailable")
        raw = path.read_bytes()
        _require(len(raw) <= 32_000, "CI37 trusted policy is oversized")
        value = json.loads(raw, object_pairs_hook=inputs._unique_object)
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, CIProfileError):
            raise
        raise CIProfileError("CI37 trusted policy is invalid") from None
    return _validate_policy(value)


def policy_identity(policy):
    """Identify the strict policy; protected controller identity also binds bytes."""
    return _digest(_validate_policy(policy))


def _pinned_source_entry(root):
    """Read the one fixed protected leaf that participates in another digest.

    Its complete raw bytes, ordinary mode and every path component are checked.
    It is never candidate data, a supplied exclusion map or an environment proof.
    The repository uses SHA1 Git object identities; other object formats fail.
    """
    path = Path(root)
    _require(path.is_absolute() and ".." not in path.parts, "CI37 pinned source requires a fixed protected root")
    try:
        current = Path(path.anchor)
        for component in (*path.parts[1:], *Path(PINNED_SOURCE).parts):
            current /= component
            _require(not current.is_symlink(), "CI37 pinned source must not contain aliases")
        info = current.stat()
        _require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o111 and info.st_size <= 1_000_000,
                 "CI37 pinned source must be a bounded ordinary nonexecutable file")
        raw = current.read_bytes()
        _require(len(raw) <= 1_000_000, "CI37 pinned source exceeds its byte bound")
    except OSError:
        raise CIProfileError("CI37 pinned source is unavailable") from None
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return {"mode": "100644", "type": "blob", "sha": hashlib.sha1(header + raw).hexdigest()}


def definition_digest(registry):
    """Bind commands, contexts, closures, reviewed imports and control inputs."""
    try:
        inputs._validate_registry(registry)
    except (TypeError, ValueError):
        raise CIProfileError("CI37 requires the complete trusted registry") from None
    suites = registry["suites"]
    expected = tuple(name for name, suite in suites.items()
                     if suite["layer"] == "quick" and name not in _PRODUCT_QUICK)
    _require(expected == SUITES, "trusted quick inventory is not the reviewed CI37 generation")
    _require(suites.keys() == set(SUITES) | _PRODUCT_QUICK | _HOST_SUITES
             and all(suites[name]["layer"] == "quick" for name in _PRODUCT_QUICK)
             and all(suites[name]["layer"] == "host" for name in _HOST_SUITES),
             "CI37 requires a complete registry with its separate product owners")
    return _digest({"suites": [{"name": name, "definition": suites[name]} for name in SUITES],
                    "registry_inventory": list(suites),
                    "control_inputs": registry["control_inputs"]})


def generation(tree, registry):
    """Bind an immutable broad source superset and all lookup membership.

    The CI37 policy is omitted to avoid a self-cycle. Only the fixed Android
    orchestration leaf omits its SHA to break the other reviewed anchor cycle;
    its path/mode/type remain bound. Admission pins its complete bytes against
    the actual protected root and both immutable trees. Neither exception can
    narrow ordinary suite fingerprints or protected controller identity.
    """
    try:
        inputs._validate_tree(tree)
    except (TypeError, ValueError):
        raise CIProfileError("CI37 requires a complete immutable source inventory") from None
    _require(bool(tree), "CI37 source inventory is empty")
    entries = []
    for path, entry in sorted(tree.items()):
        _require(entry["mode"] in {"100644", "100755"} and entry["type"] == "blob",
                 "CI37 source inventory contains an alias or nonregular entry")
        if path == POLICY:
            _require(entry["mode"] == "100644", "CI37 policy must be an ordinary nonexecutable blob")
            continue
        item = {"path": path, **entry}
        if path in _VARIABLE_DATA or path == PINNED_SOURCE:
            _require(entry["mode"] == "100644", "CI37 reviewed data must remain nonexecutable")
            del item["sha"]
        entries.append(item)
    return _digest({"kind": "ci37-conservative-source-v1", "entries": entries,
                    "definition_digest": definition_digest(registry)})


def validate_selection(selection, candidate_tree, trusted_tree, registry, *, target="main",
                       regular=True, unknown=False, policy=None, require_enabled=True, root=ROOT):
    """Admit only the independently recomputed main CI37 selection and generation.

    Production callers leave require_enabled at its default. False is for pure
    source preparation/tests and yields no runtime or execution qualification.
    The independent router still owns changed-path and workflow authorization.
    """
    value = load_policy(root) if policy is None else _validate_policy(policy)
    _require(type(require_enabled) is bool, "invalid CI37 source preparation mode")
    if require_enabled:
        _require(SOURCE_READY and value["enabled"] is True, "CI37 runtime profile is not activated")
    _require(target == "main" and regular is True and unknown is False,
             "CI37 requires a known regular main plan")
    required = {"suites", "reason", "full_host", "include_platform"}
    _require(isinstance(selection, dict) and required <= selection.keys()
             and selection.keys() <= required | {"package_owned_paths"},
             "unsupported CI37 selection fields")
    _require(selection["suites"] == list(SUITES) and selection["full_host"] is False
             and selection["include_platform"] is False and isinstance(selection["reason"], str)
             and selection["reason"] in _REASONS,
             "CI37 requires the exact independently selected 37 owners")
    packages = selection.get("package_owned_paths", [])
    _require(isinstance(packages, list)
             and all(isinstance(path, str) and path in _PACKAGE_LOCKS for path in packages)
             and packages == sorted(set(packages))
             and bool(packages) == (selection["reason"] == "reviewed-ci-and-package-owners"),
             "CI37 package work requires its finite independent owner")
    definitions = definition_digest(registry)
    _require(definitions == value["definition_digest"], "CI37 command definitions changed")
    candidate_generation = generation(candidate_tree, registry)
    trusted_generation = generation(trusted_tree, registry)
    _require(candidate_generation == trusted_generation == value["generation_digest"],
             "CI37 executable, discovery or lookup generation changed")
    old_policy, new_policy = trusted_tree.get(POLICY), candidate_tree.get(POLICY)
    _require(isinstance(old_policy, dict) and old_policy == new_policy
             and old_policy["mode"] == "100644" and old_policy["type"] == "blob",
             "CI37 policy requires identical ordinary trusted and candidate entries")
    pinned = _pinned_source_entry(root)
    _require(candidate_tree.get(PINNED_SOURCE) == trusted_tree.get(PINNED_SOURCE) == pinned,
             "CI37 fixed pinned source differs from the protected root or immutable trees")
    return {"schema": ENVIRONMENT_SCHEMA, "profile": PROFILE, "epoch": value["epoch"],
            "suites": list(SUITES), "definition_digest": definitions,
            "generation_digest": candidate_generation, "policy_digest": policy_identity(value),
            "pinned_source": {"path": PINNED_SOURCE, **pinned}}
