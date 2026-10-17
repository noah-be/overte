#!/usr/bin/env python3
"""Complete-generation iOS host owner; no artifact or reuse authority."""
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
import stat
import subprocess
import sys
import tempfile
from urllib.parse import quote
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/ios-host-orchestration.json"
WORKFLOW = ".github/workflows/ios-build-qualification.yml"
TEMPLATE = "tools/ios-build-qualification/host-workflow.yml"
COMPILER_DATA_GENERATION = "host-v1-compiler-data-v1"
COMPILER_DATA_CALLEE = "66892fd2b87b7aa4b0ffe8c12407fc5a7597db44"
# Reviewed execution-only checkpoint update. These identities are comparison
# inputs, never replacements for the actual source snapshots or execution E.
COMPILER_DATA_ORIGINAL = {
    ".github/workflows/ios-integrated.yml": ("100644", "1004d282c847655be7deafced0108ee291e8250c"),
    "ios/ci/qt-checkpoint-artifact.py": ("100755", "4e5ccd1fec2df26a2337bae3fad40e1e48a510a1"),
    "ios/tests/qt-checkpoint-artifact-test.py": ("100755", "af1c253a649677993d14da2972817dcb67644639"),
    "ios/tests/ios-full-client-sccache-contract-test.py": ("100644", "b785011cad8f83f7bf012ec528d93703a1cf47c9"),
    "docs/ios/SIGNING_AND_DEVICE_TESTS.md": ("100644", "776a65d11c637d5a7f0323e1a6ac690defc80b35"),
}
COMPILER_DATA_UPDATED = {
    ".github/workflows/ios-integrated.yml": ("100644", COMPILER_DATA_CALLEE),
    "ios/ci/qt-checkpoint-artifact.py": ("100755", "aaa047eb8a29a1b440a71d6c28503af78f3aaef5"),
    "ios/tests/qt-checkpoint-artifact-test.py": ("100755", "6b52ab115080e204ca3013336abda032e74e95e4"),
    "ios/tests/ios-full-client-sccache-contract-test.py": ("100644", "305a56d5f906101fb728feca59f811278477eb69"),
    "docs/ios/SIGNING_AND_DEVICE_TESTS.md": ("100644", "bb4f69bb29368f04fdc6a6c7ce00b48d92b7f90d"),
}
SOURCE_READY = True
BOOTSTRAP_REVIEWED_SOURCE = "52f1cc38180e96cdfd8049a4be93517961ae7dbd"
BOOTSTRAP_REVIEWED_TREE = "f5b44d19b5c64c96bc3f73f72c51519dbfbf08a3"
REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
SHA = re.compile(r"[0-9a-f]{40}\Z")
PATHS = frozenset({WORKFLOW, ".github/workflows/ios-integrated.yml", ".github/workflows/ios-qt-source.yml",
                   "ios/tests/run-tests.sh", "ios/ci/host-test-network.sh", "tests/requirements-host.txt"})
VARIANTS = ["complete-reviewed-launcher", "Qt6Core/Gui/Qml/Concurrent/WebChannel", "Qt6-script-assets-and-OBJ",
            "Qt5/Qt6-CMake-contracts", "renderer-mutations", "hosted-isolated-network", "Node22"]


