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
TEMPLATES = ROOT / "tools/repository-checks/workflows/packages"
TEMPLATE_NAMES = ("project-tests.yml", "parent-qualification.yml", "sync-validation.yml",
                  "repository-checks.yml", "repository-checks-direct.yml")
GENERATION_MANIFEST = ".github/package-workflow-generations.json"
PRODUCER_TEMPLATE = "tools/repository-checks/workflows/producers/project-tests.yml"
WORKFLOW_PATHS = tuple(".github/workflows/" + name for name in (
    "project-tests.yml", "parent-qualification.yml", "sync-validation.yml", "repository-checks.yml"))


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
    if not isinstance(generations, list) or not 1 <= len(generations) <= 16:
        raise ValueError("invalid trusted package workflow-generation inventory")
    names, tuples = set(), set()
    for generation in generations:
        if not isinstance(generation, dict) or set(generation) != {"name", "workflows"}:
            raise ValueError("invalid complete workflow-generation fields")
        name, workflows = generation["name"], generation["workflows"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in names \
                or not isinstance(workflows, dict) or set(workflows) != set(WORKFLOW_PATHS):
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
    relatives += ["tools/repository-checks/" + name for name in ("check.py", "package_checks.py", "tool_dependencies.py")]
    relatives += ["tools/test-evidence/" + name for name in ("run.py", "execution.py", "inputs.py", "runtime.py")]
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


def select(paths, regular=True, *, legacy_mode="full", legacy_projects=(), unknown=False):
    """OR-select S3 even when mixed/native/unknown changes keep host mode full."""
    for path in paths:
        if not isinstance(path, str):
            raise ValueError("invalid package input path")
        p = PurePosixPath(path)
        if not isinstance(path, str) or not path or "\0" in path or "\\" in path \
                or p.is_absolute() or ".." in p.parts or str(p) != path:
            raise ValueError("invalid package input path")
    packages = [S3] if unknown or any(p == S3 or p.startswith(S3 + "/") for p in paths) else []
    bounded = () if unknown else tools().affected_projects(paths, regular, include_s3=True)
    mode, projects = ("full", []) if unknown else (legacy_mode, list(legacy_projects))
    if bounded and legacy_mode not in {"delegated-sync", "documentation"}:
        projects = [p for p in bounded if p != S3]
        mode = "tool-dependencies" if projects else "package-dependencies"
    return {"host_mode": mode, "tool_projects": projects, "package_set": packages}


def _git(candidate, *args):
    return subprocess.check_output(["git", "--no-replace-objects", *args], cwd=candidate,
                                   text=True, stderr=subprocess.PIPE, timeout=30).strip()


def _digest(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def candidate_plan(candidate, event, sha):
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
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        paths, regular = checks.changed_paths(candidate, event, sha)
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
    selected = select(paths, regular, legacy_mode=legacy["mode"],
                      legacy_projects=legacy.get("tool_projects", "").split(",") if legacy.get("tool_projects") else (),
                      unknown=unknown)
    policy = _policy_inputs()
    result = {"schema": 1, "candidate": sha, "tree": _git(candidate, "rev-parse", "HEAD^{tree}"),
              "base": base, "head": head, "paths": paths, "regular": regular, "unknown": unknown,
              "policy": policy, **selected}
    result["plan"] = _digest(result)
    return result


def outputs(plan):
    return {"package_candidate": plan["candidate"], "package_plan": plan["plan"],
            "package_host_mode": plan["host_mode"],
            "package_tool_projects": json.dumps(plan["tool_projects"], separators=(",", ":")),
            "package_set": json.dumps(plan["package_set"], separators=(",", ":"))}


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


def verify(needs, plan):
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
    return receipt(plan)


def validate_wiring(candidate):
    """Accept one complete reviewed generation; never combine allowed files."""
    candidate = Path(candidate)
    if any(not p.is_dir() or p.is_symlink() for p in (candidate / ".github", candidate / ".github/workflows")):
        raise ValueError("package workflow directories must be ordinary directories")
    tree = {}
    for relative in WORKFLOW_PATHS:
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
    for generation in workflow_generations():
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


def execute(candidate, plan, lane):
    projects = plan["tool_projects"] if lane == "tool-dependencies" else plan["package_set"]
    if lane not in {"tool-dependencies", "package-checks"} or not projects:
        raise ValueError("no independently selected package execution lane")
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
        tools().run(Path(candidate), projects, include_s3=True)
    if _git(candidate, "rev-parse", "HEAD") != plan["candidate"] or _git(candidate, "diff", "--name-only", "HEAD", "--"):
        raise ValueError("package source changed during execution")
    return receipt(plan, lane)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "run", "verify"))
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
        validate_wiring(args.candidate)
        plan = candidate_plan(args.candidate, event, args.sha)
        if args.expected_candidate and args.expected_candidate != plan["candidate"]:
            raise ValueError("package caller candidate mismatch")
        if args.expected_plan and args.expected_plan != plan["plan"]:
            raise ValueError("package caller plan mismatch")
        if args.expected_projects and args.expected_projects != ",".join(plan["tool_projects"]):
            raise ValueError("package caller cannot select arbitrary tool projects")
        if args.command == "plan":
            result = outputs(plan)
        elif args.command == "run":
            result = execute(args.candidate, plan, args.lane)
        else:
            result = verify(json.loads(args.needs_json), plan)
        with args.output.open("a") as output:
            output.write("".join(f"{key}={value}\n" for key, value in result.items()))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, OSError, TypeError, subprocess.SubprocessError) as error:
        print(f"Package checks failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
