#!/usr/bin/env python3
"""Keep derived branch and suite displays aligned with executable policy.

Default mode is read-only. --write updates only the two marked documentation
blocks; it never changes repository settings, policy manifests or GitHub.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {"branch-table": "docs/BRANCH_GOVERNANCE.md", "test-suites": "tests/PROJECT_TESTING.md"}


def read_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{path.name}: duplicate JSON key {key!r}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def display_path(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"{relative}: generated document escapes checkout")
    part = path
    while part != root:
        if part.is_symlink():
            raise ValueError(f"{relative}: generated document path must not contain symlinks")
        part = part.parent
    if path.exists() and path.stat().st_nlink != 1:
        raise ValueError(f"{relative}: generated document must not be hard-linked")
    return path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def branch_table(branches) -> str:
    rows = ["| Permanent branch | Parent | Task scope |", "| --- | --- | --- |"]
    for branch in branches.values():
        parent = f"`{branch.parent}`" if branch.parent else "—"
        rows.append(f"| `{branch.name}` | {parent} | `{branch.scope}` |")
    return "\n".join(rows)


def suite_table(suites) -> str:
    rows = ["| Suite | Layer | Run individually |", "| --- | --- | --- |"]
    for suite in suites:
        rows.append(f"| `{suite.name}` | `{suite.layer}` | `python3 tests/run-project-tests.py --suite {suite.name}` |")
    return "\n".join(rows)


def shared_suites(runner):
    """Shared documentation must propagate unchanged across platform branches."""
    product_names = {suite.name for suite in runner.PLATFORM_SUITES}
    return tuple(suite for suite in runner.SUITES if suite.name not in product_names)


def replace_block(text: str, name: str, contents: str) -> str:
    start = f"<!-- generated:{name}:start -->"
    end = f"<!-- generated:{name}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"{name}: expected exactly one generated start/end marker pair")
    before, remainder = text.split(start)
    if end not in remainder:
        raise ValueError(f"{name}: generated block markers are reversed")
    _, after = remainder.split(end)
    return before + start + "\n" + contents + "\n" + end + after


def topology_errors(root: Path, branches) -> list[str]:
    """Validate repeated machine contracts without automatically changing them."""
    errors = []
    expected = set(branches)
    cleanup = read_json(root / ".github/branch-cleanup.json")
    actual = cleanup["permanent_branches"]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        errors.append(".github/branch-cleanup.json: permanent branches differ from branch-policy.json")
    ruleset = read_json(root / ".github/rulesets/permanent-branches.json")
    refs = ruleset["conditions"]["ref_name"]
    if (len(refs["include"]) != len(set(refs["include"]))
            or set(refs["include"]) != {f"refs/heads/{name}" for name in expected} or refs["exclude"]):
        errors.append(".github/rulesets/permanent-branches.json: protected branch set differs from branch-policy.json")
    reuse = read_json(root / ".github/sync-test-reuse.json")
    edges = {name: (branch.parent, branch.scope) for name, branch in branches.items() if branch.parent}
    actual_edges = {name: (entry["parent"], entry["scope"]) for name, entry in reuse["edges"].items()}
    if actual_edges != edges:
        errors.append(".github/sync-test-reuse.json: synchronization edges/scopes differ from branch-policy.json")
    parents = {branch.parent for branch in branches.values() if branch.parent}
    if len(reuse["parents"]) != len(set(reuse["parents"])) or set(reuse["parents"]) != parents:
        errors.append(".github/sync-test-reuse.json: qualified parents differ from branch-policy.json")
    return errors


def check(root: Path = ROOT, write: bool = False) -> list[str]:
    root = root.resolve()
    read_json(root / ".github/branch-policy.json")
    policy = load_module("repository_display_branch_policy", root / "tools/branch-policy/check.py")
    branches = policy.load_policy(root / ".github/branch-policy.json")
    runner = load_module("repository_display_project_runner", root / "tests/run-project-tests.py")
    suite_names = [suite.name for suite in runner.SUITES]
    if len(set(suite_names)) != len(suite_names):
        raise ValueError("project test runner contains duplicate suite names")
    errors = topology_errors(root, branches)
    displays = {"branch-table": branch_table(branches), "test-suites": suite_table(shared_suites(runner))}
    pending = []
    for name, relative in TARGETS.items():
        path = display_path(root, relative)
        text = path.read_text(encoding="utf-8")
        replacement = replace_block(text, name, displays[name])
        if text != replacement:
            if write:
                pending.append((path, replacement))
            else:
                errors.append(f"{relative}: generated {name} display is stale; run python3 tools/repository-policy/check.py --write")
    # Fail before writing if the executable sources themselves disagree.
    if not errors:
        for path, replacement in pending:
            path.write_text(replacement, encoding="utf-8")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate only marked local documentation blocks")
    args = parser.parse_args()
    try:
        errors = check(write=args.write)
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors = [str(error)]
    if errors:
        print("Repository policy consistency failed:\n- " + "\n- ".join(errors))
        return 1
    print("Repository policy consistency passed (branch topology and generated documentation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