# Dependency audit of protected apple-ios 2fc894a and the CI-only rollout.
# These exact files are not imported, discovered, executed or read by the iOS
# product launcher. All other entries, including documentation, native scan
# membership, local imports and historical child differences, remain anchored.
# This proves only that the own host run is unaffected; it is not a passing
# test receipt, shared-owner handoff or application-build selection authority.
REVIEWED_CI_HOST_BOUNDARY = "90da341e226f56b8dfb8b925af7c0273ecc41772ca424e3426b04c80acdb9a7b"
CI_HOST_INDEPENDENT_PATHS = frozenset({
    # Linux-only shared Device launcher; its required Device owner is unchanged.
    "tests/device/run_artifact_identity.py",
    "tools/repository-health/check.py",
    '.github/workflows/documentation-checks.yml',
    '.github/workflows/workflow-security.yml',
    '.github/workflows/documentation-push-owner.yml',
    'tools/test-evidence/source_admission.py',
    'tools/test-evidence/source-admission-test.py',
    'tools/repository-checks/workflows/producers/legacy/parent-qualification-metadata-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/protected-project-tests-metadata-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/repository-checks-metadata-v1.yml',
    ".github/dependency-security.md",
    ".github/test-suite-dependencies.json",
    "tools/test-evidence/affected-test.py",
    "tools/test-evidence/AFFECTED_SELECTION.md",
    'tools/repository-checks/workflows/producers/legacy/repository-checks-protected-ci-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/parent-qualification-postmerge-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/protected-project-tests-ci37-v1.yml',
    'tools/repository-checks/metadata_context.py',
    'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
    'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
    '.github/workflows/pr-metadata-context.yml',
    ".github/shared-sandbox.json",
    ".github/workflows/shared-sandbox-host-diagnostic.yml",
    "tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml",
    "tools/test-evidence/sandbox.py",
    "tools/test-evidence/sandbox-test.py",
    "tools/test-evidence/sandbox_host.py",
    "tools/test-evidence/sandbox-host-test.py",
    "tools/test-evidence/sandbox_host_fixture.py",
    "tools/test-evidence/sandbox_probe.py",
    "tools/test-evidence/sandbox_shared.py",
    "tools/test-evidence/producer_workflow.py",
    "tools/test-evidence/postmerge.py",
    "tests/run-unittest-suite.py",
    "tests/unittest-runner-test.py",
    ".github/ci37-runtime.json",
    "tools/test-evidence/ci_profile.py",
    "tools/test-evidence/runtime_ci.py",
    "tools/test-evidence/ci-profile-test.py",
    "tools/test-evidence/runtime-ci-test.py",
    "tools/test-evidence/ci-integration-test.py",
    "tools/repository-checks/workflows/producers/legacy/protected-project-tests-v1.yml",
    "tools/repository-checks/workflows/producers/legacy/protected-project-tests-postmerge-v1.yml",
    "tools/repository-checks/workflows/producers/protected-project-tests.yml",
    "tools/repository-checks/workflows/producers/repository-checks.yml",
    "tools/repository-checks/workflows/producers/parent-qualification.yml",
    "tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml",
    "tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml",
    ".github/workflows/android-required.yml",
    ".github/android-owner-transfer.json",
    "tests/android-owner-transfer-test.py",
    "tools/repository-checks/android_handoff.py",
    "tools/repository-checks/workflows/android-owned/android-required.yml",
    "tools/repository-checks/workflows/android-owned/handoff/.github/workflows/android-tests.yml",
    "tools/repository-checks/workflows/android-owned/handoff/.github/workflows/android-vr-tests.yml",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/android-workflow-contract-test.py",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/ci/test_ci_contract.py",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/ci/validate_ci_contract.py",
    "tools/repository-checks/workflows/android-owned/project-tests.yml",
    "tools/repository-checks/workflows/android-owned/repository-checks.yml",
    "tools/repository-checks/workflows/android-owned/handoff/android/phone/tests/phone-release-metadata-test.py",
    'tools/repository-checks/workflows/metadata-edits/codeql.yml',
    'tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml',
    'tools/repository-checks/workflows/metadata-edits/repository-checks.yml',
    'tools/repository-checks/workflows/metadata-edits/sync-test-reuse.yml',
    'tools/repository-checks/workflows/sync-ci-selection.yml',
    'tools/repository-checks/npm_consumers.py',
    'tools/repository-checks/npm-source-map-tests.cjs',
    'tools/repository-checks/npm-proxy-addr-tests.cjs',
    'tools/repository-checks/workflows/npm-consumers/browser-client.yml',
    'tools/repository-checks/workflows/npm-consumers/repository-checks.yml',
    '.github/android-checks.json',
    '.github/android-orchestration.json',
    '.github/attested-runtime.json',
    '.github/ios-host-orchestration.json',
    '.github/package-workflow-generations.json',
    '.github/repository-checks.json',
    '.github/sync-test-reuse.json',
    '.github/test-suites.json',
    '.github/workflows/branch-cleanup.yml',
    '.github/workflows/browser-client-atomic-settings.yml',
    '.github/workflows/browser-client.yml',
    '.github/workflows/browser-direct-client.yml',
    '.github/workflows/codeql.yml',
    '.github/workflows/dependency-releases.yml',
    '.github/workflows/parent-qualification.yml',
    '.github/workflows/project-tests.yml',
    '.github/workflows/repository-checks.yml',
    '.github/workflows/repository-health.yml',
    '.github/workflows/sync-test-reuse.yml',
    '.github/workflows/sync-validation.yml',
    'docs/ANDROID_BUILD_INPUTS.md',
    'docs/ATTESTED_RUNTIME_REUSE.md',
    'docs/AUTOMATIC_BRANCH_CLEANUP.md',
    'docs/BRANCH_GOVERNANCE.md',
    'docs/BRANCH_WORKFLOW.md',
    'docs/BROWSER_CPU_SELECTION.md',
    'docs/DEPENDENCY_RELEASES.md',
    'docs/IOS_BUILD_QUALIFICATION.md',
    'docs/PRODUCER_API_PROOF.md',
    'docs/README.md',
    'docs/REPOSITORY_HEALTH.md',
    'tests/PROJECT_TESTING.md',
    'tests/android-build-inputs-test.py',
    'tests/android-ci-test.py',
    'tests/android-orchestration-test.py',
    'tests/branch-cleanup-test.py',
    'tests/branch-policy-test.py',
    'tests/browser-cpu-selection-test.py',
    'tests/codeql-selection-test.py',
    'tests/device/run_control_plane_tests.py',
    'tests/host-producer-preparation-test.py',
    'tests/host-selection-test.py',
    'tests/ios-build-qualification-test.py',
    'tests/ios-input-selection-test.py',
    'tests/native-ci-test.py',
    'tests/project-suite-self-test.py',
    'tests/repository-checks-test.py',
    'tests/repository-health-test.py',
    'tests/run-project-tests.py',
    'tests/workflow-contract-test.py',
    'tools/branch-cleanup/adoption.py',
    'tools/branch-cleanup/cleanup.py',
    'tools/branch-policy/check.py',
    'tools/ios-build-qualification/check.py',
    'tools/ios-build-qualification/fixtures/host-launcher-52f.sh',
    'tools/ios-build-qualification/host-workflow.yml',
    'tools/ios-build-qualification/host.py',
    'tools/ios-build-qualification/inputs.py',
    'tools/native-tests/README.md',
    'tools/native-tests/check.py',
    'tools/repository-checks/android-build-inputs.py',
    'tools/repository-checks/android-host-prepare.sh',
    'tools/repository-checks/android.py',
    'tools/repository-checks/android_gate.py',
    'tools/repository-checks/browser_cpu.py',
    'tools/repository-checks/check.py',
    'tools/repository-checks/codeql.py',
    'tools/repository-checks/codeql_results.py',
    'tools/repository-checks/host_selection.py',
    'tools/repository-checks/package_checks.py',
    'tools/repository-checks/tool_dependencies.py',
    'tools/repository-checks/workflows/android-required.yml',
    'tools/repository-checks/workflows/android/repository-checks-direct-browser.yml',
    'tools/repository-checks/workflows/android/repository-checks.yml',
    'tools/repository-checks/workflows/browser-client.yml',
    'tools/repository-checks/workflows/browser-direct-client.yml',
    'tools/repository-checks/workflows/browser/repository-checks.yml',
    'tools/repository-checks/workflows/codeql-main.json',
    'tools/repository-checks/workflows/codeql-results.yml',
    'tools/repository-checks/workflows/host/parent-qualification.yml',
    'tools/repository-checks/workflows/host/project-tests.yml',
    'tools/repository-checks/workflows/packages/parent-qualification.yml',
    'tools/repository-checks/workflows/packages/project-tests.yml',
    'tools/repository-checks/workflows/packages/repository-checks-direct.yml',
    'tools/repository-checks/workflows/packages/repository-checks.yml',
    'tools/repository-checks/workflows/packages/sync-validation.yml',
    'tools/repository-checks/workflows/producers/project-tests.yml',
    'tools/repository-checks/workflows/repository-checks.yml',
    'tools/sync-test-reuse/differential.py',
    'tools/sync-test-reuse/gate.py',
    'tools/sync-test-reuse/qualification.py',
    'tools/sync-test-reuse/test.py',
    'tools/test-evidence/attested-test.py',
    'tools/test-evidence/attested.py',
    'tools/test-evidence/execution-test.py',
    'tools/test-evidence/execution.py',
    'tools/test-evidence/inputs.py',
    'tools/test-evidence/producer-api-test.py',
    'tools/test-evidence/producer-test.py',
    'tools/test-evidence/producer.py',
    'tools/test-evidence/producer_api.py',
    'tools/test-evidence/qualification-producer-test.py',
    'tools/test-evidence/registry-test.py',
    'tools/test-evidence/run.py',
    'tools/test-evidence/runtime-test.py',
    'tools/test-evidence/runtime.py',
    'tools/test-evidence/test.py',
    'tools/test-evidence/validate-sync-test.py',
    'tools/test-evidence/validate-sync.py',
})
CI_HOST_EXECUTABLE_PATHS = frozenset({
    "tools/repository-health/check.py",
    "tests/project-suite-self-test.py", "tests/repository-health-test.py", "tests/run-project-tests.py",
})
# Outside the iOS host reader graph, but a changed lock additionally requires
# the independently mandatory package owner. Never add these to the CI set.
NPM_HOST_PATHS = frozenset({
    'browser-client/package-lock.json',
    'script-archive/marketplace/S3Server/package-lock.json',
})


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


