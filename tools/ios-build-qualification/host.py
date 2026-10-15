#!/usr/bin/env python3
"""Dormant complete-generation iOS host owner; no artifact or reuse authority."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/ios-host-orchestration.json"
WORKFLOW = ".github/workflows/ios-build-qualification.yml"
TEMPLATE = "tools/ios-build-qualification/host-workflow.yml"
SOURCE_READY = False
REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
SHA = re.compile(r"[0-9a-f]{40}\Z")
PATHS = frozenset({WORKFLOW, ".github/workflows/ios-integrated.yml", ".github/workflows/ios-qt-source.yml",
                   "ios/tests/run-tests.sh", "ios/ci/host-test-network.sh", "tests/requirements-host.txt"})
VARIANTS = ["complete-reviewed-launcher", "Qt6Core/Gui/Qml/Concurrent/WebChannel", "Qt6-script-assets-and-OBJ",
            "Qt5/Qt6-CMake-contracts", "renderer-mutations", "hosted-isolated-network", "Node22"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                                 allow_nan=False).encode()).hexdigest()


def git(candidate, *arguments, data=None):
    return subprocess.run(["git", "--no-replace-objects", "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                           *arguments], cwd=candidate, input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=30, check=True).stdout


def trusted_file(root, relative):
    root = Path(root)
    path = root / relative
    require(not any(item.is_symlink() for item in (path, *path.parents) if item.is_relative_to(root))
            and path.is_file(), "trusted iOS host policy source is unavailable")
    return path


def selector(policy_root):
    path = trusted_file(policy_root, "tools/ios-build-qualification/inputs.py")
    spec = importlib.util.spec_from_file_location("ios_host_trusted_inputs", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def policy(policy_root=ROOT):
    value = json.loads(trusted_file(policy_root, POLICY).read_text())
    require(isinstance(value, dict) and set(value) == {"schema", "repository", "repositoryId", "activationTargets",
            "reviewedSource", "legacy", "nextTemplate"} and type(value["schema"]) is int and value["schema"] == 1
            and value["repository"] == REPOSITORY and type(value["repositoryId"]) is int
            and value["repositoryId"] == REPOSITORY_ID and value["nextTemplate"] == TEMPLATE
            and isinstance(value["reviewedSource"], str) and SHA.fullmatch(value["reviewedSource"])
            and value["activationTargets"] in ([], ["apple-ios"])
            and isinstance(value["legacy"], dict) and set(value["legacy"]) == PATHS,
            "invalid trusted iOS host generation policy")
    for path, entry in value["legacy"].items():
        require(isinstance(entry, dict) and set(entry) == {"mode", "type", "oid"}
                and entry["mode"] == ("100755" if path in {"ios/tests/run-tests.sh", "ios/ci/host-test-network.sh"}
                                      else "100644") and entry["type"] == "blob"
                and isinstance(entry["oid"], str) and SHA.fullmatch(entry["oid"]),
                "invalid reviewed iOS source identity")
    return value


def generations(policy_root=ROOT):
    value = policy(policy_root)
    legacy = value["legacy"]
    next_source = trusted_file(policy_root, TEMPLATE).read_bytes()
    oid = git(policy_root, "hash-object", "--stdin", data=next_source).decode().strip()
    current = {**legacy, WORKFLOW: {"mode": "100644", "type": "blob", "oid": oid}}
    return {"legacy": legacy, "host-v1": current}


def entries(snapshot):
    return {entry.path: {key: entry.identity()[key] for key in ("mode", "type", "oid")}
            for entry in snapshot.entries}


def resolve(candidate, revision, *, policy_root=ROOT):
    source = selector(policy_root).read_snapshot(candidate, revision)
    observed = entries(source)
    matches = [name for name, approved in generations(policy_root).items()
               if all(observed.get(path) == identity for path, identity in approved.items())]
    require(len(matches) == 1, "iOS source does not match one complete reviewed generation")
    return matches[0], source


def participates(candidate, revision, event, *, policy_root=ROOT):
    """Either protected-base or candidate next source requires next admission."""
    inputs = selector(policy_root)
    approved = generations(policy_root)["host-v1"][WORKFLOW]
    revisions = [revision]
    if event.get("pull_request") is not None:
        revisions.append(event["pull_request"]["base"]["sha"])
    return any(entries(inputs.read_snapshot(candidate, item)).get(WORKFLOW) == approved for item in revisions)


def context(event, candidate, source):
    repo = event.get("repository", {})
    require(repo.get("full_name") == REPOSITORY and type(repo.get("id")) is int and repo["id"] == REPOSITORY_ID,
            "foreign iOS host repository")
    require(isinstance(source, str) and SHA.fullmatch(source)
            and git(candidate, "rev-parse", "HEAD").decode().strip() == source, "wrong iOS host candidate")
    pr = event.get("pull_request")
    if pr is not None:
        require(isinstance(pr, dict), "invalid iOS host PR")
        for side in ("base", "head"):
            item = pr.get(side, {})
            require(item.get("repo", {}).get("full_name") == REPOSITORY
                    and type(item.get("repo", {}).get("id")) is int and item["repo"]["id"] == REPOSITORY_ID
                    and isinstance(item.get("sha"), str) and SHA.fullmatch(item["sha"]), "foreign iOS host PR source")
        require(pr["base"].get("ref") == "apple-ios", "iOS host target must be apple-ios")
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        require(git(candidate, "show", "-s", "--format=%P", source).decode().split() == [base, head],
                "iOS host candidate must merge the exact ordered event parents")
        return base, head
    require(event.get("ref") in {"apple-ios", "refs/heads/apple-ios"}, "manual iOS host target must be apple-ios")
    return "", source


def host_inventory(candidate, snapshot, *, policy_root=ROOT):
    """The full Git tree binds all transitive tests, fixtures and native variants."""
    document = policy(policy_root)
    launcher = git(candidate, "cat-file", "blob", document["legacy"]["ios/tests/run-tests.sh"]["oid"]).decode()
    literal = re.findall(r'\$script_dir/([^"$\s]+\.(?:py|cjs|sh|cmake))', launcher)
    rendering = re.search(r"readonly rendering_contracts=\(\n(.*?)\n\)", launcher, re.S)
    require(rendering is not None, "reviewed iOS host renderer inventory is missing")
    literal += re.findall(r"^    ([a-z0-9-]+\.py)$", rendering[1], re.M)
    required = {posixpath.normpath("ios/tests/" + name) for name in literal}
    observed = entries(snapshot)
    for directory in ("ios/release-check/", "tests/device/ios/self_tests/"):
        discovery = [path for path in observed if path.startswith(directory) and Path(path).name.startswith("test_")
                     and path.endswith(".py")]
        require(discovery, "iOS host discovery would execute no tests")
        required.update(discovery)
    require(len(required) >= 150, "incomplete reviewed iOS host command inventory")
    for path in required:
        require(path in observed and observed[path]["mode"] in {"100644", "100755"}
                and observed[path]["type"] == "blob", "iOS host source closure is missing or nonregular: " + path)
    return digest({"domain": "ios-complete-host-inputs-v1", "entries": [entry.identity() for entry in snapshot.entries],
                   "entrypoints": sorted(required), "variants": VARIANTS})


def route(event, candidate, source, *, policy_root=ROOT):
    base, head = context(event, candidate, source)
    generation, current = resolve(candidate, source, policy_root=policy_root)
    require(generation == "host-v1", "iOS next-generation ownership cannot roll back to legacy")
    require(SOURCE_READY and "apple-ios" in policy(policy_root)["activationTargets"],
            "iOS host-only generation is not qualified or activated")
    inputs = selector(policy_root)
    if base:
        previous = inputs.read_snapshot(candidate, base)
        head_source = inputs.read_snapshot(candidate, head)
        if previous.tree == current.tree == head_source.tree:
            reason, required, host_required = "unchanged-tree", False, False
            selection = {"tree": current.tree, "base": base, "head": head, "candidate": source}
        else:
            selection = inputs.candidate_plan(candidate, base, source)
            required, host_required = selection["requires_application_build"], True
            reason = selection["reason"]
    else:
        selection = inputs.input_fingerprint(candidate, source)
        reason, required, host_required = "manual-application-build-required", True, True
    host_inputs = host_inventory(candidate, current, policy_root=policy_root)
    generation_id = digest({"name": generation, "sources": generations(policy_root)[generation]})
    plan = digest({"selection": selection, "generation": generation_id, "host_inputs": host_inputs,
                   "controller": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "policy": policy(policy_root)})
    return {"required": str(required).lower(), "host_required": str(host_required).lower(), "source": source,
            "tree": current.tree, "base": base, "head": head, "reason": reason,
            "generation": generation_id, "selection": plan, "host_inputs": host_inputs}


def stamp(value):
    require(isinstance(value, str), "missing iOS host execution timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.utcoffset() is not None, "iOS host timestamp must include its timezone")
    return result


def verify_execution(jobs, run, run_id, attempt, head):
    """First-attempt proof only; retry snapshots cannot establish original execution."""
    require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0
            and isinstance(head, str) and SHA.fullmatch(head), "invalid iOS host qualifier identity")
    require(attempt == 1, "iOS host proof supports the first attempt only; original retry execution is not authenticated")
    require(isinstance(run, dict) and type(run.get("id")) is int and run["id"] == run_id
            and type(run.get("run_attempt")) is int and run["run_attempt"] == attempt
            and run.get("head_sha") == head and run.get("path") == WORKFLOW,
            "iOS host run/source/attempt mismatch")
    require(run.get("repository", {}).get("full_name") == REPOSITORY
            and type(run.get("repository", {}).get("id")) is int
            and run["repository"]["id"] == REPOSITORY_ID, "foreign iOS host producer")
    require(isinstance(jobs, list), "missing actual iOS host jobs")
    selected = [job for job in jobs if job.get("name") == "iOS host contracts"]
    require(len(selected) == 1, "missing or duplicate actual iOS host producer")
    job = selected[0]
    require(type(job.get("id")) is int and job["id"] > 0 and type(job.get("run_id")) is int
            and job["run_id"] == run_id and type(job.get("run_attempt")) is int
            and job["run_attempt"] == attempt and job.get("head_sha") == head
            and job.get("status") == "completed" and job.get("conclusion") == "success",
            "iOS host producer did not succeed for this run/source/attempt")
    selected_steps = [step for step in job.get("steps", []) if step.get("name") == "Run iOS host contracts"]
    require(len(selected_steps) == 1 and selected_steps[0].get("status") == "completed"
            and selected_steps[0].get("conclusion") == "success", "actual iOS host execution step is missing or skipped")
    step = selected_steps[0]
    require(stamp(run.get("run_started_at")) <= stamp(job.get("started_at")) <= stamp(step.get("started_at"))
            < stamp(step.get("completed_at")) <= stamp(job.get("completed_at")),
            "iOS host execution is outside the authenticated current attempt")
    return {"runId": run_id, "originalExecutionRunAttempt": attempt, "originalExecutionJobId": job["id"],
            "apiSnapshotRunAttempt": attempt, "step": "Run iOS host contracts"}


def preflight(candidate, runner=subprocess.run):
    for executable in ("bash", "python3", "node", "c++", "cmake", "pkg-config", "qtpaths6"):
        require(shutil.which(executable), "mandatory iOS host executable is missing: " + executable)
    runner(["pkg-config", "--exists", "Qt6Core", "Qt6Gui", "Qt6Qml", "Qt6Concurrent", "Qt6WebChannel", "vulkan", "glm"],
           check=True, timeout=30)
    qml = runner(["qtpaths6", "--query", "QT_INSTALL_QML"], check=True, capture_output=True, text=True, timeout=30)
    for module in ("QtQml", "QtQml/Models", "QtQml/WorkerScript", "QtQuick", "QtQuick/Controls", "QtQuick/Layouts",
                   "QtQuick/Templates", "QtQuick/Window", "Qt/labs/settings", "Qt/labs/folderlistmodel", "QtQuick/Dialogs", "QtTest"):
        require((Path(qml.stdout.strip()) / module / "qmldir").is_file(), "mandatory iOS QML module is missing: " + module)
    expected = "/usr/lib/qt6/bin/qmltestrunner"
    require(os.environ.get("OVERTE_QML_TEST_RUNNER") == expected and os.access(expected, os.X_OK),
            "mandatory iOS QML runner is missing")
    for path in ("/usr/lib/qt6/libexec/moc", "/usr/lib/qt6/libexec/rcc"):
        require(os.access(path, os.X_OK), "mandatory iOS Qt host compiler tool is missing: " + path)
    require(os.environ.get("OVERTE_HOST_TEST_NETWORK_RUNNER") == str(Path(candidate).resolve() / "ios/ci/host-test-network.sh"),
            "reviewed iOS network wrapper is not selected")
    node = runner(["node", "--version"], check=True, capture_output=True, text=True, timeout=30)
    require(re.fullmatch(r"v22\.[0-9]+\.[0-9]+\s*", node.stdout), "mandatory iOS Node 22 runtime is missing")
    runner([sys.executable, "-m", "pip", "check"], check=True, timeout=30)


@contextmanager
def candidate_environment():
    """Candidate children cannot rewrite Actions commands or inherit API tokens."""
    names = {"GH_TOKEN", "GITHUB_TOKEN", "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STATE",
             "GITHUB_STEP_SUMMARY", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_RUNTIME_URL", "ACTIONS_CACHE_URL",
             "ACTIONS_RESULTS_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_URL"}
    names.update(name for name in os.environ if name.startswith(("GIT_CONFIG_", "OVERTE_")))
    fixed = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
             "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0", "QT_QPA_PLATFORM": "offscreen"}
    # These two exact runner selections are independently checked by preflight.
    fixed.update({name: os.environ[name] for name in ("OVERTE_QML_TEST_RUNNER", "OVERTE_HOST_TEST_NETWORK_RUNNER")
                  if name in os.environ})
    previous = {name: os.environ.get(name) for name in names | set(fixed)}
    try:
        for name in names:
            os.environ.pop(name, None)
        os.environ.update(fixed)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def execute(event, candidate, source, *, policy_root=ROOT):
    before = route(event, candidate, source, policy_root=policy_root)
    require(before["host_required"] == "true", "unselected iOS host execution")
    with candidate_environment():
        git(candidate, "diff", "--no-ext-diff", "--quiet", "HEAD", "--")
        preflight(candidate)
        subprocess.run(["bash", "ios/tests/run-tests.sh"], cwd=candidate, check=True)
        git(candidate, "diff", "--no-ext-diff", "--quiet", "HEAD", "--")
    require(route(event, candidate, source, policy_root=policy_root) == before,
            "iOS host source plan changed during execution")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run"])
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        event = json.loads(args.event.read_text())
        execute(event, args.candidate, args.sha)
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f"iOS host ownership failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
