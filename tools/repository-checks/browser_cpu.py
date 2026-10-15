#!/usr/bin/env python3
"""Dormant trusted Browser CPU-history routing and independent final validation.

No active workflow or required gate calls this helper yet. Candidate files are
Git data only. A future caller must use this default-branch controller and the
exact canonical template, then authenticate the final handoff independently.
The JSON/needs arguments alone are not authentication or reusable test proof.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/browser-client.yml"
TEMPLATE = "tools/repository-checks/workflows/browser-client.yml"
REPOSITORY = {"full_name": "noah-l-frank/overte", "id": 1319052603}
REVIEWED_REVISION = "2750afb6416a4dc71366974f24c8e3e87e5228af"
REVIEWED_WORKFLOW = "db09fbf3858e022d1f6f50eda61ecb657666cbe5"
REVIEWED_BOUNDARY = "sha256:4f942162be837be489d841066fd14c7821b01b345a615bec948897a3a477a70f"
CPU_PATHS = frozenset("browser-client/" + path for path in (
    "tests/integration/capture-startup-integration-source-fixture.mjs",
    "tests/tablet-capture-startup-integration-manifest.test.mjs",
    "tests/integration/prepare-tablet-capture-acceptance.mjs",
    "tests/integration/capture-fork-rename-source-fixture.mjs",
    "tests/fixtures/capture-v33-fork-rename-before.json.gz",
    "tests/fixtures/capture-fork-rename-v34-complete-source-manifest.json",
    "tests/tablet-capture-fork-rename-manifest.test.mjs",
    # Reserved exact V35 migration inputs; no arbitrary history directory rule.
    "tests/integration/capture-workflow-source-fixture.mjs",
    "tests/fixtures/capture-v34-workflow-before.json.gz",
    "tests/fixtures/capture-workflow-v35-complete-source-manifest.json",
    "tests/tablet-capture-workflow-manifest.test.mjs",
    "tests/embedded-world-software-ci.test.mjs",
))
INDEPENDENT_POLICY_PATHS = frozenset({
    "tools/repository-checks/browser_cpu.py", TEMPLATE, "tests/browser-cpu-selection-test.py",
    ".github/test-suites.json", "tests/run-project-tests.py", "tests/PROJECT_TESTING.md",
    "docs/BROWSER_CPU_SELECTION.md", "docs/README.md",
})
PACKAGE_PATHS = frozenset({"browser-client/package.json", "browser-client/package-lock.json"})
JOBS = {"route", "cpu", "browser", "native-journey"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
_DOMAIN = "overte-browser-cpu-history-selection-v1"
_SPEC = importlib.util.spec_from_file_location("trusted_browser_cpu_inventory", ROOT / "tools/test-evidence/inputs.py")
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("trusted Git inventory validator unavailable")
inputs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(inputs)


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return "sha256:" + hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":"),
                                                 allow_nan=False) + "\n").encode()).hexdigest()


def git(repository, *args):
    return subprocess.run(["git", "--no-replace-objects", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
                          cwd=repository, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout


def snapshot(repository, revision):
    """Read a complete exact commit with replacement refs disabled and no hooks."""
    require(isinstance(revision, str) and SHA.fullmatch(revision), "exact candidate commit SHA required")
    require(git(repository, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
            == revision, "candidate must identify a commit directly")
    tree = git(repository, "rev-parse", "--verify", "--end-of-options", revision + "^{tree}").decode().strip()
    require(SHA.fullmatch(tree), "invalid candidate root tree")
    raw = git(repository, "ls-tree", "-rz", "--full-tree", tree)
    require(raw.endswith(b"\0") or not raw, "incomplete immutable Git inventory")
    entries = {}
    for record in raw.split(b"\0")[:-1]:
        metadata, encoded_path = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split(" ")
        path = encoded_path.decode("utf-8", errors="strict")
        require(path not in entries and SHA.fullmatch(oid), "invalid or duplicate Git entry")
        entries[path] = {"mode": mode, "type": kind, "sha": oid}
    inputs._validate_tree(entries)
    return {"revision": revision, "tree": tree, "entries": entries}


def canonical_workflow(policy_root=ROOT):
    path = policy_root / TEMPLATE
    require(path.is_file() and not any(parent.is_symlink() for parent in (path, path.parent, path.parent.parent)),
            "trusted canonical browser workflow unavailable")
    return path.read_bytes()


def _blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _boundary(current, policy_root=ROOT):
    approved = {REVIEWED_WORKFLOW, _blob(canonical_workflow(policy_root))}
    selected = []
    for path, entry in sorted(current["entries"].items()):
        expected = "100755" if path == "tests/run-project-tests.py" else "100644"
        if (path in CPU_PATHS or path in INDEPENDENT_POLICY_PATHS) and entry["mode"] == expected:
            continue
        value = {"path": path, **entry}
        # Only the exact trusted template may replace the exact reviewed legacy
        # workflow. Unknown candidate workflow bytes are never normalized away.
        if path == WORKFLOW and entry["mode"] == "100644" and entry["type"] == "blob" and entry["sha"] in approved:
            value["sha"] = REVIEWED_WORKFLOW
        selected.append(value)
    return digest({"domain": _DOMAIN + "-reader-boundary", "entries": selected})


def review_boundary(repository, revision, *, policy_root=ROOT):
    """Return a review proposal; callers must never auto-approve a new reader."""
    current = snapshot(repository, revision)
    return {"revision": revision, "tree": current["tree"], "boundary": _boundary(current, policy_root)}


def _policy(policy_root):
    return digest({"domain": _DOMAIN, "reviewed_revision": REVIEWED_REVISION,
                   "reviewed_boundary": REVIEWED_BOUNDARY, "cpu_paths": sorted(CPU_PATHS),
                   "independent_policy_paths": sorted(INDEPENDENT_POLICY_PATHS),
                   "legacy_workflow": REVIEWED_WORKFLOW, "canonical_workflow": _blob(canonical_workflow(policy_root)),
                   "controller": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "inventory": hashlib.sha256((ROOT / "tools/test-evidence/inputs.py").read_bytes()).hexdigest()})


def classify(previous, current, *, policy_root=ROOT):
    """Pure classification requires two complete authenticated snapshot maps."""
    for value in (previous, current):
        inputs._validate_tree(value["entries"])
    old, new = previous["entries"], current["entries"]
    changes = [{"path": path, "old": old.get(path), "new": new.get(path)}
               for path in sorted(old.keys() | new.keys()) if old.get(path) != new.get(path)]
    paths = {item["path"] for item in changes}
    regular = all(entry["mode"] in {"100644", "100755"} for tree in (old, new) for entry in tree.values())
    cpu_modes = all(entry is None or entry["mode"] == "100644"
                    for item in changes if item["path"] in CPU_PATHS for entry in (item["old"], item["new"]))
    boundary = [_boundary(value, policy_root) for value in (previous, current)]
    bootstrap = (WORKFLOW in paths and bool(paths & CPU_PATHS) and paths <= CPU_PATHS | {WORKFLOW}
                 and old.get(WORKFLOW) == {"mode": "100644", "type": "blob", "sha": REVIEWED_WORKFLOW}
                 and new.get(WORKFLOW) == {"mode": "100644", "type": "blob",
                                          "sha": _blob(canonical_workflow(policy_root))})
    if not changes:
        reason = "empty-inventory-requires-full"
    elif not regular or not cpu_modes:
        reason = "nonregular-mode-or-alias-requires-full"
    elif boundary != [REVIEWED_BOUNDARY, REVIEWED_BOUNDARY]:
        reason = "reader-boundary-not-reviewed"
    elif paths <= CPU_PATHS or bootstrap:
        reason = "approved-workflow-bootstrap-and-cpu-history" if bootstrap else "cpu-history-only"
    else:
        reason = "other-or-mixed-inputs-require-full"
    return {"mode": "cpu" if reason in {"cpu-history-only", "approved-workflow-bootstrap-and-cpu-history"} else "full",
            "audit": bool(paths & PACKAGE_PATHS), "reason": reason, "changes": changes,
            "base_boundary": boundary[0], "candidate_boundary": boundary[1]}


def validate_wiring(current, *, policy_root=ROOT):
    require(current["entries"].get(WORKFLOW) == {"mode": "100644", "type": "blob",
                                                "sha": _blob(canonical_workflow(policy_root))},
            "browser workflow differs from trusted canonical orchestration")


def route(event, event_name, candidate, expected_sha, *, policy_root=ROOT):
    require(isinstance(event, dict) and all(event.get("repository", {}).get(k) == v for k, v in REPOSITORY.items()),
            "foreign browser repository")
    require(git(candidate, "rev-parse", "HEAD").decode().strip() == expected_sha, "wrong candidate checkout")
    current = snapshot(candidate, expected_sha)
    validate_wiring(current, policy_root=policy_root)
    if event_name == "pull_request":
        pr = event["pull_request"]
        require(all(pr.get("base", {}).get("repo", {}).get(k) == v for k, v in REPOSITORY.items()),
                "foreign PR base")
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        require(isinstance(base, str) and SHA.fullmatch(base) and isinstance(head, str) and SHA.fullmatch(head),
                "invalid PR revisions")
        require(git(candidate, "show", "-s", "--format=%P", expected_sha).decode().split() == [base, head],
                "candidate does not merge exact event base and head")
        selection = classify(snapshot(candidate, base), current, policy_root=policy_root)
    else:
        require(event_name == "workflow_dispatch" and "pull_request" not in event, "unsupported browser event")
        base, head = "", expected_sha
        selection = {"mode": "full", "audit": True, "reason": "manual-full-verification"}
    binding = {"candidate": expected_sha, "tree": current["tree"], "base": base, "head": head,
               "mode": selection["mode"], "audit": str(selection["audit"]).lower()}
    return {**binding, "plan": digest({"policy": _policy(policy_root), "event_name": event_name,
                                       "binding": binding, "selection": selection})}


def verify(event, event_name, candidate, expected_sha, needs, *, policy_root=ROOT):
    """Use actual same-run needs from the approved template, never candidate JSON."""
    expected = route(event, event_name, candidate, expected_sha, policy_root=policy_root)
    require(isinstance(needs, dict) and set(needs) == JOBS, "missing or unexpected browser jobs")
    require(needs["route"].get("result") == "success" and needs["route"].get("outputs") == expected,
            "route failed or differs from independent exact candidate plan")
    for name in JOBS - {"route"}:
        selected = (name == "cpu") == (expected["mode"] == "cpu")
        require(needs[name].get("result") == ("success" if selected else "skipped"),
                "missing, failed or unexpectedly executed browser job: " + name)
    # Manual startup diagnostics intentionally do not prove full journeys. They
    # cannot satisfy the future independently required pull-request handoff.
    diagnostic = event_name == "workflow_dispatch" and event.get("inputs", {}).get("startup_diagnostics") in (True, "true")
    return {"candidate": expected_sha, "plan": expected["plan"], "verified": "diagnostic-only" if diagnostic else "true"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("route", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--event", type=Path, required=True)
        command.add_argument("--event-name", required=True)
        command.add_argument("--candidate", type=Path, required=True)
        command.add_argument("--sha", required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "verify":
            command.add_argument("--needs", type=Path, required=True)
    command = commands.add_parser("workflow")
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "workflow":
            require(args.output.resolve() != (ROOT / WORKFLOW).resolve(), "active workflow activation is a separate change")
            args.output.write_bytes(canonical_workflow())
        else:
            event = json.loads(args.event.read_text())
            value = route(event, args.event_name, args.candidate, args.sha) if args.command == "route" else verify(
                event, args.event_name, args.candidate, args.sha, json.loads(args.needs.read_text()))
            with args.output.open("a") as handle:
                handle.write("".join(f"{key}={value}\n" for key, value in value.items()))
            print(json.dumps(value, sort_keys=True))
        return 0
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print("Browser selection failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