def package_controller(policy_root):
    path = trusted_file(policy_root, "tools/repository-checks/package_checks.py")
    spec = importlib.util.spec_from_file_location("ios_required_package_controller", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def required_package_owner(event, candidate, source, *, policy_root=ROOT):
    """Recompute the exact mandatory package plan, not an execution receipt.

    A complete five-workflow caller is independently enforced by check.py even
    before the target is listed in the explicit package activation inventory.
    The required repository aggregate still owns the actual successful receipt.
    Missing/unsupported ownership selects the full iOS gate instead of waiving it.
    """
    try:
        module = package_controller(policy_root)
        module.validate_wiring(candidate)
        if not module.consumer_generation(candidate):
            return None
        config = json.loads(trusted_file(policy_root, ".github/repository-checks.json").read_text())
        mandatory = (config.get("repository") == REPOSITORY
                     and type(config.get("repository_id")) is int and config["repository_id"] == REPOSITORY_ID
                     and "repository-checks" in config.get("required_contexts", [])
                     and module.has_staged_caller(candidate))
        if not (module.activated(event) or mandatory):
            return None
        plan = module.candidate_plan(candidate, event, source)
        if plan.get("consumer_generation") is not True or plan.get("candidate") != source:
            return None
        return plan
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError, subprocess.SubprocessError):
        return None


