#!/usr/bin/env python3
"""Staged required S3 package checks, independent of the shared-host decision.

Active legacy callers retain their existing capabilities. Load this controller
from the trusted default branch; candidate paths, caller strings and job outputs
cannot narrow its independently recomputed exact-candidate plan.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
S3 = "script-archive/marketplace/S3Server"
BROWSER = "browser-client"
TEMPLATES = ROOT / "tools/repository-checks/workflows/packages"
TEMPLATE_NAMES = ("project-tests.yml", "parent-qualification.yml", "sync-validation.yml",
                  "repository-checks.yml", "repository-checks-direct.yml")
GENERATION_MANIFEST = ".github/package-workflow-generations.json"
PRODUCER_TEMPLATE = "tools/repository-checks/workflows/producers/project-tests.yml"
WORKFLOW_PATHS = tuple(".github/workflows/" + name for name in (
    "project-tests.yml", "parent-qualification.yml", "sync-validation.yml", "repository-checks.yml"))
CONSUMER_WORKFLOW_PATHS = (*WORKFLOW_PATHS, '.github/workflows/browser-client.yml')
METADATA_WORKFLOW_PATHS = (*CONSUMER_WORKFLOW_PATHS, '.github/workflows/pr-metadata-context.yml')
CONSUMER_TEMPLATES = 'tools/repository-checks/workflows/npm-consumers/'
# Only these complete protected recipes publish the sixth route output. The
# postmerge-original-e-v1 predecessor retains the strict legacy five-field form.
_PROTECTED_ROUTE_GENERATIONS = frozenset({
    'protected-shared-producer-v1',
    'protected-producer-postmerge-original-e-v1',
    'protected-producer-ci37-v1',
    'protected-producer-metadata-ci-v1',
    'protected-producer-seven-target-ci-v1',
    'protected-producer-original-default-v1',
})


def _trusted_sparse_blob(relative, limit):
    """Read an omitted tracked input from this trusted checkout's exact HEAD."""
    def git(*arguments):
        return subprocess.check_output(["git", "--no-replace-objects", *arguments], cwd=ROOT,
                                       stderr=subprocess.PIPE, timeout=30)
    try:
        # A deleted/materialized policy file is an error, not a sparse omission.
        if git("ls-files", "-v", "--error-unmatch", "--", relative) != ("S " + relative + "\n").encode():
            raise ValueError("trusted package input is missing outside sparse policy")
        raw = git("ls-tree", "-z", "HEAD", "--", ":(literal)" + relative)
        records = raw.rstrip(b"\0").split(b"\0")
        if len(records) != 1:
            raise ValueError("trusted sparse input is not an exact Git blob")
        metadata, encoded_path = records[0].split(b"\t", 1)
        mode, kind, sha = metadata.decode("ascii").split()
        if encoded_path.decode("utf-8") != relative or mode not in {"100644", "100755"} or kind != "blob" \
                or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("trusted sparse input is not an ordinary Git blob")
        if int(git("cat-file", "-s", sha)) > limit:
            raise ValueError("trusted sparse package input is oversized")
        value = git("cat-file", "blob", sha)
        if len(value) > limit:
            raise ValueError("trusted sparse package input is oversized")
        return value
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise ValueError("trusted sparse package input is unavailable") from error


def _trusted_bytes(relative, *, limit=1_000_000, git_fallback=False):
    path = ROOT
    for component in PurePosixPath(relative).parts:
        path = path / component
        if path.is_symlink():
            raise ValueError("trusted package policy cannot contain symbolic links")
    if not path.exists() and git_fallback:
        return _trusted_sparse_blob(relative, limit)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("trusted package policy file is missing or oversized")
    value = path.read_bytes()
    if len(value) > limit:
        raise ValueError("trusted package policy file is oversized")
    return value


