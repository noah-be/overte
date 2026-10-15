#!/usr/bin/env python3
"""Dormant exact-candidate Android orchestration; no artifact authority or builds.

The CLI always uses trusted default-branch policy. Activation remains blocked
until the separately reviewed advisory/profile and extended-tier handoffs land.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/android-orchestration.json"
CALLERS = ("tools/repository-checks/workflows/android/repository-checks.yml",
           "tools/repository-checks/workflows/android/repository-checks-direct-browser.yml")
CALLEE = "tools/repository-checks/workflows/android-required.yml"
WORKFLOW = ".github/workflows/android-required.yml"
REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
INDEPENDENT_ROOTS = (
    "browser-client/", "browser-direct-client/", "tools/branch-policy/", "tools/issue-intake/",
    "tools/repository-health/", "tools/repository-maintenance/", "tools/workflow-security/",
)
BLOCKERS = {"extended-tier-prerequisite-transfer", "advisory-profile-owner-handoff"}
# No policy marker can authorize the still-unimplemented ownership transition.
ACTIVATION_READY = False


def _module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def android():
    return _module("required_android_owner", "tools/repository-checks/android.py")


def packages():
    return _module("android_package_generations", "tools/repository-checks/package_checks.py")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def _blob(data):
    return {"mode": "100644", "type": "blob", "sha": hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


def load_policy(policy_root=ROOT):
    owner = android()
    value = owner._json(owner._file(Path(policy_root), POLICY))
    fields = {"schema", "repository", "repository_id", "required_branches", "activation_blockers",
              "independent_roots", "reviewed_sources", "workflow_generations"}
    if not isinstance(value, dict) or set(value) != fields or type(value["schema"]) is not int \
            or value["schema"] != 1 or value["repository"] != REPOSITORY \
            or type(value["repository_id"]) is not int or value["repository_id"] != REPOSITORY_ID \
            or value["independent_roots"] != list(INDEPENDENT_ROOTS):
        raise ValueError("invalid trusted Android orchestration policy")
    branches = set(owner.load_policy(policy_root)["branches"])
    targets, blockers = value["required_branches"], value["activation_blockers"]
    if not isinstance(targets, list) or any(name not in branches for name in targets) \
            or len(set(targets)) != len(targets) or not isinstance(blockers, list) \
            or any(name not in BLOCKERS for name in blockers) or len(set(blockers)) != len(blockers):
        raise ValueError("invalid Android activation settings")
    if set(value["reviewed_sources"]) != branches:
        raise ValueError("incomplete Android reader review")
    for review in value["reviewed_sources"].values():
        if not isinstance(review, dict) or set(review) != {"commit", "tree", "readers", "entries"} \
                or any(not isinstance(review[key], str) or not re.fullmatch(r"[0-9a-f]{40}", review[key])
                       for key in ("commit", "tree")) \
                or not isinstance(review["readers"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", review["readers"]) \
                or type(review["entries"]) is not int or review["entries"] <= 0:
            raise ValueError("invalid Android reader anchor")
    generations = value["workflow_generations"]
    if not isinstance(generations, list) or not 1 <= len(generations) <= 8:
        raise ValueError("invalid Android workflow-generation inventory")
    seen, identities = set(), set()
    for item in generations:
        if not isinstance(item, dict) or set(item) != {"name", "caller", "callee"} \
                or item["caller"] not in CALLERS or item["callee"] != CALLEE \
                or not isinstance(item["name"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", item["name"]) \
                or item["name"] in seen:
            raise ValueError("invalid Android workflow-generation declaration")
        identity = (item["caller"], item["callee"])
        if identity in identities:
            raise ValueError("duplicate Android workflow-generation tuple")
        identities.add(identity)
        seen.add(item["name"])
    return value


def _sources(candidate, commit=None):
    owner = android()
    shared, _ = owner._shared()
    actual, tree = shared.checkout_identity(Path(candidate).resolve(strict=True))
    source = owner._GitSources(Path(candidate), actual, tree, shared)
    if commit is not None and commit != actual:
        tree = source._git("rev-parse", "--verify", commit + "^{tree}").decode().strip()
        source = owner._GitSources(Path(candidate), commit, tree, shared)
    return source


def reader_identity(entries):
    """Bind every reader and its negative inventory outside reviewed exclusions."""
    return digest([[path, item["mode"], item["type"], item["sha"]]
                   for path, item in sorted(entries.items())
                   if not path.startswith(INDEPENDENT_ROOTS)])


def _policy_identity(policy_root):
    owner = android()
    names = [POLICY, ".github/android-checks.json", ".github/package-workflow-generations.json",
             ".github/branch-policy.json",
             "tools/repository-checks/android_gate.py", "tools/repository-checks/check.py",
             "tools/repository-checks/package_checks.py",
             CALLEE, *CALLERS, *owner.EXECUTION_FILES]
    def content(name):
        if Path(policy_root).resolve() == ROOT.resolve():
            return packages()._trusted_bytes(name, git_fallback=True)
        return owner._file(Path(policy_root), name).read_bytes()
    return digest({name: hashlib.sha256(content(name)).hexdigest() for name in sorted(set(names))})


def _context(candidate, event, sha, event_name, policy):
    if not isinstance(event, dict) or event.get("repository", {}).get("full_name") != REPOSITORY \
            or type(event["repository"].get("id")) is not int or event["repository"]["id"] != REPOSITORY_ID \
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Android event repository or candidate mismatch")
    current = _sources(candidate)
    actual = current._git("rev-parse", "HEAD").decode().strip()
    if sha != actual:
        raise ValueError("Android checkout is not the exact event candidate")
    pr = event.get("pull_request")
    if event_name == "pull_request" and isinstance(pr, dict):
        base, head = pr.get("base", {}), pr.get("head", {})
        repo = base.get("repo", {})
        if repo.get("full_name") != REPOSITORY or type(repo.get("id")) is not int or repo["id"] != REPOSITORY_ID \
                or not isinstance(base.get("ref"), str) or not base["ref"] \
                or any(not isinstance(item.get("sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", item["sha"])
                       for item in (base, head)):
            raise ValueError("invalid Android pull request source identity")
        parents = current._git("show", "--no-patch", "--format=%P", sha).decode().split()
        if parents != [base["sha"], head["sha"]]:
            raise ValueError("Android candidate does not merge the exact event parents")
        return current, _sources(candidate, base["sha"]), base["ref"], base["sha"], head["sha"]
    if event_name != "workflow_dispatch" or pr is not None:
        raise ValueError("unsupported Android orchestration event")
    ref = event.get("ref", "")
    if not isinstance(ref, str) or not ref:
        raise ValueError("manual Android validation requires the exact target branch")
    return current, None, ref.removeprefix("refs/heads/"), "", sha


def candidate_plan(candidate, event, sha, *, event_name="pull_request", policy_root=ROOT):
    """No caller-supplied branch, views, omitted cases or parent-name waivers."""
    policy = load_policy(policy_root)
    source, before, branch, base, head = _context(candidate, event, sha, event_name, policy)
    branches = android()._json(android()._file(Path(policy_root), ".github/branch-policy.json"))["branches"]
    if branch not in branches:
        raise ValueError("Android event target is not a reviewed permanent branch")
    paths = sorted(path for path in set(source.entries) | set(before.entries if before else {})
                   if before is None or source.entries.get(path) != before.entries.get(path))
    known = branch in policy["reviewed_sources"]
    selected, reason = False, "outside-Android-target"
    if known:
        selected, reason = True, "conservative-complete-union"
        if before is not None and not paths:
            selected, reason = False, "verified-empty-tree-delta"
        elif before is not None and all(path.startswith(INDEPENDENT_ROOTS) for path in paths):
            regular = all(item is None or item["mode"] in {"100644", "100755"} and item["type"] == "blob"
                          for path in paths for item in (before.entries.get(path), source.entries.get(path)))
            anchor = policy["reviewed_sources"][branch]["readers"]
            if regular and reader_identity(before.entries) == anchor == reader_identity(source.entries):
                selected, reason = False, "reviewed-independent-inputs"
    views = list(android().VIEWS if event_name == "pull_request" else android().DEFAULT_VIEWS) if selected else []
    owner_plan = android().plan(candidate, branch, views=views, policy_root=policy_root) if known else None
    inventory = {name: {"command": item["command"], "variant": item["variant"], "cases": item["cases"]}
                 for name, item in (owner_plan["executions"].items() if owner_plan else [])}
    result = {"schema": 1, "repository": REPOSITORY, "repository_id": REPOSITORY_ID,
              "candidate": sha, "tree": source._git("rev-parse", sha + "^{tree}").decode().strip(),
              "base": base, "head": head, "target": branch, "event": event_name,
              "required": selected, "reason": reason, "paths": paths, "views": views,
              "owner_plan": owner_plan["plan"] if owner_plan else None, "inventory": digest(inventory),
              "policy": _policy_identity(policy_root)}
    result["plan"] = digest(result)
    return result


def outputs(plan):
    return {"android_required": str(plan["required"]).lower(), "android_candidate": plan["candidate"],
            "android_plan": plan["plan"], "android_inventory": plan["inventory"]}


def receipt(plan):
    return {"verified": "true", "candidate": plan["candidate"], "plan": plan["plan"],
            "inventory": plan["inventory"]}


def validate_tree_wiring(tree, *, policy_root=ROOT):
    """Require one complete approved package tuple plus its exact Android callee."""
    policy = load_policy(policy_root)
    generation = packages().validate_tree_wiring(tree)
    caller, callee = tree.get(".github/workflows/repository-checks.yml"), tree.get(WORKFLOW)
    for approved in policy["workflow_generations"]:
        def expected(relative):
            return _blob(android()._file(Path(policy_root), relative).read_bytes())
        if caller == expected(approved["caller"]) and callee == expected(approved["callee"]):
            return generation
    raise ValueError("Android caller/callee differ from a complete trusted generation")


def has_staged_caller(candidate, *, policy_root=ROOT):
    tree = _sources(candidate).entries
    caller = tree.get(".github/workflows/repository-checks.yml")
    return any(caller == _blob(android()._file(Path(policy_root), path).read_bytes()) for path in CALLERS)


def activated(event, *, policy_root=ROOT):
    policy = load_policy(policy_root)
    targets = policy["required_branches"]
    if not targets:
        return False
    branch = ((event.get("pull_request") or {}).get("base") or {}).get("ref")
    return branch in targets or event.get("pull_request") is None


def admit(candidate, event, *, policy_root=ROOT):
    validate_tree_wiring(_sources(candidate).entries, policy_root=policy_root)
    policy = load_policy(policy_root)
    if policy["activation_blockers"]:
        raise ValueError("Android activation blocked: " + ", ".join(policy["activation_blockers"]))
    if not ACTIVATION_READY:
        raise ValueError("Android activation blocked: complete ownership handoff is not implemented")
    if not activated(event, policy_root=policy_root):
        raise ValueError("Android required workflow is not activated for this target")


def verify_inner(needs, expected):
    if not isinstance(needs, dict) or set(needs) != {"route", "execute"} \
            or needs["route"].get("result") != "success" or needs["route"].get("outputs") != outputs(expected):
        raise ValueError("Android inner routing/candidate/inventory mismatch")
    verify_outer(needs["execute"], expected)
    return receipt(expected)


def verify_outer(job, expected):
    # The outer caller skips the reusable workflow for an empty union. Its
    # independently recomputed route proves that no Android setup was needed.
    conclusion = "success" if expected["required"] else "skipped"
    if not isinstance(job, dict) or job.get("result") != conclusion:
        raise ValueError("selected Android owner failed, was missing or skipped")
    if expected["required"] and job.get("outputs") != receipt(expected):
        raise ValueError("Android execution receipt candidate/plan/inventory mismatch")
    if not expected["required"] and any(job.get("outputs", {}).values()):
        raise ValueError("unexpected receipt for an unselected Android owner")


def run(candidate, event, sha, *, event_name, policy_root=ROOT, receipt_path, reports,
        expected_outputs, run_command=None, capture=None):
    admit(candidate, event, policy_root=policy_root)
    expected = candidate_plan(candidate, event, sha, event_name=event_name, policy_root=policy_root)
    if outputs(expected) != expected_outputs or not expected["required"]:
        raise ValueError("Android execution caller differs from independently selected union")
    owner = android()
    code, proof = owner.execute(candidate, expected["target"], views=expected["views"], policy_root=policy_root,
                                receipt_path=receipt_path, reports=reports, run_command=run_command, capture=capture)
    if code:
        raise ValueError("selected Android execution failed")
    # Same trusted process consumes its own execution result; no raw artifact or
    # candidate-controlled JSON can manufacture final-job authority here.
    actual = owner._capture_effective(capture) if capture is not None else None
    owner.verify(candidate, expected["target"], proof, views=expected["views"], policy_root=policy_root, environment=actual)
    if candidate_plan(candidate, event, sha, event_name=event_name, policy_root=policy_root) != expected:
        raise ValueError("Android candidate or source plan changed during execution")
    return receipt(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "verify"))
    parser.add_argument("--event", type=Path, default=os.environ.get("GITHUB_EVENT_PATH"), required=False)
    parser.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA"), required=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-json")
    parser.add_argument("--needs-json")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--reports", type=Path)
    args = parser.parse_args()
    try:
        if args.event is None:
            raise ValueError("Android orchestration requires a trusted event")
        event = json.loads(args.event.read_text())
        admit(args.candidate, event)
        expected = candidate_plan(args.candidate, event, args.sha, event_name=args.event_name)
        if args.action == "plan":
            result = outputs(expected)
            if args.expected_json is not None and json.loads(args.expected_json) != result:
                raise ValueError("Android caller differs from exact candidate plan")
        elif args.action == "run":
            if args.receipt is None or args.reports is None or args.expected_json is None:
                raise ValueError("Android run requires fresh external proof/report paths and exact caller outputs")
            result = run(args.candidate, event, args.sha, event_name=args.event_name,
                         receipt_path=args.receipt, reports=args.reports, expected_outputs=json.loads(args.expected_json))
        else:
            result = verify_inner(json.loads(args.needs_json), expected)
        with args.output.open("a") as output:
            output.write("".join(f"{key}={value}\n" for key, value in result.items()))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Android orchestration failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