def policy(policy_root=ROOT):
    value = json.loads(trusted_file(policy_root, POLICY).read_text())
    fields = {"schema", "repository", "repositoryId", "activationTargets", "reviewedSource", "legacy", "nextTemplate"}
    require(isinstance(value, dict) and type(value.get("schema")) is int
            and value["schema"] in {1, 2}
            and set(value) == (fields if value["schema"] == 1 else fields | {"reviewedGenerations"})
            and value["repository"] == REPOSITORY and type(value["repositoryId"]) is int
            and value["repositoryId"] == REPOSITORY_ID and value["nextTemplate"] == TEMPLATE
            and isinstance(value["reviewedSource"], str) and SHA.fullmatch(value["reviewedSource"])
            and value["activationTargets"] in ([], ["apple-ios"])
            and isinstance(value["legacy"], dict) and set(value["legacy"]) == PATHS,
            "invalid trusted iOS host generation policy")
    rows = [value["legacy"]]
    if value["schema"] == 2:
        reviewed = value["reviewedGenerations"]
        require(isinstance(reviewed, dict) and set(reviewed) == {COMPILER_DATA_GENERATION},
                "invalid reviewed iOS generation names")
        rows.append(reviewed[COMPILER_DATA_GENERATION])
    for row in rows:
        require(isinstance(row, dict) and set(row) == PATHS, "incomplete reviewed iOS generation")
        for path, entry in row.items():
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
    result = {"legacy": legacy, "host-v1": current}
    if value["schema"] == 2:
        reviewed = value["reviewedGenerations"][COMPILER_DATA_GENERATION]
        expected = {**current, ".github/workflows/ios-integrated.yml": {
            "mode": "100644", "type": "blob", "oid": COMPILER_DATA_CALLEE}}
        require(reviewed == expected and reviewed != current and reviewed != legacy,
                "iOS compiler-data generation must change only the exact reviewed client callee")
        result[COMPILER_DATA_GENERATION] = reviewed
    return result


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
        revisions.append(context(event, candidate, revision)[0])
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
        path = trusted_file(ROOT, "tools/repository-checks/check.py")
        spec = importlib.util.spec_from_file_location("ios_host_candidate_context", path)
        checks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checks)
        try:
            resolved = checks.pr_candidate_context(candidate, event, source)
        except ValueError as exc:
            raise ValueError("iOS host candidate must merge the exact ordered event parents") from exc
        return resolved["base"], resolved["head"]
    require(event.get("ref") in {"apple-ios", "refs/heads/apple-ios"}, "manual iOS host target must be apple-ios")
    return "", source