def _requirement_paths():
    """Follow the same exact pinned -r graph without materializing sparse files."""
    visited, pins = set(), {}
    def read(relative):
        relative = posixpath.normpath(relative)
        if relative.startswith("/") or relative == ".." or relative.startswith("../"):
            raise ValueError("trusted host requirements escape the policy checkout")
        if relative in visited:
            return
        visited.add(relative)
        if len(visited) > 20:
            raise ValueError("trusted host requirement graph exceeds its bound")
        source = _trusted_bytes(relative, limit=100_000, git_fallback=True).decode("utf-8")
        for line in source.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("-r "):
                read(posixpath.join(posixpath.dirname(relative), line[3:].strip()))
                continue
            match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9_.+!-]+)", line)
            if not match:
                raise ValueError("trusted host requirements must use exact version pins")
            name = re.sub(r"[-_.]+", "-", match[1]).lower()
            if name in pins and pins[name] != match[2]:
                raise ValueError("trusted host requirements contain conflicting pins")
            pins[name] = match[2]
    read("tests/requirements-host.txt")
    if not pins:
        raise ValueError("trusted host requirements are empty")
    return visited


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate trusted workflow-generation field")
        result[key] = value
    return result


def workflow_generations():
    """Read complete reviewed tuples from trusted policy, never candidate JSON."""
    document = json.loads(_trusted_bytes(GENERATION_MANIFEST, limit=64_000), object_pairs_hook=_unique_fields)
    if not isinstance(document, dict) or set(document) != {"schema", "repository", "generations"} \
            or type(document["schema"]) is not int or document["schema"] != 1 \
            or document["repository"] != {"full_name": REPOSITORY, "id": REPOSITORY_ID} \
            or type(document["repository"].get("id")) is not int:
        raise ValueError("invalid trusted package workflow-generation policy")
    generations = document["generations"]
    if not isinstance(generations, list) or not 1 <= len(generations) <= 23:
        raise ValueError("invalid trusted package workflow-generation inventory")
    names, tuples = set(), set()
    for generation in generations:
        if not isinstance(generation, dict) or set(generation) != {"name", "workflows"}:
            raise ValueError("invalid complete workflow-generation fields")
        name, workflows = generation["name"], generation["workflows"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in names \
                or not isinstance(workflows, dict) or set(workflows) not in (
                    set(WORKFLOW_PATHS), set(CONSUMER_WORKFLOW_PATHS), set(METADATA_WORKFLOW_PATHS)):
            raise ValueError("invalid or duplicate complete workflow generation")
        for entry in workflows.values():
            if not isinstance(entry, dict) or set(entry) != {"mode", "type", "sha"} \
                    or entry["mode"] != "100644" or entry["type"] != "blob" \
                    or not isinstance(entry["sha"], str) or not re.fullmatch(r"[0-9a-f]{40}", entry["sha"]) \
                    or entry["sha"] == "0" * 40:
                raise ValueError("workflow generations require exact ordinary Git blob identities")
        identity = _digest(workflows)
        if identity in tuples:
            raise ValueError("duplicate complete workflow-generation tuple")
        names.add(name)
        tuples.add(identity)
    return generations


def _policy_inputs():
    """Bind actual templates, generation policy, controller and requirement graph."""
    workflow_generations()
    relatives = ["tools/repository-checks/workflows/packages/" + name for name in TEMPLATE_NAMES]
    relatives += [GENERATION_MANIFEST, PRODUCER_TEMPLATE, ".github/test-suites.json",
                  ".github/repository-checks.json", ".github/branch-policy.json",
                  "tests/run-project-tests.py", "tests/platform-profile.json",
                  "tools/sync-test-reuse/qualification.py"]
    relatives += ["tools/repository-checks/" + name for name in (
        "check.py", "package_checks.py", "tool_dependencies.py", "host_selection.py",
        "npm_consumers.py", "npm-source-map-tests.cjs", "npm-proxy-addr-tests.cjs")]
    relatives += ["tools/test-evidence/" + name for name in ("run.py", "execution.py", "inputs.py", "runtime.py", "attested.py")]
    relatives += [".github/attested-runtime.json"]
    relatives += [CONSUMER_TEMPLATES + name for name in ('browser-client.yml', 'repository-checks.yml')]
    relatives += ['tools/repository-checks/workflows/metadata-edits/' + name
                  for name in ('repository-checks.yml', 'sync-test-reuse.yml')]
    relatives += list(_requirement_paths())
    return {relative: hashlib.sha256(_trusted_bytes(relative, git_fallback=True)).hexdigest()
            for relative in sorted(set(relatives))}


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def tools():
    return load("package_owned_tools", "tools/repository-checks/tool_dependencies.py")


def select(paths, regular=True, *, legacy_mode="full", legacy_projects=(), unknown=False, include_browser=False):
    """OR-select S3 even when mixed/native/unknown changes keep host mode full."""
    for path in paths:
        if not isinstance(path, str):
            raise ValueError("invalid package input path")
        p = PurePosixPath(path)
        if not isinstance(path, str) or not path or "\0" in path or "\\" in path \
                or p.is_absolute() or ".." in p.parts or str(p) != path:
            raise ValueError("invalid package input path")
    packages = [S3] if unknown or any(p == S3 or p.startswith(S3 + "/") for p in paths) else []
    browser_manifests = {BROWSER + "/package.json", BROWSER + "/package-lock.json"}
    if include_browser and browser_manifests.intersection(paths):
        packages.append(BROWSER)
    capability = {"include_browser": True} if include_browser else {}
    bounded = () if unknown else tools().affected_projects(paths, regular, include_s3=True, **capability)
    mode, projects = ("full", []) if unknown else (legacy_mode, list(legacy_projects))
    if bounded and legacy_mode not in {"delegated-sync", "documentation"}:
        projects = [p for p in bounded if p not in {S3, BROWSER}]
        mode = "tool-dependencies" if projects else "package-dependencies"
    return {"host_mode": mode, "tool_projects": projects, "package_set": packages}


def _git(candidate, *args):
    return subprocess.check_output(["git", "--no-replace-objects", *args], cwd=candidate,
                                   text=True, stderr=subprocess.PIPE, timeout=30).strip()


def _digest(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def consumer_generation(candidate):
    """Detect a complete reviewed caller; old four-file callers stay unchanged."""
    path = Path(candidate) / '.github/workflows/repository-checks.yml'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        return False
    value = path.read_bytes()
    sha = hashlib.sha1(b'blob ' + str(len(value)).encode() + b'\0' + value).hexdigest()
    if not any(set(generation['workflows']) in (set(CONSUMER_WORKFLOW_PATHS), set(METADATA_WORKFLOW_PATHS))
               and generation['workflows']['.github/workflows/repository-checks.yml']['sha'] == sha
               for generation in workflow_generations()):
        return False
    name = validate_wiring(candidate)
    return any(generation['name'] == name and set(generation['workflows']) in (set(CONSUMER_WORKFLOW_PATHS), set(METADATA_WORKFLOW_PATHS))
               for generation in workflow_generations())


def consumer_base(candidate, revision):
    """A deployed protected-base generation cannot be reverted to a legacy pair."""
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        return False
    try:
        raw = _git(candidate, 'ls-tree', '-z', revision, '--', *METADATA_WORKFLOW_PATHS)
    except subprocess.CalledProcessError:
        return False  # The separately established unknown-history fallback remains full.
    tree = {}
    for record in raw.split('\0'):
        if not record:
            continue
        metadata, path = record.split('\t', 1)
        mode, kind, sha = metadata.split()
        tree[path] = {'mode': mode, 'type': kind, 'sha': sha}
    return any(set(generation['workflows']) in (set(CONSUMER_WORKFLOW_PATHS), set(METADATA_WORKFLOW_PATHS))
               and all(tree.get(path) == entry for path, entry in generation['workflows'].items())
               for generation in workflow_generations())


def candidate_plan(candidate, event, sha, *, include_browser=False, include_consumers=None, pr_context=None):
    repository = event.get("repository", {})
    if repository.get("full_name") != REPOSITORY or repository.get("id") != REPOSITORY_ID:
        raise ValueError("package repository identity mismatch")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) or _git(candidate, "rev-parse", "HEAD") != sha:
        raise ValueError("package checkout must be the exact candidate")
    checks = load("package_repository_policy", "tools/repository-checks/check.py")
    config, branches = checks.configuration()
    base = head = ""
    unknown = False
    if isinstance(event.get("pull_request"), dict):
        pr = event["pull_request"]
        repo = pr["base"].get("repo") or {}
        if repo.get("full_name") != REPOSITORY or repo.get("id") != REPOSITORY_ID:
            raise ValueError("foreign package PR base")
        context = checks.pr_candidate_context(candidate, event, sha, pr_context=pr_context)
        base, head = context["base"], context["head"]
        paths, regular = checks.changed_paths(candidate, event, sha, pr_context=context)
    elif "before" in event or "after" in event:
        base, head = event.get("before"), event.get("after")
        if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{40}", v) for v in (base, head)) or head != sha:
            raise ValueError("invalid exact package push identity")
        try:
            if base == "0" * 40:
                raise ValueError("new push has no complete previous inventory")
            paths, regular = checks.inventory_paths(candidate, base, sha)
        except (ValueError, subprocess.CalledProcessError):
            paths, regular, unknown = [], False, True
    else:
        paths, regular, unknown = [], False, True
    legacy = checks.plan(event, paths, config, branches, regular)
    current_consumers = consumer_generation(candidate)
    if consumer_base(candidate, base) and (not current_consumers or include_consumers is False):
        raise ValueError('deployed required npm consumer ownership cannot be disabled')
    if include_consumers is None:
        include_consumers = current_consumers
    consumers = None
    if include_consumers:
        consumers = load("package_npm_consumers", "tools/repository-checks/npm_consumers.py").select(candidate, base, sha)
    focused_browser = (consumers is not None and consumers['projects'][BROWSER]['profile']
                       in {'source-map-postcss-v1', 'none'})
    selected = select(paths, regular, legacy_mode=legacy["mode"],
                      legacy_projects=legacy.get("tool_projects", "").split(",") if legacy.get("tool_projects") else (),
                      unknown=unknown, include_browser=include_browser or focused_browser)
    empty = checks.verified_empty_candidate(candidate,event,sha) if not paths and not unknown else None
    if empty is not None:
        selected = {'host_mode':'unchanged','tool_projects':[],'package_set':[]}
    if consumers is not None:
        selected['package_set'] = [project for project in selected['package_set']
                                  if consumers['projects'][project]['profile'] != 'none']
        selected['dependency_profiles'] = consumers
        selected['consumer_generation'] = current_consumers
    policy = _policy_inputs()
    result = {"schema": 1, "candidate": sha, "tree": _git(candidate, "rev-parse", "HEAD^{tree}"),
              "base": base, "head": head, "paths": paths, "regular": regular, "unknown": unknown,
              "policy": policy, **selected}
    if empty is not None:
        result['verified_empty_delta'] = empty
    result["plan"] = _digest(result)
    return result


def outputs(plan):
    return {"package_candidate": plan["candidate"], "package_plan": plan["plan"],
            "package_host_mode": plan["host_mode"],
            "package_tool_projects": json.dumps(plan["tool_projects"], separators=(",", ":")),
            "package_set": json.dumps(plan["package_set"], separators=(",", ":"))}


def browser_outputs(plan):
    """Omit legacy jobs only when the reviewed required owner proves selection."""
    profile = (plan.get('dependency_profiles') or {}).get('projects', {}).get(BROWSER, {})
    focused = (profile.get('profile') == 'source-map-postcss-v1'
               and profile.get('required') is True and BROWSER in plan['package_set'])
    unchanged = (profile.get('profile') == 'none' and profile.get('required') is False
                 and profile.get('reason') == 'reviewed-lockfile-format-only')
    omit = plan.get('consumer_generation') is True and (focused or unchanged)
    return {'browser_npm_only': str(omit).lower(), 'package_candidate': plan['candidate'],
            'package_plan': plan['plan']}


def receipt(plan, lane="project"):
    return {"package_verified": "true", "package_candidate": plan["candidate"],
            "package_plan": plan["plan"], "package_lane": lane}


def has_staged_caller(candidate):
    """Detect only the exact next generation, retaining legacy sparse routing."""
    path = Path(candidate) / ".github/workflows/repository-checks.yml"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        return False
    value = path.read_bytes()
    identity = hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest()
    return identity in {generation["workflows"][".github/workflows/repository-checks.yml"]["sha"]
                        for generation in workflow_generations()}


def verify_empty_plan(plan, candidate, event):
    """No route marker can replace fresh exact-candidate zero-work planning."""
    if candidate is None or event is None or not isinstance(plan,dict) or plan.get('host_mode') != 'unchanged':
        raise ValueError('unchanged route requires its immutable candidate and native event')
    current = candidate_plan(candidate,event,plan.get('candidate'))
    if current != plan or current.get('verified_empty_delta') is None:
        raise ValueError('unchanged route differs from independently verified empty inputs')


def verify(needs, plan, *, candidate=None, event=None):
    if plan.get('host_mode') == 'unchanged':
        verify_empty_plan(plan,candidate,event)
    if not isinstance(needs, dict) or set(needs) != {"route", "project-tests", "tool-dependencies", "package-checks"}:
        raise ValueError("incomplete required package project dependencies")
    if needs["route"].get("result") != "success" or needs["route"].get("outputs") != outputs(plan):
        raise ValueError("package route differs from the exact trusted candidate plan")
    selected = {"project-tests": plan["host_mode"] == "full",
                "tool-dependencies": plan["host_mode"] == "tool-dependencies",
                "package-checks": bool(plan["package_set"])}
    for name, required in selected.items():
        job = needs[name]
        if job.get("result") != ("success" if required else "skipped"):
            raise ValueError(f"{name}: selected package/host check did not succeed")
        if required and name != "project-tests" and job.get("outputs") != receipt(plan, name):
            raise ValueError(f"{name}: exact package execution receipt missing")
        if plan['host_mode']=='unchanged' and job.get('outputs') != {}:
            raise ValueError(f"{name}: unchanged route requires exact empty unselected outputs")
    return {} if plan['host_mode']=='unchanged' else receipt(plan)


def verify_protected_route(needs, plan, candidate, *, event=None):
    """Admit one fixed routing field from an actual complete protected recipe.

    The literal flag describes dispatch only. It grants no execution, receipt
    or native publisher authority; the existing verifier checks every lane.
    """
    if validate_wiring(candidate) not in _PROTECTED_ROUTE_GENERATIONS:
        raise ValueError("protected route requires a complete reviewed producer generation")
    route = needs.get('route') if isinstance(needs,dict) else None
    published = route.get('outputs') if isinstance(route,dict) else None
    if not isinstance(published,dict) or set(published) != set(outputs(plan)) | {'protected_full'} \
            or type(published.get('protected_full')) is not str \
            or published['protected_full'] not in {'true','false'} \
            or (published['protected_full']=='true' and plan['host_mode']!='full'):
        raise ValueError("protected route output differs from the reviewed producer contract")
    ordinary = {key:value for key,value in published.items() if key!='protected_full'}
    normalized = {**needs,'route':{**route,'outputs':ordinary}}
    return verify(normalized,plan,candidate=candidate,event=event)


def validate_wiring(candidate):
    """Accept one complete reviewed generation; never combine allowed files."""
    candidate = Path(candidate)
    if any(not p.is_dir() or p.is_symlink() for p in (candidate / ".github", candidate / ".github/workflows")):
        raise ValueError("package workflow directories must be ordinary directories")
    tree = {}
    required = list(WORKFLOW_PATHS)
    caller = candidate / '.github/workflows/repository-checks.yml'
    if caller.is_file() and not caller.is_symlink() and caller.stat().st_size <= 1_000_000:
        value = caller.read_bytes()
        identity = hashlib.sha1(b'blob ' + str(len(value)).encode() + b'\0' + value).hexdigest()
        matching = [generation for generation in workflow_generations()
                    if generation['workflows']['.github/workflows/repository-checks.yml']['sha'] == identity]
        if matching:
            required = sorted(set(required) | set().union(*(set(row['workflows']) for row in matching)))
    for relative in required:
        path = candidate / relative
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000 \
                or path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            raise ValueError("required package workflows must be ordinary non-executable files")
        value = path.read_bytes()
        if len(value) > 1_000_000:
            raise ValueError("required package workflow is oversized")
        tree[relative] = {"mode": "100644", "type": "blob",
                          "sha": hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest()}
    return validate_tree_wiring(tree)


def validate_tree_wiring(tree):
    """Validate a complete API/Git tuple already authenticated by its caller.

    This pure comparison does not authenticate a tree, run or artifact itself.
    Unknown/missing generations fail closed, including individually known files
    combined into a tuple that trusted policy never approved.
    """
    if not isinstance(tree, dict):
        raise ValueError("required package workflow tree is invalid")
    for generation in sorted(workflow_generations(), key=lambda item: len(item['workflows']), reverse=True):
        if all(isinstance(tree.get(path), dict) and all(tree[path].get(key) == value for key, value in entry.items())
               for path, entry in generation["workflows"].items()):
            return generation["name"]
    raise ValueError("unapproved complete required package workflow generation")


def activated(event):
    checks = load("package_activation_policy", "tools/repository-checks/check.py")
    config, _ = checks.configuration()
    targets = config.get("package_checks_required_branches", [])
    if not targets:
        return False
    if not isinstance(event, dict):
        raise ValueError("invalid package activation event")
    repo = event.get("repository") or {}
    if not isinstance(repo, dict):
        raise ValueError("invalid package activation repository")
    if repo.get("full_name") != REPOSITORY or repo.get("id") != REPOSITORY_ID:
        raise ValueError("package activation repository mismatch")
    if "pull_request" in event:
        pr = event["pull_request"]
        base = pr.get("base") if isinstance(pr, dict) else None
        base_repo = base.get("repo") if isinstance(base, dict) else None
        if not isinstance(base_repo, dict) or base_repo.get("full_name") != REPOSITORY \
                or base_repo.get("id") != REPOSITORY_ID:
            raise ValueError("invalid package activation base repository")
        branch = base.get("ref")
        if isinstance(branch, str) and branch.startswith("refs/"):
            raise ValueError("invalid package activation PR branch")
    else:
        ref = event.get("ref")
        if not isinstance(ref, str):
            raise ValueError("missing package activation branch ref")
        if ref.startswith("refs/heads/"):
            branch = ref[len("refs/heads/"):]
        elif not ref.startswith("refs/") and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
            # Dispatch payload refs can be unqualified. Runner metadata must
            # prove that this exact ref is a branch rather than an equal tag.
            branch = ref
        else:
            raise ValueError("unsupported package activation ref")
        if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and (
                os.environ.get("GITHUB_REF") != "refs/heads/" + branch
                or os.environ.get("GITHUB_REF_TYPE", "branch") != "branch"):
            raise ValueError("manual package activation branch identity mismatch")
    # Git branch syntax, checked in linear time. A malformed ref cannot turn an
    # activated target into an apparently inactive legacy caller.
    if (not isinstance(branch, str) or not branch or branch.startswith(("-", "/"))
            or branch.endswith("/") or "//" in branch or ".." in branch or "@{" in branch or branch == "@"
            or any(ord(char) <= 32 or ord(char) == 127 or char in "~^:?*[\\" for char in branch)
            or any(part.startswith(".") or part.endswith((".", ".lock")) for part in branch.split("/"))):
        raise ValueError("invalid package activation branch")
    return branch in targets


def execute(candidate, plan, lane, *, include_browser=False):
    projects = plan["tool_projects"] if lane == "tool-dependencies" else plan["package_set"]
    if lane not in {"tool-dependencies", "package-checks"} or not projects:
        raise ValueError("no independently selected package execution lane")
    # No CLI flag or candidate JSON enables this capability. Existing callers
    # retain S3/tool ownership until the atomic Browser caller/trigger handoff.
    if _git(candidate, "rev-parse", "HEAD") != plan["candidate"] or _git(candidate, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("package source changed before execution")
    root = Path(candidate).resolve()
    for project in projects:
        folder = root / project
        for path in (folder, *folder.parents):
            if path == root:
                break
            if path.is_symlink():
                raise ValueError("package execution cannot follow source directory symlinks")
        for name in ("package.json", "package-lock.json"):
            path = folder / name
            if not path.is_file() or path.is_symlink():
                raise ValueError("package execution requires ordinary npm manifests")
    # execution.py uses sibling imports. Resolve them explicitly from this
    # trusted checkout, never from candidate source or an ambient PYTHONPATH.
    load("inputs", "tools/test-evidence/inputs.py")
    load("runtime", "tools/test-evidence/runtime.py")
    controller = load("package_process_boundary", "tools/test-evidence/execution.py")
    with controller.candidate_process_environment():
        consumers = plan.get('dependency_profiles') if lane == 'package-checks' else None
        focused = [project for project in projects if consumers is not None
                   and consumers['projects'][project]['profile'] in {
                       'source-map-postcss-v1', 'proxy-addr-express-v1'}]
        if focused:
            module = load("package_npm_consumer_execution", "tools/repository-checks/npm_consumers.py")
            result = module.run(Path(candidate), consumers, focused)
            print(json.dumps({'focused_npm_consumers': result}, sort_keys=True))
        remaining = [project for project in projects if project not in focused]
        if remaining:
            capability = {"include_browser": True} if include_browser else {}
            tools().run(Path(candidate), remaining, include_s3=True, **capability)
    if _git(candidate, "rev-parse", "HEAD") != plan["candidate"] or _git(candidate, "diff", "--name-only", "HEAD", "--"):
        raise ValueError("package source changed during execution")
    return receipt(plan, lane)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "run", "verify", "browser-route"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-candidate", default="")
    parser.add_argument("--expected-plan", default="")
    parser.add_argument("--expected-projects", default="")
    parser.add_argument("--lane", default="package-checks")
    parser.add_argument("--needs-json", default="{}")
    args = parser.parse_args()
    try:
        event = json.loads(args.event.read_text())
        generation = validate_wiring(args.candidate)
        plan = candidate_plan(args.candidate, event, args.sha)
        if args.expected_candidate and args.expected_candidate != plan["candidate"]:
            raise ValueError("package caller candidate mismatch")
        if args.expected_plan and args.expected_plan != plan["plan"]:
            raise ValueError("package caller plan mismatch")
        if args.expected_projects and args.expected_projects != ",".join(plan["tool_projects"]):
            raise ValueError("package caller cannot select arbitrary tool projects")
        if args.command == 'browser-route':
            result = browser_outputs(plan)
        elif args.command == "plan":
            result = outputs(plan)
        elif args.command == "run":
            result = execute(args.candidate, plan, args.lane)
        else:
            needs = json.loads(args.needs_json)
            result = (verify_protected_route(needs,plan,args.candidate,event=event)
                      if generation in _PROTECTED_ROUTE_GENERATIONS else verify(needs,plan,candidate=args.candidate,event=event))
        with args.output.open("a") as output:
            output.write("".join(f"{key}={value}\n" for key, value in result.items()))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, OSError, TypeError, subprocess.SubprocessError) as error:
        print(f"Package checks failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
