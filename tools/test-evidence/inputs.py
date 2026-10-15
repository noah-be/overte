#!/usr/bin/env python3
"""Fingerprint complete, trusted test input closures without running candidate code.

The registry belongs to the trusted validator. Trees describe immutable commits;
neither candidate routing metadata nor the current working directory can narrow
the inputs used to authorize reuse.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import subprocess


class InputError(ValueError):
    """An input identity cannot safely authorize reuse."""


_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_OBJECT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MODES = {"100644": "blob", "100755": "blob", "120000": "blob", "160000": "commit"}


def _canonical(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise InputError("input identity must contain canonical JSON values") from error


def _path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise InputError(f"{label} must be a nonempty relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != value or value == ".":
        raise InputError(f"{label} must be a normalized relative path")
    return value


def _paths(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise InputError(f"{label} must be {'a nonempty' if nonempty else 'a'} path list")
    for item in value:
        _path(item, label)
    if len(value) != len(set(value)):
        raise InputError(f"{label} contains duplicate paths")
    return value


def _validate_registry(registry: object) -> dict:
    if not isinstance(registry, dict) or set(registry) != {"schema", "control_inputs", "suites"}:
        raise InputError("invalid test input registry fields")
    if type(registry["schema"]) is not int or registry["schema"] != 1:
        raise InputError("unsupported test input registry schema")
    _paths(registry["control_inputs"], "control inputs", nonempty=True)
    suites = registry["suites"]
    if not isinstance(suites, dict) or not suites:
        raise InputError("registry suites must be a nonempty object")
    fields = {"command", "layer", "scope", "environment", "closure"}
    for name, suite in suites.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise InputError("invalid suite name")
        if not isinstance(suite, dict) or set(suite) != fields:
            raise InputError(f"invalid definition for suite {name}")
        command = suite["command"]
        if not isinstance(command, list) or not command or any(
            not isinstance(argument, str) or not argument or "\0" in argument for argument in command
        ):
            raise InputError(f"invalid command for suite {name}")
        executable = command[0]
        if "/" in executable or "\\" in executable or any(character.isspace() for character in executable):
            raise InputError(f"suite {name} command must use a canonical executable name")
        if executable.startswith("python") and executable != "python":
            raise InputError(f"suite {name} Python command must use canonical python")
        if suite["layer"] not in ("quick", "host") or suite["scope"] not in ("content", "candidate"):
            raise InputError(f"invalid execution scope for suite {name}")
        if not isinstance(suite["environment"], str) or not _NAME.fullmatch(suite["environment"]):
            raise InputError(f"invalid environment contract for suite {name}")
        closure = suite["closure"]
        if not isinstance(closure, dict) or set(closure) != {"kind", "inputs", "required"}:
            raise InputError(f"invalid input closure for suite {name}")
        if closure["kind"] not in ("patterns", "repository"):
            raise InputError(f"invalid input closure kind for suite {name}")
        _paths(closure["inputs"], f"suite {name} inputs", nonempty=closure["kind"] == "patterns")
        if closure["kind"] == "repository" and closure["inputs"]:
            raise InputError(f"repository closure for suite {name} cannot narrow its inputs")
        _paths(closure["required"], f"suite {name} required inputs")
        if any(any(character in relative for character in "*?[") for relative in closure["required"]):
            raise InputError(f"suite {name} required inputs must be exact paths")
        if closure["kind"] == "patterns" and any(
            not any(fnmatchcase(relative, pattern) for pattern in closure["inputs"])
            for relative in closure["required"]
        ):
            raise InputError(f"suite {name} required inputs must be inside its closure")
    _canonical(registry)
    return registry


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate registry JSON field")
        result[key] = value
    return result


def load_registry(path: Path | str) -> dict:
    """Read and strictly validate a registry from the trusted validator checkout."""
    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InputError("cannot read the trusted test input registry") from error
    return _validate_registry(registry)


def _validate_tree(tree: object) -> dict:
    if not isinstance(tree, dict):
        raise InputError("immutable tree must be a path-to-entry object")
    for path, entry in tree.items():
        _path(path, "tree path")
        if not isinstance(entry, dict) or set(entry) != {"mode", "type", "sha"}:
            raise InputError("tree entry must contain mode, type and object SHA")
        if not isinstance(entry["mode"], str) or _MODES.get(entry["mode"]) != entry["type"]:
            raise InputError("tree entry has an invalid mode or object type")
        if not isinstance(entry["sha"], str) or not _OBJECT.fullmatch(entry["sha"]):
            raise InputError("tree entry has an invalid object SHA")
    return tree


def full_tree(root: Path | str, commit: str = "HEAD") -> dict[str, dict[str, str]]:
    """Read every tracked entry of an immutable commit, including gitlinks.

    Resolve refs before enumeration. No checkout, filesystem import, candidate
    script, hook, or source-controlled command is executed.
    """
    if not isinstance(commit, str) or not commit or "\0" in commit:
        raise InputError("commit identity is invalid")
    try:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", commit + "^{commit}"],
            cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
        if not _OBJECT.fullmatch(resolved):
            raise InputError("commit did not resolve to an immutable object")
        raw = subprocess.run(
            ["git", "ls-tree", "-rz", "--full-tree", resolved], cwd=root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
        tree = {}
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, sha = metadata.decode("ascii").split(" ")
            path = encoded_path.decode("utf-8", errors="strict")
            if path in tree:
                raise InputError("immutable tree contains a duplicate path")
            tree[path] = {"mode": mode, "type": object_type, "sha": sha}
    except (OSError, subprocess.CalledProcessError, ValueError, UnicodeError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError("cannot enumerate the immutable commit tree") from error
    return _validate_tree(tree)


def _selected_entries(tree: dict, patterns: list[str]) -> list[dict[str, str]]:
    return [{"path": path, **tree[path]} for path in sorted(tree)
            if any(fnmatchcase(path, pattern) for pattern in patterns)]


def selected_entries(tree: dict, patterns: list[str]) -> list[dict[str, str]]:
    """Select deterministic entries; modes, symlinks and gitlinks stay visible."""
    _validate_tree(tree)
    _paths(patterns, "input patterns")
    return _selected_entries(tree, patterns)


def _environment(environment: object) -> dict:
    if not isinstance(environment, dict) or not environment:
        raise InputError("runtime environment identity must be a nonempty JSON object")

    def keys(value: object) -> None:
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise InputError("runtime environment JSON keys must be strings")
            for item in value.values():
                keys(item)
        elif isinstance(value, list):
            for item in value:
                keys(item)
        elif value is not None and type(value) not in (str, int, float, bool):
            raise InputError("runtime environment must contain only JSON values")

    keys(environment)
    _canonical(environment)
    return environment


def _suite_fingerprint(registry: dict, suite_name: str, tree: dict, environment: dict) -> str:
    suite = registry["suites"][suite_name]
    closure = suite["closure"]
    missing = sorted(set(closure["required"]) - set(tree))
    if missing:
        raise InputError(f"suite {suite_name} is missing required inputs")
    inputs = [{"path": path, **tree[path]} for path in sorted(tree)] if closure["kind"] == "repository" \
        else _selected_entries(tree, closure["inputs"])
    controls = _selected_entries(tree, registry["control_inputs"])
    if any(item["mode"] == "120000" for item in [*inputs, *controls]):
        # A symlink blob identifies the target string, not the bytes read after
        # dereferencing it. Without an independently proven referent closure it
        # cannot authorize reuse, even when the link itself has not changed.
        raise InputError(f"suite {suite_name} has an unproven symlink input closure")
    identity = {
        "schema": 1,
        "suite": suite_name,
        "definition": suite,
        "control_inputs": controls,
        "inputs": inputs,
        "environment": environment,
    }
    return "sha256:" + hashlib.sha256(_canonical(identity)).hexdigest()


def suite_fingerprint(registry: dict, suite_name: str, tree: dict, environment: dict) -> str:
    """Bind one suite's full source/configuration closure and runtime identity."""
    _validate_registry(registry)
    if not isinstance(suite_name, str) or suite_name not in registry["suites"]:
        raise InputError("suite is not in the trusted input registry")
    _validate_tree(tree)
    _environment(environment)
    return _suite_fingerprint(registry, suite_name, tree, environment)