def workflow_bootstrap(candidate, previous, current, head, *, policy_root=ROOT):
    """Finite source proof, never a new reader anchor or activation authority.

    Only the independently reviewed complete legacy tree can take this route.
    A later reader/host/package edit cannot inherit the bootstrap exception.
    """
    if policy(policy_root)["reviewedSource"] != BOOTSTRAP_REVIEWED_SOURCE \
            or previous.tree != BOOTSTRAP_REVIEWED_TREE or current.tree != head.tree:
        return None
    before, _ = resolve(candidate, previous.revision, policy_root=policy_root)
    after, _ = resolve(candidate, head.revision, policy_root=policy_root)
    if before != "legacy" or after != "host-v1":
        return None
    old, new = entries(previous), entries(current)
    approved = generations(policy_root)
    expected = {**old, WORKFLOW: approved["host-v1"][WORKFLOW]}
    if new != expected or old == new or any(value["mode"] not in {"100644", "100755"}
            or value["type"] != "blob" for value in (*old.values(), *new.values())):
        return None
    return {"schema": 1, "reason": "reviewed-host-v1-workflow-bootstrap", "requires_application_build": False,
            "reviewed_source": BOOTSTRAP_REVIEWED_SOURCE, "reviewed_tree": BOOTSTRAP_REVIEWED_TREE,
            "base": {"revision": previous.revision, "tree": previous.tree},
            "head": {"revision": head.revision, "tree": head.tree},
            "candidate": {"revision": current.revision, "tree": current.tree},
            "workflow": {"path": WORKFLOW, "old": approved["legacy"][WORKFLOW], "new": approved["host-v1"][WORKFLOW]},
            "generations": {name: approved[name] for name in ("legacy", "host-v1")},
            "normalized_inputs": digest([entry.identity() for entry in previous.entries])}


