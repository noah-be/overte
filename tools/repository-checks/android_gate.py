#!/usr/bin/env python3
"""Dormant exact-candidate Android orchestration; no artifact authority or builds.

The CLI always uses trusted default-branch policy. Activation remains blocked
until the complete prospective generation receives separate hosted qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/android-orchestration.json"
CALLERS = ("tools/repository-checks/workflows/android/repository-checks.yml",
           "tools/repository-checks/workflows/android/repository-checks-direct-browser.yml")
CALLEE = "tools/repository-checks/workflows/android-required.yml"
OWNED = "tools/repository-checks/workflows/android-owned"
OWNED_PROJECTS = {
    OWNED + "/repository-checks.yml": OWNED + "/project-tests.yml",
    "tools/repository-checks/workflows/producers/repository-checks.yml":
        "tools/repository-checks/workflows/producers/protected-project-tests.yml",
}
OWNED_CALLERS = tuple(OWNED_PROJECTS)
WORKFLOW = ".github/workflows/android-required.yml"
REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
INDEPENDENT_ROOTS = (
    "browser-client/", "browser-direct-client/", "tools/branch-policy/", "tools/issue-intake/",
    "tools/repository-health/", "tools/repository-maintenance/", "tools/workflow-security/",
)
FOREIGN_LOCKS = frozenset({"browser-client/package-lock.json",
                          "script-archive/marketplace/S3Server/package-lock.json"})
HERMETIC_METADATA_TEST = "android/phone/tests/phone-release-metadata-test.py"
HERMETIC_METADATA_BLOB = "8f0968ab4af834577b894971af09244cb9c82316"
BLOCKERS = {"extended-tier-prerequisite-transfer", "advisory-profile-owner-handoff",
            "prospective-generation-hosted-qualification"}
# No policy marker can authorize an unqualified ownership transition.
ACTIVATION_READY = False
# A reviewed current-source attempt capability, never historical qualification.
# Legacy admission/targets remain separate and unchanged.
SOURCE_CAPABILITY = True
SOURCE_GUARD_BLOB = '20580c3ea413e63a6779898fdd3d2c5e051625f4'
CURRENT_SOURCE_GENERATION = "protected-producer-original-default-v1"
CURRENT_SOURCE_TARGETS = frozenset({"android-main", "android-vr", "android-vr-pico", "android-phone"})
CURRENT_JOBS = {
    "android / route": "Independently select the complete Android union",
    "android / execute": "Execute and verify the independently selected Android owners once",
    "android / verify": "Recompute candidate union and require complete successful ownership",
}


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
              "independent_roots", "reviewed_sources", "reviewed_lock_sources",
              "workflow_generations", "handoff_manifest"}
    if not isinstance(value, dict) or set(value) != fields or type(value["schema"]) is not int \
            or value["schema"] != 1 or value["repository"] != REPOSITORY \
            or type(value["repository_id"]) is not int or value["repository_id"] != REPOSITORY_ID \
            or value["independent_roots"] != list(INDEPENDENT_ROOTS) \
            or value["handoff_manifest"] != ".github/android-owner-transfer.json":
        raise ValueError("invalid trusted Android orchestration policy")
    branches = set(owner.load_policy(policy_root)["branches"])
    targets, blockers = value["required_branches"], value["activation_blockers"]
    if not isinstance(targets, list) or any(name not in branches for name in targets) \
            or len(set(targets)) != len(targets) or not isinstance(blockers, list) \
            or any(name not in BLOCKERS for name in blockers) or len(set(blockers)) != len(blockers):
        raise ValueError("invalid Android activation settings")
    for field in ("reviewed_sources", "reviewed_lock_sources"):
        if not isinstance(value[field], dict) or set(value[field]) != branches:
            raise ValueError("incomplete Android reader review")
        for review in value[field].values():
            if not isinstance(review, dict) or set(review) != {"commit", "tree", "readers", "entries"} \
                    or any(not isinstance(review[key], str) or not re.fullmatch(r"[0-9a-f]{40}", review[key])
                           for key in ("commit", "tree")) \
                    or not isinstance(review["readers"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", review["readers"]) \
                    or type(review["entries"]) is not int or review["entries"] < (1 if field == "reviewed_sources" else 0):
                raise ValueError("invalid Android reader anchor")
    generations = value["workflow_generations"]
    if not isinstance(generations, list) or not 1 <= len(generations) <= 8:
        raise ValueError("invalid Android workflow-generation inventory")
    seen, identities = set(), set()
    for item in generations:
        ordinary = isinstance(item, dict) and set(item) == {"name", "caller", "callee"} \
            and item["caller"] in CALLERS and item["callee"] == CALLEE
        owned = isinstance(item, dict) and set(item) == {"name", "caller", "callee", "project", "browser"} \
            and item["caller"] in OWNED_CALLERS and item["callee"] == OWNED + "/android-required.yml" \
            and item["project"] == OWNED_PROJECTS[item["caller"]] \
            and item["browser"] == "tools/repository-checks/workflows/npm-consumers/browser-client.yml"
        if not (ordinary or owned) or not isinstance(item["name"], str) \
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", item["name"]) or item["name"] in seen:
            raise ValueError("invalid Android workflow-generation declaration")
        identity = canonical({key: value for key, value in item.items() if key != "name"})
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


def lock_reader_identity(entries):
    """Bind the full consumer inventory; only two lock payloads are independent.

    The exact owner policy retains its path, type and mode. Its contents are
    separately bound by _policy_identity; including its anchor bytes here would
    make publishing a new anchor self-referential. This is not path admission.
    """
    if entries.get(POLICY, {}).get("mode") != "100644" or entries.get(POLICY, {}).get("type") != "blob":
        raise ValueError("Android lock review requires a regular owner policy")
    return digest([[path, item["mode"], item["type"],
                    "separately-bound-owner-policy" if path == POLICY else item["sha"]]
                   for path, item in sorted(entries.items()) if path not in FOREIGN_LOCKS])


def _reviewed_lock_delta(candidate, event, sha, source, before, paths, anchor, *, event_name, base, head):
    """A fresh mandatory package plan can own only the reviewed lock-only delta."""
    if event_name != "pull_request" or not paths or not set(paths).issubset(FOREIGN_LOCKS) \
            or anchor["entries"] <= 0:
        return None
    labels = event["pull_request"].get("labels", [])
    if not isinstance(labels, list) or any(not isinstance(label, dict) or
            not isinstance(label.get("name"), str) for label in labels) \
            or any(label["name"] == "android-long-diagnostics" for label in labels):
        return None
    for tree in (before, source):
        if tree.entries.get(HERMETIC_METADATA_TEST) != {
                "mode": "100755", "type": "blob", "sha": HERMETIC_METADATA_BLOB}:
            return None
        if any(tree.entries.get(path, {}).get("mode") != "100644" or
               tree.entries.get(path, {}).get("type") != "blob" for path in FOREIGN_LOCKS):
            return None
        if len(tree.entries) - len(FOREIGN_LOCKS) != anchor["entries"]:
            return None
        try:
            if lock_reader_identity(tree.entries) != anchor["readers"]:
                return None
        except ValueError:
            return None
    try:
        package_policy = packages()
        package_policy.validate_tree_wiring(before.entries)
        package_policy.validate_tree_wiring(source.entries)
        package_plan = package_policy.candidate_plan(candidate, event, sha)
        if not isinstance(package_plan, dict) or package_plan.get("candidate") != sha or package_plan.get("base") != base \
                or package_plan.get("head") != head or package_plan.get("paths") != paths \
                or package_plan.get("regular") is not True or package_plan.get("unknown") is not False \
                or package_plan.get("tree") != source._git("rev-parse", sha + "^{tree}").decode().strip():
            return None
        selection = _module("android_lock_package_ownership", "tools/repository-checks/host_selection.py")
        if not set(paths).issubset(selection.package_owned_paths(package_plan)):
            return None
        return package_plan["plan"]
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        return None


def _policy_identity(policy_root):
    owner = android()
    names = [POLICY, ".github/android-checks.json", ".github/package-workflow-generations.json",
             ".github/branch-policy.json",
             "tools/repository-checks/android_gate.py", "tools/repository-checks/check.py",
             "tools/repository-checks/package_checks.py",
             "tools/repository-checks/host_selection.py",
             CALLEE, *CALLERS, *OWNED_CALLERS, *OWNED_PROJECTS.values(), OWNED + "/android-required.yml",
             "tools/repository-checks/android_handoff.py", ".github/android-owner-transfer.json", *owner.EXECUTION_FILES]
    transfer = handoff().policy(policy_root)
    names += [item["source"] for group in ("legacy_workflows", "source_contracts")
              for item in transfer[group].values()]
    def content(name):
        if Path(policy_root).resolve() == ROOT.resolve():
            return packages()._trusted_bytes(name, git_fallback=True)
        return owner._file(Path(policy_root), name).read_bytes()
    return digest({"android": {name: hashlib.sha256(content(name)).hexdigest() for name in sorted(set(names))},
                   "packages": packages()._policy_inputs()})


def _context(candidate, event, sha, event_name, policy, *, pr_context=None):
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
        checks = packages().load("android_candidate_context", "tools/repository-checks/check.py")
        resolved = checks.pr_candidate_context(candidate, event, sha, pr_context=pr_context)
        return current, _sources(candidate, resolved["base"]), base["ref"], resolved["base"], resolved["head"]
    if event_name != "workflow_dispatch" or pr is not None:
        raise ValueError("unsupported Android orchestration event")
    ref = event.get("ref", "")
    if not isinstance(ref, str) or not ref:
        raise ValueError("manual Android validation requires the exact target branch")
    return current, None, ref.removeprefix("refs/heads/"), "", sha


def event_views(event, event_name, selected):
    """The authenticated runner event alone selects optional long diagnostics."""
    if not selected:
        return []
    owner = android()
    if event_name == "pull_request":
        labels = event["pull_request"].get("labels", [])
        if not isinstance(labels, list) or any(not isinstance(label, dict) or
                not isinstance(label.get("name"), str) for label in labels):
            raise ValueError("invalid Android diagnostic label inventory")
        return list(owner.VIEWS) + (list(owner.DIAGNOSTIC_VIEWS[:3]) if
            any(label["name"] == "android-long-diagnostics" for label in labels) else [])
    inputs = event.get("inputs", {})
    regression_value = inputs.get("run_regression", True) if isinstance(inputs, dict) else None
    if not isinstance(inputs, dict) or not (type(regression_value) is bool or
            type(regression_value) is str and regression_value in {"true", "false"}):
        raise ValueError("invalid Android manual regression selection")
    regression = inputs.get("run_regression", True) in (True, "true")
    return list(owner.DEFAULT_VIEWS) + list(owner.DIAGNOSTIC_VIEWS[:3]) + (["regression"] if regression else [])


def validate_non_android_absence(source, before=None):
    """Bootstrap outside Android only when neither immutable tree owns it."""
    legacy = {".github/workflows/android-tests.yml", ".github/workflows/android-vr-tests.yml"}
    profile_path = "tests/platform-profile.json"
    for tree in (source, before):
        if tree is None:
            continue  # A manual event has no predecessor tree.
        if any(path == "android" or path.startswith("android/") or path in legacy for path in tree.entries):
            raise ValueError("unexpected Android ownership source on a non-Android target")
        entry = tree.entries.get(profile_path)
        if entry is None or entry["mode"] != "100644" or entry["type"] != "blob":
            raise ValueError("non-Android bootstrap requires a regular shared platform profile")
        profile = tree.json(profile_path)
        if not isinstance(profile, dict) or type(profile.get("schema")) is not int \
                or profile != {"schema": 1, "platform": "shared", "suites": []}:
            raise ValueError("unexpected Android or unreviewed platform profile on a non-Android target")


def candidate_plan(candidate, event, sha, *, event_name="pull_request", policy_root=ROOT, pr_context=None):
    """No caller-supplied branch, views, omitted cases or parent-name waivers."""
    policy = load_policy(policy_root)
    source, before, branch, base, head = _context(candidate, event, sha, event_name, policy, pr_context=pr_context)
    branches = android()._json(android()._file(Path(policy_root), ".github/branch-policy.json"))["branches"]
    if branch not in branches:
        raise ValueError("Android event target is not a reviewed permanent branch")
    paths = sorted(path for path in set(source.entries) | set(before.entries if before else {})
                   if before is None or source.entries.get(path) != before.entries.get(path))
    known = branch in policy["reviewed_sources"]
    selected, reason = False, "outside-Android-target"
    lock_package_plan = None
    if not known:
        validate_non_android_absence(source, before)
    else:
        selected, reason = True, "conservative-complete-union"
        if before is not None and not paths:
            selected, reason = False, "verified-empty-tree-delta"
        elif before is not None and set(paths).intersection(FOREIGN_LOCKS):
            # Unsupported lock changes must not fall through the older broad
            # Browser-root route, whose reader anchors are deliberately frozen.
            lock_package_plan = _reviewed_lock_delta(candidate, event, sha, source, before, paths,
                policy["reviewed_lock_sources"][branch], event_name=event_name, base=base, head=head)
            if lock_package_plan is not None:
                selected, reason = False, "reviewed-package-lock-inputs"
        elif before is not None and all(path.startswith(INDEPENDENT_ROOTS) for path in paths):
            regular = all(item is None or item["mode"] in {"100644", "100755"} and item["type"] == "blob"
                          for path in paths for item in (before.entries.get(path), source.entries.get(path)))
            anchor = policy["reviewed_sources"][branch]["readers"]
            if regular and reader_identity(before.entries) == anchor == reader_identity(source.entries):
                selected, reason = False, "reviewed-independent-inputs"
    views = event_views(event, event_name, selected)
    owner_plan = android().plan(candidate, branch, views=views, policy_root=policy_root) if known else None
    inventory = {name: {"command": item["command"], "variant": item["variant"], "cases": item["cases"]}
                 for name, item in (owner_plan["executions"].items() if owner_plan else [])}
    result = {"schema": 1, "repository": REPOSITORY, "repository_id": REPOSITORY_ID,
              "candidate": sha, "tree": source._git("rev-parse", sha + "^{tree}").decode().strip(),
              "base": base, "head": head, "target": branch, "event": event_name,
              "required": selected, "reason": reason, "paths": paths, "views": views,
              "owner_plan": owner_plan["plan"] if owner_plan else None, "inventory": digest(inventory),
              "lock_package_plan": lock_package_plan,
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
    if generation == CURRENT_SOURCE_GENERATION:
        if tree.get(WORKFLOW) != _blob(android()._file(Path(policy_root), OWNED + "/android-required.yml").read_bytes()):
            raise ValueError("current Android source callee is missing or noncanonical")
        return generation
    caller, callee = tree.get(".github/workflows/repository-checks.yml"), tree.get(WORKFLOW)
    for approved in policy["workflow_generations"]:
        if _generation_matches(tree, approved, policy_root):
            return generation
    raise ValueError("Android caller/callee differ from a complete trusted generation")


def _generation_matches(tree, approved, policy_root):
    paths = {"caller": ".github/workflows/repository-checks.yml", "callee": WORKFLOW,
             "project": ".github/workflows/project-tests.yml", "browser": ".github/workflows/browser-client.yml",
             "direct": ".github/workflows/browser-direct-client.yml"}
    return all(tree.get(paths[key]) == _blob(android()._file(Path(policy_root), relative).read_bytes())
               for key, relative in approved.items() if key != "name")


def has_staged_caller(candidate, *, policy_root=ROOT):
    tree = _sources(candidate).entries
    caller = tree.get(".github/workflows/repository-checks.yml")
    return any(caller == _blob(android()._file(Path(policy_root), path).read_bytes()) for path in CALLERS + OWNED_CALLERS)


def handoff():
    return _module("required_android_handoff", "tools/repository-checks/android_handoff.py")


def validate_owned_generation(candidate, branch, *, policy_root=ROOT, before_sha=None):
    sources = _sources(candidate)
    generation = validate_tree_wiring(sources.entries, policy_root=policy_root)
    approved = load_policy(policy_root)["workflow_generations"]
    if generation != CURRENT_SOURCE_GENERATION and not any("project" in item and _generation_matches(sources.entries, item, policy_root) for item in approved):
        raise ValueError("Android activation requires the complete sole-owner project generation")
    previous = None
    if before_sha is not None:
        if not isinstance(before_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", before_sha):
            raise ValueError("invalid Android predecessor identity")
        previous = _sources(candidate, before_sha)
    handoff().validate_sources(sources, branch, policy_root=policy_root, previous=previous)


def activated(event, *, policy_root=ROOT):
    policy = load_policy(policy_root)
    targets = policy["required_branches"]
    if not targets:
        return False
    branch = ((event.get("pull_request") or {}).get("base") or {}).get("ref") or event.get("ref", "").removeprefix("refs/heads/")
    return branch in targets


def _execution_target(candidate, event, *, policy_root=ROOT, pr_context=None):
    source = _sources(candidate)
    validate_tree_wiring(source.entries, policy_root=policy_root)
    policy = load_policy(policy_root)
    repository = event.get("repository", {})
    base = ((event.get("pull_request") or {}).get("base") or {})
    branch = base.get("ref") or event.get("ref", "").removeprefix("refs/heads/")
    branches = android()._json(android()._file(Path(policy_root), ".github/branch-policy.json"))["branches"]
    if repository.get("full_name") != REPOSITORY or repository.get("id") != REPOSITORY_ID \
            or branch not in branches or (base and any(base.get("repo", {}).get(key) != repository.get(key) for key in ("full_name", "id"))):
        raise ValueError("Android admission requires an exact reviewed event target")
    source, before, _, before_sha, _ = _context(candidate, event,
        source._git("rev-parse", "HEAD").decode().strip(),
        "pull_request" if "pull_request" in event else "workflow_dispatch", policy, pr_context=pr_context)
    if branch not in policy["reviewed_sources"]:
        validate_non_android_absence(source, before)
    # Preserve the raw event snapshot; owned-generation admission uses actual
    # immutable M.parent0 from the same independently recomputed context.
    return policy, branch, before_sha or None


def validate_execution_generation(candidate, event, *, policy_root=ROOT, pr_context=None):
    """Allow qualification of a complete prospective owner, never its merge.

    The required outer repository verifier separately calls admit(). Keeping
    activation there lets real candidate producers be qualified while protected
    branches retain the enforced old owner. A diagnostic is not merge authority.
    """
    policy, branch, base = _execution_target(candidate, event, policy_root=policy_root, pr_context=pr_context)
    if branch in policy["reviewed_sources"]:
        validate_owned_generation(candidate, branch, policy_root=policy_root, before_sha=base)


def admit(candidate, event, *, policy_root=ROOT):
    """Merge authority still requires the trusted completed activation policy."""
    policy, branch, base = _execution_target(candidate, event, policy_root=policy_root)
    if branch not in policy["reviewed_sources"]:
        return
    if policy["activation_blockers"]:
        raise ValueError("Android activation blocked: " + ", ".join(policy["activation_blockers"]))
    if not ACTIVATION_READY:
        raise ValueError("Android activation blocked: complete ownership handoff is not qualified")
    if not activated(event, policy_root=policy_root):
        raise ValueError("Android required workflow is not activated for this target")
    branch = ((event.get("pull_request") or {}).get("base") or {}).get("ref") or event.get("ref", "").removeprefix("refs/heads/")
    validate_owned_generation(candidate, branch, policy_root=policy_root, before_sha=base)




def _bootstrap_git(root,*arguments):
    environment={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1',
        'GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}
    result=subprocess.run(['/usr/bin/git','--no-replace-objects','-c','safe.directory='+str(root),
        '-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',*arguments],cwd=root,env=environment,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=True)
    if len(result.stdout)>1_000_000:raise ValueError('Android bootstrap Git response exceeds bound')
    return result.stdout


def _protected_default(policy_root, *, api=None):
    """Stdlib-only actualD/lookup admission BEFORE any API/execution import."""
    root=Path(policy_root).resolve(strict=True)
    relative='tools/test-evidence/source_admission.py';path=root
    for component in Path(relative).parts:
        path/=component
        if path.is_symlink():raise ValueError('Android stdlib guard has an aliased source')
    raw=_bootstrap_git(root,'show','HEAD:'+relative)
    if not path.is_file() or path.stat().st_size>128_000 or path.stat().st_mode&0o111 \
            or path.read_bytes()!=raw or _blob(raw)['sha']!=SOURCE_GUARD_BLOB:
        raise ValueError('Android stdlib guard has no reviewed bootstrap identity')
    search=list(sys.path);bytecode=sys.dont_write_bytecode;standard=Path(os.__file__).resolve().parent
    sys.path[:]=[str(standard),str(standard/'lib-dynload')]
    sys.dont_write_bytecode=True
    try:
        spec=importlib.util.spec_from_file_location('trusted_android_default_bootstrap',path)
        source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    finally:
        sys.path[:]=search
        sys.dont_write_bytecode=bytecode
    # api is private test transport only. The production entrypoint always
    # constructs the fixed-fork stdlib reader before importing producer_api.
    api=source.GitHubSource() if api is None else api
    repository=api.get('');reference=api.get('git/ref/heads/main');branch=api.get('branches/main')
    source.require(repository.get('full_name')==REPOSITORY and repository.get('id')==REPOSITORY_ID
        and repository.get('default_branch')=='main' and reference.get('ref')=='refs/heads/main'
        and reference.get('object',{}).get('type')=='commit','Android bootstrap default repository/ref differs')
    default=source.object_id(reference['object'].get('sha'))
    source.require(branch.get('name')=='main' and branch.get('protected') is True
        and branch.get('commit',{}).get('sha')==default,'Android bootstrap default protection differs')
    source.require(_bootstrap_git(root,'rev-parse','--verify','HEAD^{commit}').decode().strip()==default,
        'Android bootstrap actual checkout differs from protectedD')
    tree=source.api_tree(api,default)
    context=source.compatibility(tree,tree,'main',read_actual=lambda name:source.actual_bytes(root,name),
        actual_imports=source.actual_import_inventory(root))
    source.require(api.get('git/ref/heads/main')==reference and api.get('branches/main')==branch,
        'Android bootstrap protectedD changed')
    return {'default':default,'admission':context}


def _native_modules():
    directory=str(ROOT/'tools/test-evidence')
    search=list(sys.path);bytecode=sys.dont_write_bytecode;sys.dont_write_bytecode=True
    sys.path.insert(0,directory)  # Fixed protected directory, never candidate.
    try:
        import execution
        import inputs
        import producer_api
        import source_admission
        if any(Path(module.__file__).resolve()!=Path(directory)/(name+'.py')
               for name,module in (('execution',execution),('inputs',inputs),
                                   ('producer_api',producer_api),('source_admission',source_admission))):
            raise ValueError('current Android helper imported a foreign controller')
        return execution, inputs, producer_api, source_admission
    finally:
        sys.path[:]=search
        sys.dont_write_bytecode=bytecode



def _diagnostic_presence(labels):
    if type(labels) is not list or len(labels)>1000:
        raise ValueError('current Android label inventory is unavailable')
    names=[]
    for item in labels:
        if type(item) is not dict or type(item.get('name')) is not str or not 0<len(item['name'])<=100 \
                or any(ord(c)<32 or ord(c)==127 for c in item['name']) or item['name'] in names:
            raise ValueError('current Android label inventory is malformed')
        names.append(item['name'])
    return 'android-long-diagnostics' in names


def _current_metadata_policy(workflow):
    directory=ROOT/'tools/test-evidence'
    search=list(sys.path);bytecode=sys.dont_write_bytecode;sys.dont_write_bytecode=True
    sys.path.insert(0,str(directory))
    try:
        import producer_workflow
        if Path(producer_workflow.__file__).resolve()!=directory/'producer_workflow.py':
            raise ValueError('current Android metadata reader is foreign')
        _,_,A,_=_native_modules()
        workflows,sources=producer_workflow.metadata_generations(producer_workflow._host_policy())
        return A.MetadataPolicy(workflow,'.github/workflows/repository-checks.yml',workflows,sources)
    finally:
        sys.path[:]=search;sys.dont_write_bytecode=bytecode


def _current_source(candidate, event, sha, environment, adapter, policy_root):
    """Actual current B/H/M/defaultD; no candidate Python or old B is imported."""
    execution, inputs, A, source = _native_modules()
    expected = {'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':REPOSITORY,
        'GITHUB_REPOSITORY_ID':str(REPOSITORY_ID),'GITHUB_EVENT_NAME':'pull_request',
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'repository-checks','RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24'}
    A.require(all(environment.get(key)==value for key,value in expected.items()), 'current Android owner native context differs')
    ref=environment.get('GITHUB_REF','');match=re.fullmatch(r'refs/pull/([1-9][0-9]*)/merge',ref)
    A.require(match is not None and re.fullmatch('[1-9][0-9]*',environment.get('GITHUB_RUN_ID',''))
        and environment.get('GITHUB_SHA')==sha==environment.get('GITHUB_WORKFLOW_SHA')
        and environment.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/.github/workflows/repository-checks.yml@'+ref,
        'current Android workflow source differs')
    number=int(match[1]);binding,refs=adapter.current(number)
    live=adapter._object('pulls/'+str(number))
    repo={'full_name':REPOSITORY,'id':REPOSITORY_ID};pr=event.get('pull_request',{})
    A.require(event.get('repository',{}).get('full_name')==REPOSITORY
        and type(event.get('repository',{}).get('id')) is int and event['repository']['id']==REPOSITORY_ID
        and event.get('number')==pr.get('number')==number and binding['merge_sha']==sha
        and binding['base_ref'] in CURRENT_SOURCE_TARGETS
        and environment.get('GITHUB_BASE_REF')==binding['base_ref']
        and environment.get('GITHUB_HEAD_REF')==binding['head_ref'], 'current Android event source differs')
    A.require(live.get('number')==number and live.get('state')=='open'
        and _diagnostic_presence(live.get('labels'))==_diagnostic_presence(pr.get('labels',[])),
        'current Android diagnostic label intent changed')
    for side in ('base','head'):
        actual=pr.get(side,{})
        A.require(live.get(side,{}).get('ref')==binding[side+'_ref']
            and live.get(side,{}).get('sha')==binding[side+'_sha']
            and all(live.get(side,{}).get('repo',{}).get(key)==value for key,value in repo.items()),
            'current Android labeled PR source differs')
        A.require(actual.get('sha')==binding[side+'_sha'] and actual.get('ref')==binding[side+'_ref']
            and all(actual.get('repo',{}).get(key)==value for key,value in repo.items()), 'current Android event parents differ')
    A.require(refs['default_ref']=='main','current Android default is not protected main')
    for target,revision in ((binding['base_ref'],binding['base_sha']),('main',refs['default'])):
        branch=adapter._object('branches/'+target)
        A.require(branch.get('name')==target and branch.get('protected') is True
            and branch.get('commit',{}).get('sha')==revision,'current Android protected source moved')
    reader=SimpleNamespace(get=adapter._object)
    before=source.api_tree(reader,binding['base_sha'],tree_reader=adapter.api.immutable_tree)
    current=source.api_tree(reader,sha,tree_reader=adapter.api.immutable_tree)
    default=source.api_tree(reader,refs['default'],tree_reader=adapter.api.immutable_tree)
    root=Path(policy_root)
    A.require(execution.checkout_identity(root)[0]==refs['default']
        and inputs.full_tree(root,'HEAD')==default and _sources(candidate).entries==current
        and _sources(candidate,binding['base_sha']).entries==before,
        'current Android actual source differs from immutable B/M/D')
    admission=source.compatibility(default,default,'main',
        read_actual=lambda name:source.actual_bytes(root,name),actual_imports=source.actual_import_inventory(root))
    # B is authenticated data and may be a finite historical recipe on first
    # install. D alone supplies executable controllers; handoff checks B below.
    A.require(packages().validate_tree_wiring(before) in {
        "npm-consumers-sync-ci-v1","npm-consumers-sync-ci-budget-v1","android-owned-npm5-sync-ci-v1",CURRENT_SOURCE_GENERATION},
        'current Android predecessor is not a finite protected recipe')
    A.require(validate_tree_wiring(current,policy_root=root)==CURRENT_SOURCE_GENERATION,
        'current Android owner requires the exact complete new generation')
    validate_owned_generation(candidate,binding['base_ref'],policy_root=root,before_sha=binding['base_sha'])
    return binding,refs,current,default,admission


def verify_current_owner(candidate, event, sha, needs, environment, adapter=None, *, policy_root=ROOT,
                         clock=lambda:datetime.now(timezone.utc)):
    """Current completed Android jobs only; the outer run remains in progress.

    This grants no reusable runtime/receipt or historical PASS. The actual
    fixed execute step verifies all selected commands, subcases and runtime
    before publishing outputs. Native job/check facts authenticate its success.
    """
    if SOURCE_CAPABILITY is not True:
        raise ValueError('current Android source capability is disabled')
    bootstrap=_protected_default(policy_root)
    _,_,A,_=_native_modules();adapter=adapter or A.Adapter()
    initial=_current_source(candidate,event,sha,environment,adapter,policy_root)
    binding,refs,current,default,_=initial
    A.require(refs['default']==bootstrap['default'],'Android bootstrap/API actualD differs')
    expected=candidate_plan(candidate,event,sha,event_name='pull_request',policy_root=policy_root)
    A.require(expected['target'] in CURRENT_SOURCE_TARGETS and type(needs) is dict
        and 'android' in needs,'current Android owner is missing')
    verify_outer(needs['android'],expected)
    identifier=int(environment['GITHUB_RUN_ID'])
    registration=adapter._object('actions/workflows/repository-checks.yml')
    A.require(registration.get('path')=='.github/workflows/repository-checks.yml'
        and registration.get('state')=='active','current Android native caller registration differs')
    workflow=A.positive(registration.get('id'))
    metadata_policy=_current_metadata_policy(workflow)
    ref='refs/pull/'+str(binding['pull_request'])+'/merge'
    def observation():
        now=clock();A.P._now(now)
        A.require(adapter._object('actions/workflows/repository-checks.yml')==registration,
            'current Android native caller registration changed')
        listed=adapter._pages('actions/workflows/'+str(workflow)+'/runs?head_sha='+binding['head_sha'],'workflow_runs',search=True)
        A.require(listed and all(type(row) is dict for row in listed),'current Android run inventory unavailable')
        metadata={};ordinary=[]
        for row in listed:
            identity=A.positive(row.get('id'))
            marker=(adapter.metadata_observation(row,binding,metadata_policy,now=now)
                    if identity!=identifier else None)
            if marker is None:ordinary.append(row)
            else:metadata[identity]=marker
        times=[A.P._time(row.get('run_started_at')) for row in ordinary]
        newest=max(times)
        A.require(sum(stamp==newest for stamp in times)==1
            and ordinary[times.index(newest)].get('id')==identifier,
            'current Android run is not unique newest ordinary authority; source may be unclassified')
        run=adapter._object('actions/runs/'+str(identifier))
        attempt=adapter._object('actions/runs/'+str(identifier)+'/attempts/1')
        claimed=next(row for row in listed if row.get('id')==identifier)
        fields=('id','workflow_id','check_suite_id','path','event','head_sha','head_branch',
                'run_attempt','status','conclusion','run_started_at','updated_at')
        A.require(all(claimed.get(key)==run.get(key)==attempt.get(key) for key in fields)
            and type(run.get('run_attempt')) is int and run['run_attempt']==1 and run.get('workflow_id')==workflow
            and all(run.get(key)==attempt.get(key) for key in
                ('repository','head_repository','pull_requests','referenced_workflows'))
            and A.P._time(run['run_started_at'])<=A.P._time(run['updated_at'])<=now
            and run.get('path')=='.github/workflows/repository-checks.yml' and run.get('event')=='pull_request'
            and run.get('head_sha')==binding['head_sha'] and run.get('head_branch')==binding['head_ref']
            and run.get('repository',{}).get('id')==run.get('head_repository',{}).get('id')==REPOSITORY_ID
            and run.get('repository',{}).get('full_name')==run.get('head_repository',{}).get('full_name')==REPOSITORY
            and (run.get('status'),run.get('conclusion'))==('in_progress',None)
            and sum(type(pr) is dict and pr.get('number')==binding['pull_request'] for pr in run.get('pull_requests',[]))==1,
            'current Android run/attempt/source identity differs')
        references=attempt.get('referenced_workflows')
        A.require(type(references) is list,'current Android reusable source chain unavailable')
        paths=[]
        for item in references:
            A.require(type(item) is dict and item.get('sha')==sha and item.get('ref')==ref
                and type(item.get('path')) is str and item['path'].startswith(REPOSITORY+'/.github/workflows/')
                and item['path'].endswith('@'+sha),'current Android reusable source is foreign')
            path=item['path'][len(REPOSITORY)+1:-(len(sha)+1)]
            A.require(current.get(path,{}).get('mode')=='100644' and current[path]['type']=='blob'
                and path not in paths,'current Android reusable source leaf differs')
            paths.append(path)
        A.require(paths,'current Android native M source edge is unavailable')
        if expected['required']:
            A.require(WORKFLOW in paths,'current Android callee source is unavailable')
        jobs=adapter._pages('actions/runs/'+str(identifier)+'/attempts/1/jobs','jobs')
        outer=[job for job in jobs if job.get('name')=='repository-checks']
        A.require(len(outer)==1,'current Android outer native job is missing or ambiguous')
        outer_fact=adapter._job(outer[0],attempt,15368,final_name='repository-checks')
        A.require((outer_fact.status,outer_fact.conclusion)==('in_progress',None)
            and outer_fact.completed_at is None and A.P._time(run['run_started_at'])
                <=A.P._time(outer_fact.started_at)<=now,'current Android outer native job differs')
        facts={'outer':{'job':outer[0],'check':vars(outer_fact)}}
        A.require(all(job.get('name') in CURRENT_JOBS for job in jobs
            if type(job.get('name')) is str and job['name'].startswith('android / ')),
            'current Android native owner inventory is unknown')
        for name,step_name in CURRENT_JOBS.items():
            matches=[job for job in jobs if job.get('name')==name]
            if not expected['required']:
                A.require(not matches or len(matches)==1 and matches[0].get('status')=='completed'
                    and matches[0].get('conclusion')=='skipped','unselected Android executed or failed')
                continue
            A.require(len(matches)==1,'current Android native owner is missing or ambiguous')
            job=matches[0];fact=adapter._job(job,attempt,15368,final_name=name)
            A.require((fact.status,fact.conclusion)==('completed','success')
                and A.P._time(run['run_started_at'])<=A.P._time(fact.started_at)<=A.P._time(fact.completed_at)<=now,
                'current Android native owner did not succeed')
            steps=[step for step in job.get('steps',[]) if step.get('name')==step_name]
            A.require(len(steps)==1 and steps[0].get('status')=='completed' and steps[0].get('conclusion')=='success'
                and A.P._time(fact.started_at)<=A.P._time(steps[0].get('started_at'))
                    <=A.P._time(steps[0].get('completed_at'))<=A.P._time(fact.completed_at),
                'current Android actual execute/verify step did not succeed')
            facts[name]={'job':job,'check':vars(fact)}
        if expected['required']:
            A.require(A.P._time(facts['android / route']['job']['completed_at'])
                <=A.P._time(facts['android / execute']['job']['started_at'])
                and A.P._time(facts['android / execute']['job']['completed_at'])
                <=A.P._time(facts['android / verify']['job']['started_at']), 'current Android owner ordering differs')
        for row in listed:
            identity=A.positive(row.get('id'))
            if identity in metadata:
                A.require(adapter.metadata_observation(row,binding,metadata_policy,now=clock())==metadata[identity],
                    'current Android typed metadata source changed during observation')
        # Only the adapter's exact authenticated intent recipe has a stable
        # progress projection. Ordinary and historical marker rows stay whole.
        inventory=[A.metadata_inventory_record(row,metadata.get(row['id'])) for row in listed]
        return {'registration':registration,'listed':inventory,'run':run,'attempt':attempt,'jobs':jobs,'facts':facts,'metadata':metadata}
    first=observation()
    if expected['required']:
        # Full current plan is independently derived from protected policy;
        # no downloaded receipt or suite-count output supplies authority.
        owner_plan=android().plan(candidate,binding['base_ref'],views=expected['views'],policy_root=policy_root)
        normal=android().plan(candidate,binding['base_ref'],
            views=event_views({'pull_request':{'labels':[]}},'pull_request',True),policy_root=policy_root)
        A.require(owner_plan['plan']==expected['owner_plan'] and set(normal['executions'])<=set(owner_plan['executions'])
            and len(normal['executions'])==40,'current Android union omits mandatory ordinary owners')
    A.require(_current_source(candidate,event,sha,environment,adapter,policy_root)==initial
        and candidate_plan(candidate,event,sha,event_name='pull_request',policy_root=policy_root)==expected
        and observation()==first and SOURCE_CAPABILITY is True,'current Android source/native owner changed')
    return {'kind':'current-original-android-owner','qualification':False,'verified':True,
        'run_id':identifier,'attempt':1,'candidate':sha,'plan':expected['plan'],
        'inventory':expected['inventory'],'executed':expected['required']}


def _source_generation(candidate,sha,policy_root):
    """Stdlib-only dispatch data; it grants no execution/admission authority."""
    if type(sha) is not str or not re.fullmatch('[0-9a-f]{40}',sha) or sha=='0'*40:
        raise ValueError('Android source dispatch candidate is unavailable')
    raw=_bootstrap_git(policy_root,'show','HEAD:.github/package-workflow-generations.json')
    if len(raw)>64_000:raise ValueError('Android source catalog exceeds bound')
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('Android source catalog has duplicate fields')
            value[key]=item
        return value
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite source catalog')))
    if type(value) is not dict or set(value)!={'schema','repository','generations'} or type(value['schema']) is not int \
            or value['schema']!=1 or value['repository']!={'full_name':REPOSITORY,'id':REPOSITORY_ID} \
            or type(value['repository'].get('id')) is not int \
            or type(value['generations']) is not list or not 1<=len(value['generations'])<=23:
        raise ValueError('Android source catalog is not the finite protected schema')
    four={'.github/workflows/'+name+'.yml' for name in ('project-tests','parent-qualification','sync-validation','repository-checks')}
    five=four|{'.github/workflows/browser-client.yml'};six=five|{'.github/workflows/pr-metadata-context.yml'}
    names=set();identities=set()
    for row in value['generations']:
        if type(row) is not dict or set(row)!={'name','workflows'} or type(row['name']) is not str \
                or not re.fullmatch('[a-z0-9][a-z0-9-]*',row['name']) or row['name'] in names \
                or type(row['workflows']) is not dict or set(row['workflows']) not in (four,five,six):
            raise ValueError('Android source recipe is unknown or incomplete')
        if row['name']==CURRENT_SOURCE_GENERATION and set(row['workflows'])!=six:
            raise ValueError('Android current source recipe is incomplete')
        names.add(row['name'])
        for entry in row['workflows'].values():
            if type(entry) is not dict or set(entry)!={'mode','type','sha'} or entry['mode']!='100644' \
                    or entry['type']!='blob' or type(entry['sha']) is not str \
                    or not re.fullmatch('[0-9a-f]{40}',entry['sha']) or entry['sha']=='0'*40:
                raise ValueError('Android source workflow is nonordinary')
        identity=digest(row['workflows'])
        if identity in identities:raise ValueError('Android source recipe is duplicated')
        identities.add(identity)
    entries={}
    for row in _bootstrap_git(candidate,'ls-tree','-rz','--full-tree',sha,'--','.github/workflows').split(b'\0'):
        if row:
            header,path=row.split(b'\t',1);mode,kind,oid=header.decode().split()
            entries[path.decode()]={'mode':mode,'type':kind,'sha':oid}
    for row in sorted(value['generations'],key=lambda row:len(row['workflows']),reverse=True):
        if all(entries.get(path)==entry for path,entry in row['workflows'].items()):return row['name']
    raise ValueError('Android source candidate does not match any complete protected recipe')


def current_source_owner(candidate,event,sha,needs,environment,adapter=None,*,policy_root=ROOT):
    """New recipe dispatch before imports; old recipes keep original admit()."""
    if _source_generation(candidate,sha,policy_root)!=CURRENT_SOURCE_GENERATION:
        return None
    return verify_current_owner(candidate,event,sha,needs,environment,adapter,policy_root=policy_root)


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
    validate_execution_generation(candidate, event, policy_root=policy_root)
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
        validate_execution_generation(args.candidate, event)
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