def plan_reuse(
    registry: dict, parent_tree: dict, candidate_tree: dict, parent_results: dict,
    parent_environment: dict, candidate_environment: dict,
) -> dict:
    """Reuse only successful proof matching independently recomputed full inputs.

    ``parent_results`` maps names to ``{status: 'passed', fingerprint: 'sha256:…'}``.
    Missing/malformed per-suite proof schedules execution. Invalid global input
    identities raise InputError, so callers must fall back rather than authorize.
    Context-sensitive suites are always required for this new candidate.
    """
    _validate_registry(registry)
    _validate_tree(parent_tree)
    _validate_tree(candidate_tree)
    _environment(parent_environment)
    _environment(candidate_environment)
    if not isinstance(parent_results, dict):
        raise InputError("parent results must be a suite-to-result object")
    if set(parent_results) - set(registry["suites"]):
        raise InputError("parent results contain an unknown suite")
    plan = {"reused": [], "required": [], "reasons": {}}
    for name, suite in registry["suites"].items():
        reason = ""
        proof = parent_results.get(name)
        if suite["scope"] == "candidate":
            reason = "candidate-context suite requires execution"
        elif not isinstance(proof, dict) or set(proof) != {"status", "fingerprint"}:
            reason = "successful parent suite proof is missing or malformed"
        elif proof["status"] != "passed" or not isinstance(proof["fingerprint"], str) \
                or not _DIGEST.fullmatch(proof["fingerprint"]):
            reason = "parent suite did not provide a successful valid fingerprint"
        else:
            try:
                parent = _suite_fingerprint(registry, name, parent_tree, parent_environment)
                candidate = _suite_fingerprint(registry, name, candidate_tree, candidate_environment)
            except InputError:
                reason = "complete suite input closure is unavailable"
            else:
                if proof["fingerprint"] != parent:
                    reason = "parent proof does not match trusted inputs and definition"
                elif parent != candidate:
                    reason = "candidate inputs or runtime environment differ"
        if reason:
            plan["required"].append(name)
            plan["reasons"][name] = reason
        else:
            plan["reused"].append(name)
            plan["reasons"][name] = "successful proof matches complete candidate inputs"
    return plan