def _api_get(endpoint):
    """Independently read one bounded GitHub fact; never accept artifact claims."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    require(isinstance(token, str) and token, "fresh iOS PR metadata requires the trusted read credential")
    executable = Path("/usr/bin/gh")
    info = executable.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            "fixed trusted GitHub reader is unavailable or mutable")
    try:
        with tempfile.TemporaryDirectory(prefix="overte-ios-github-reader-") as directory:
            result = subprocess.run([str(executable), "api", "--hostname", "github.com", "--method", "GET", endpoint],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "GH_TOKEN": token,
                     "HOME": directory, "GH_CONFIG_DIR": directory, "GH_PROMPT_DISABLED": "1"})
        require(result.returncode == 0 and len(result.stdout) <= 1_000_000 and len(result.stderr) <= 65536,
                "fresh iOS PR GitHub metadata is unavailable or exceeds bounds")
        def unique(pairs):
            value = {}
            for key, item in pairs:
                require(key not in value, "ambiguous fresh iOS PR GitHub metadata")
                value[key] = item
            return value
        value = json.loads(result.stdout, object_pairs_hook=unique)
        require(isinstance(value, dict), "fresh iOS PR GitHub metadata is not one object")
        return value
    except (OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("fresh iOS PR GitHub metadata is unavailable") from error


def fresh_context(event, candidate, source, *, policy_root=ROOT):
    """Trusted CLI bookend: actual GETs and local immutable parents must agree.

    JSON supplied by a workflow/caller is never accepted as a fresh API proof.
    Pure route/report APIs still need these CLI bookends at deployment.
    """
    base, head = context(event, candidate, source)
    require(SOURCE_READY and "apple-ios" in policy(policy_root)["activationTargets"],
            "iOS host-only generation is not qualified or activated")
    number = event.get("number")
    pr = event.get("pull_request", {})
    require(base and type(number) is int and number > 0 and type(pr.get("number")) is int
            and pr["number"] == number, "fresh iOS PR number is missing or inconsistent")
    branch = pr["head"].get("ref")
    require(isinstance(branch, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch)
            and not any(part in {"", ".", ".."} for part in branch.split("/")), "unsupported current iOS PR head ref")
    prefix = "repos/" + REPOSITORY
    live = _api_get(prefix + "/pulls/" + str(number))
    require(type(live.get("number")) is int and live["number"] == number and live.get("state") == "open"
            and live.get("merged") is False and live.get("merge_commit_sha") in (None,source),
            "iOS PR is closed or its current merge candidate changed")
    guard_path = trusted_file(policy_root, "tools/test-evidence/source_admission.py")
    spec = importlib.util.spec_from_file_location("ios_fresh_source_context", guard_path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    api = SimpleNamespace(get=lambda endpoint: _api_get(prefix+"/"+endpoint))
    merge = api.get("commits/refs/pull/"+str(number)+"/merge")
    resolved = guard.resolve_pr_base(api, live, merge, pr)
    require(resolved["source"] == source and resolved["base"] == base and resolved["head"] == head,
            "current iOS PR protected base/head/candidate changed")
    return {"repository": REPOSITORY, "repositoryId": REPOSITORY_ID, "number": number,
            "baseRef": "apple-ios", "base": base, "headRef": branch, "head": head, "candidate": source}


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


def ci_host_boundary(snapshot):
    """Bind the complete reviewed reader complement, including path absence."""
    if any(entry.mode not in {"100644", "100755"} or entry.object_type != "blob"
           for entry in snapshot.entries):
        return None
    values = [entry.identity() for entry in sorted(snapshot.entries)
              if entry.path not in CI_HOST_INDEPENDENT_PATHS | NPM_HOST_PATHS]
    return hashlib.sha256((json.dumps(values, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False) + "\n").encode()).hexdigest()


def _compiler_profile(snapshot, profile, *, guide=True):
    observed = entries(snapshot)
    return all(observed.get(path) == {"mode": mode, "type": "blob", "oid": oid}
               for path, (mode, oid) in profile.items()
               if guide or path != "docs/ios/SIGNING_AND_DEVICE_TESTS.md")


def _compiler_comparison(snapshot, inputs, *, guide=False):
    """Temporary original-reader comparison; retain the actual snapshot intact."""
    replaced = tuple(inputs.Entry(entry.path, COMPILER_DATA_ORIGINAL[entry.path][0], "blob",
                                  COMPILER_DATA_ORIGINAL[entry.path][1])
                     if entry.path in COMPILER_DATA_ORIGINAL
                     and (guide or entry.path != "docs/ios/SIGNING_AND_DEVICE_TESTS.md")
                     else inputs.Entry(entry.path, entry.mode, entry.object_type, entry.oid)
                     for entry in snapshot.entries)
    return inputs.Snapshot(snapshot.revision, snapshot.tree, replaced)


def compiler_data_selection(previous, current, head, *, policy_root=ROOT):
    """Exact reviewed cache transition/continuation; no product result authority."""
    inputs = selector(policy_root)
    snapshots = (previous, current, head)
    if any(entry.mode not in {"100644", "100755"} or entry.object_type != "blob"
           for snapshot in snapshots for entry in snapshot.entries):
        return None
    approved = generations(policy_root)
    updated = approved.get(COMPILER_DATA_GENERATION)
    if updated is None:
        return None
    observed = [entries(snapshot) for snapshot in snapshots]
    matches = lambda tree, row: all(tree.get(path) == identity for path, identity in row.items())
    changed = [{path for path in observed[0].keys() | tree.keys() if observed[0].get(path) != tree.get(path)}
               for tree in observed[1:]]
    transition = (matches(observed[0], approved["host-v1"])
        and _compiler_profile(previous, COMPILER_DATA_ORIGINAL)
        and all(matches(tree, updated) and _compiler_profile(snapshot, COMPILER_DATA_UPDATED)
                for tree, snapshot in zip(observed[1:], snapshots[1:]))
        and all(paths == set(COMPILER_DATA_ORIGINAL) for paths in changed))
    continuation = (all(matches(tree, updated) and _compiler_profile(snapshot, COMPILER_DATA_UPDATED, guide=False)
                        for tree, snapshot in zip(observed, snapshots))
        and all(paths for paths in changed)
        and all(inputs._kind(entry) != "application-input" for snapshot, paths in zip(snapshots[1:], changed)
                for entry in (*previous.entries, *snapshot.entries) if entry.path in paths))
    if not (transition or continuation) or any(inputs._boundary(_compiler_comparison(snapshot, inputs))
            != inputs.REVIEWED_BOUNDARY for snapshot in snapshots):
        return None
    return {"schema": 1, "reason": "reviewed-compiler-data-only-inputs" if transition
            else "reviewed-compiler-data-independent-inputs", "requires_application_build": False,
            "reviewed_boundary": inputs.REVIEWED_BOUNDARY, "comparison_profile": digest(COMPILER_DATA_UPDATED),
            "base": {"revision": previous.revision, "tree": previous.tree},
            "head": {"revision": head.revision, "tree": head.tree},
            "candidate": {"revision": current.revision, "tree": current.tree},
            "changedPaths": sorted(changed[0])}


def ci_host_omission(previous, current, *, repository=None, package_owner=None, policy_root=ROOT, head=None):
    """Finite negative dependency proof; never infer independence from app inputs."""
    old, new = entries(previous), entries(current)
    changed = {path for path in old.keys() | new.keys() if old.get(path) != new.get(path)}
    if not changed or not changed <= CI_HOST_INDEPENDENT_PATHS | NPM_HOST_PATHS:
        return None
    npm = None
    if changed & NPM_HOST_PATHS:
        if repository is None:
            return None
        npm = selector(policy_root).npm_package_admission(repository, previous, current, package_owner)
        if npm is None or set(npm["changedPaths"]) != changed & NPM_HOST_PATHS:
            return None
    if any((old[path]["mode"], old[path]["type"]) != (new[path]["mode"], new[path]["type"])
           for path in changed if path in old and path in new):
        return None
    if any(value["mode"] != ("100755" if path in CI_HOST_EXECUTABLE_PATHS else "100644")
           or value["type"] != "blob" for tree in (old, new) for path, value in tree.items()
           if path in CI_HOST_INDEPENDENT_PATHS | NPM_HOST_PATHS):
        return None
    comparison = None
    if any(ci_host_boundary(snapshot) != REVIEWED_CI_HOST_BOUNDARY for snapshot in (previous, current)):
        inputs = selector(policy_root)
        updated = generations(policy_root).get(COMPILER_DATA_GENERATION)
        snapshots = (previous, current, head)
        if head is None or updated is None or any(not _compiler_profile(snapshot, COMPILER_DATA_UPDATED)
                or any(entries(snapshot).get(path) != identity for path, identity in updated.items())
                or ci_host_boundary(_compiler_comparison(snapshot, inputs, guide=True)) != REVIEWED_CI_HOST_BOUNDARY
                for snapshot in snapshots):
            return None
        comparison = {"profile": digest(COMPILER_DATA_UPDATED), "head": {"revision": head.revision, "tree": head.tree},
                      "actual_boundaries": [ci_host_boundary(snapshot) for snapshot in snapshots]}
    result = {"schema": 1, "reason": "reviewed-ci-only-host-inputs" if npm is None
              else "reviewed-ci-and-required-npm-host-inputs",
            "boundary": REVIEWED_CI_HOST_BOUNDARY, "changedPaths": sorted(changed),
            "base": {"revision": previous.revision, "tree": previous.tree},
            "candidate": {"revision": current.revision, "tree": current.tree}}
    if npm is not None:
        result["package_ownership"] = npm
    if comparison is not None:
        result["compiler_data_comparison"] = comparison
    return result


def route(event, candidate, source, *, policy_root=ROOT):
    base, head = context(event, candidate, source)
    generation, current = resolve(candidate, source, policy_root=policy_root)
    require(generation in {"host-v1", COMPILER_DATA_GENERATION},
            "iOS next-generation ownership cannot roll back to legacy")
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
            old, new = entries(previous), entries(current)
            npm_changed = any(old.get(path) != new.get(path) for path in NPM_HOST_PATHS)
            package_owner = required_package_owner(event, candidate, source, policy_root=policy_root) if npm_changed else None
            selection = workflow_bootstrap(candidate, previous, current, head_source, policy_root=policy_root)
            if selection is None:
                selection = compiler_data_selection(previous, current, head_source, policy_root=policy_root)
            if selection is None:
                selection = inputs.candidate_plan(candidate, base, source, package_owner=package_owner)
            required, host_required = selection["requires_application_build"], True
            reason = selection["reason"]
            omission = None if required else ci_host_omission(previous, current, repository=candidate,
                package_owner=package_owner, policy_root=policy_root, head=head_source)
            if omission is not None:
                host_required = False
                reason = omission["reason"]
                selection = {**selection, "host_omission": omission}
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
