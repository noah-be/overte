#!/usr/bin/env python3
"""Offline routing and fail-closed aggregation for required repository checks."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
MODES = {"full", "documentation", "tool-dependencies", "delegated-sync"}
DIRECT_WORKFLOWS = ("repository-checks.yml", "browser-direct-client.yml")
DIRECT_NATIVE_FIXTURES = frozenset({
    "browser-direct-client/tests/fixtures/native-wire.json",
    "browser-direct-client/tests/fixtures/native-avatar-audio.json",
})
DIRECT_HOST_NPM_MANIFESTS = frozenset({
    "script-archive/marketplace/S3Server/package.json",
    "script-archive/marketplace/S3Server/package-lock.json",
})
DIRECT_BROWSER_ASSETS = frozenset({
    "LICENSE", "LICENSES/Apache-2.0.txt",
    "interface/resources/meshes/defaultAvatar_full.fst",
    "interface/resources/meshes/mannequin/mannequin.fbx",
    "interface/resources/meshes/mannequin/lambert1_Base_Color.png",
    "interface/resources/meshes/mannequin/lambert1_Normal_OpenGL.png",
    "interface/resources/meshes/mannequin/lambert1_Roughness.png",
    "interface/resources/meshes/mannequin/Eyes.png",
})
DIRECT_HOST_ROOTS = (
    "docs/", "android/", "ios/", "scripts/", "unpublishedScripts/", "server-console/",
    "browser-client/", "interface/", "launchers/", "pkg-scripts/", "provenance/", "tests/",
    "tools/branch-", "tools/repository-", "tools/sync-test-reuse/", "tools/workflow-security/",
    "tools/issue-intake/", "tools/dependency-releases/", "tools/release/", "tools/sbom/",
    "tools/ios-build-qualification/", "tools/jsdoc/",
)
DIRECT_FRONTEND_SUFFIXES = frozenset({
    ".ts", ".mts", ".tsx", ".js", ".mjs", ".css", ".json", ".html", ".py", ".txt",
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".wasm", ".fbx", ".fst",
    ".bin", ".ktx", ".ktx2", ".woff", ".woff2", ".mp3", ".wav", ".ogg",
})
DIRECT_UNRELATED_NATIVE_TOOLS = frozenset({
    "tools/native-tests/check.py", "tools/native-tests/run.py", "tools/native-tests/qt-test.py",
    "tools/native-tests/shader-cache.py", "tools/native-tests/configure.sh",
    "tools/native-tests/package-image.Dockerfile",
})


def tool_dependency_projects(paths: list[str], regular: bool) -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location(
        "tool_dependencies", ROOT / "tools/repository-checks/tool_dependencies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.affected_projects(paths, regular)


def metadata_edit(event: dict, event_name: str) -> bool:
    """Recognize a PR text edit, without authorizing qualification omission.

    GitHub reports retargets in changes.base. Admit only the complete known
    title/body shapes; a future edit field or incomplete event keeps the normal
    required jobs. No PR text, label or attestation grants execution evidence.
    """
    if event_name not in {"pull_request", "pull_request_target"} or not isinstance(event, dict) \
            or event.get("action") != "edited":
        return False
    repository, pr, changes = event.get("repository"), event.get("pull_request"), event.get("changes")
    if not isinstance(repository, dict) or repository.get("full_name") != "noah-l-frank/overte" \
            or type(repository.get("id")) is not int or repository["id"] != 1319052603 \
            or not isinstance(pr, dict) or type(event.get("number")) is not int or event["number"] < 1 \
            or type(pr.get("number")) is not int or pr["number"] != event["number"] \
            or pr.get("state") != "open" or not isinstance(changes, dict) or not changes \
            or not set(changes) <= {"title", "body"}:
        return False
    for side in ("base", "head"):
        identity = pr.get(side)
        if not isinstance(identity, dict) or not isinstance(identity.get("ref"), str) or not identity["ref"] \
                or not isinstance(identity.get("sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", identity["sha"]) \
                or identity["sha"] == "0" * 40:
            return False
    base_repository = pr["base"].get("repo")
    if not isinstance(base_repository, dict) or base_repository.get("full_name") != repository["full_name"] \
            or type(base_repository.get("id")) is not int or base_repository["id"] != repository["id"]:
        return False
    for key, change in changes.items():
        if not isinstance(change, dict) or set(change) != {"from"}:
            return False
        allowed = (str, type(None)) if key == "body" else (str,)
        if not isinstance(change["from"], allowed) or key not in pr or not isinstance(pr[key], allowed):
            return False
    return True


def classify_metadata_event(path: Path, event_name: str) -> dict:
    """Classify text edits while retaining normal qualification without proof.

    A source-head check can remain green when the trusted default-branch policy
    changes without changing a child PR's base or head. Event shape therefore
    cannot prove that the current merge candidate and policy were qualified.
    Omission must remain unavailable until an authenticated qualification owner
    verifies that complete context; this classifier never supplies such proof.
    """
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate event field")
            result[key] = value
        return result
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
            raise ValueError("metadata event is unavailable or oversized")
        event = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite event")))
        metadata = metadata_edit(event, event_name)
    except (ValueError, OSError, TypeError, AttributeError):
        metadata = False
    intent = os.environ.get('NATIVE_METADATA_INTENT', '')
    if intent not in {'', 'false', 'true'}:
        raise ValueError('invalid native metadata lane state')
    if intent == 'true':
        if not metadata:
            raise ValueError('marked metadata lane no longer has a complete known event')
        # This reviewed reusable-job output selects a one-way branch, not proof.
        # The owner independently authenticates its native marker/source before
        # retaining anything. No failure can fall through to a producer.
        result = _retained_metadata(event)
        if not isinstance(result, dict) or result.get('metadata_only') != 'true' \
                or result.get('qualification') is not False:
            raise ValueError('current retained metadata qualification unavailable')
        return {**result, 'metadata_edit': True}
    return {"kind": "pr-metadata-classification", "qualification": False,
            "metadata_edit": metadata, "metadata_only": "false"}


def _retained_metadata(event):
    """Dispatch only from native caller identity, never a supplied selector."""
    reference = os.environ.get('GITHUB_WORKFLOW_REF')
    number = event['number']
    suffix = '@refs/pull/' + str(number) + '/merge'
    sys.path.insert(0, str(ROOT / 'tools/test-evidence'))
    if reference == 'noah-l-frank/overte/.github/workflows/repository-checks.yml' + suffix:
        import postmerge
        import producer_api
        return postmerge.verify_metadata(event, os.environ, producer_api.Adapter(), root=ROOT)
    if reference == 'noah-l-frank/overte/.github/workflows/codeql.yml' + suffix:
        spec = importlib.util.spec_from_file_location('trusted_metadata_codeql_results',
            ROOT / 'tools/repository-checks/codeql_results.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.MetadataVerifier(ROOT, event, os.environ).verify()
    raise ValueError('metadata caller is not a reviewed native workflow')


def configuration(root: Path = ROOT) -> tuple[dict, dict]:
    config = json.loads((root / ".github/repository-checks.json").read_text())
    branches = json.loads((root / ".github/branch-policy.json").read_text())["branches"]
    if (config.get("schema") != 1 or config.get("repository") != "noah-l-frank/overte"
            or config.get("repository_id") != 1319052603
            or config.get("documentation_suffixes") != [".md"]
            or not config.get("workflow_security_paths")):
        raise ValueError("invalid repository-check configuration")
    if type(config.get("native_required", False)) is not bool:
        raise ValueError("invalid native activation setting")
    for key in ("native_required_branches", "direct_browser_required_branches", "package_checks_required_branches",
                "browser_client_required_branches", "codeql_results_required_branches"):
        targets = config.get(key, [])
        if (not isinstance(targets, list) or any(not isinstance(name, str) or name not in branches for name in targets)
                or len(targets) != len(set(targets))):
            raise ValueError(f"invalid {key} activation targets")
    expected = {"dependency-release-policy", "branch-policy", "sync-test-reuse", "repository-checks"}
    if set(config.get("required_contexts", [])) != expected:
        raise ValueError("aggregate and independent synchronization gates must remain required")
    return config, branches


def direct_browser_plan(paths: list[str], regular: bool = True, *, verified_empty: bool = False) -> dict:
    """Separate browser inputs from the optional native server/test build.

    The native lane compiles domain-server, assignment-client, networking and
    browser transport tests, including avatars/audio/shared and their transitive
    server libraries. Library ownership is conservative until a configured graph
    proves a narrower closure. Known browser tooling/UI never requires that build.
    """
    reasons = {"browser": [], "native": []}
    if verified_empty:
        if paths:
            raise ValueError("verified empty direct-browser delta contains paths")
        return {"browser": False, "native": False, "reasons": reasons}
    if not regular or not paths:
        reason = "non-regular input" if not regular else "unverified change inventory"
        return {"browser": True, "native": True,
                "reasons": {lane: [reason] for lane in reasons}}
    for path in paths:
        if not isinstance(path, str):
            raise ValueError("invalid direct-browser changed path")
        name = PurePosixPath(path)
        if (not isinstance(path, str) or not path or "\x00" in path or "\\" in path
                or name.is_absolute() or ".." in name.parts):
            raise ValueError("invalid direct-browser changed path")
        if name.suffix == ".md":
            continue
        if path in DIRECT_UNRELATED_NATIVE_TOOLS:
            # These drive the ordinary lane or build a future immutable image;
            # ci-native.py does not import/execute them in its current context.
            continue
        if (path.startswith("tools/test-evidence/")
                and name.suffix in {".py", ".json"}):
            continue
        browser = native = False
        if path in DIRECT_NATIVE_FIXTURES:
            browser = native = True
        elif path == "browser-direct-client/tools/ci-native.py":
            native = True
        elif (name.name == "CMakeLists.txt" or name.suffix in {".cmake", ".qrc"}
              or path in {"conanfile.py", "conan.lock", ".gitmodules", ".github/native-tests.json"}
              or path.startswith(("cmake/", "tools/conan-profiles/", "tools/native-tests/",
                                  ".github/actions/conan-install/", "tests/browser-direct-transport/",
                                  "tests/networking/", "libraries/", "assignment-client/", "domain-server/"))):
            native = True
            browser = path.startswith("libraries/networking/") or path == "libraries/shared/src/Constants.h"
        elif path == ".github/workflows/browser-direct-client.yml":
            # A changed runner/toolchain is a new execution context.
            browser = native = True
        elif path.startswith("browser-direct-client/"):
            # C/C++ and unknown inputs are deliberately not frontend exemptions.
            known_root = name.parts[1] in {"src", "shared", "tests", "tools", "lab", "e2e", "public"}
            known_file = path in {"browser-direct-client/package.json", "browser-direct-client/package-lock.json",
                                 "browser-direct-client/tsconfig.json", "browser-direct-client/vendor-sdk.json",
                                 "browser-direct-client/reuse-manifest.json", "browser-direct-client/index.html",
                                 "browser-direct-client/vite.config.ts"}
            browser = True
            native = not ((known_root or known_file) and name.suffix in DIRECT_FRONTEND_SUFFIXES)
        elif path in DIRECT_BROWSER_ASSETS:
            browser = True
        elif (path in DIRECT_HOST_NPM_MANIFESTS
              or path.startswith(DIRECT_HOST_ROOTS) or path.startswith(".github/")
              or path in {"COPYING", ".gitignore", ".gitattributes", "requirements.txt", "AGENTS.md"}):
            continue
        else:
            browser = native = True  # Unowned inputs cannot obtain a silent pass.
        for lane, selected in (("browser", browser), ("native", native)):
            if selected:
                reasons[lane].append(path)
    return {lane: bool(reasons[lane]) for lane in reasons} | {"reasons": reasons}


def direct_browser_required(config: dict, event: dict | None) -> bool:
    targets = config.get("direct_browser_required_branches", [])
    if not targets:
        return False
    if not isinstance(event, dict):
        raise ValueError("direct-browser activation requires a trusted event")
    repository = event.get("repository") or {}
    if (repository.get("full_name") != config["repository"]
            or repository.get("id") != config["repository_id"]):
        raise ValueError("direct-browser activation repository mismatch")
    pr = event.get("pull_request")
    if pr is None:
        return True
    base = pr.get("base") or {}
    if ((base.get("repo") or {}).get("full_name") != config["repository"]
            or (base.get("repo") or {}).get("id") != config["repository_id"]
            or not isinstance(base.get("ref"), str) or not base["ref"]):
        raise ValueError("invalid direct-browser activation base")
    return base["ref"] in targets


def validate_direct_wiring(candidate: Path, policy_root: Path = ROOT) -> None:
    """Prospective templates are deployed before activation, never self-approved."""
    for name in DIRECT_WORKFLOWS:
        path = candidate / ".github/workflows" / name
        canonical = policy_root / "tools/repository-checks/workflows" / name
        # Keep the independently reviewed browser generation valid. The next
        # package caller is a separate, exact generation with all owners wired.
        approved = [canonical.read_bytes()] if canonical.is_file() else []
        if name == "repository-checks.yml":
            package_caller = policy_root / "tools/repository-checks/workflows/packages/repository-checks-direct.yml"
            if package_caller.is_file() and path.is_file() and path.read_bytes() == package_caller.read_bytes():
                package_policy().validate_wiring(candidate)
                approved.append(package_caller.read_bytes())
            android_caller = policy_root / "tools/repository-checks/workflows/android/repository-checks-direct-browser.yml"
            if android_caller.is_file() and path.is_file() and path.read_bytes() == android_caller.read_bytes():
                package_policy().validate_wiring(candidate)
                android_policy().validate_tree_wiring(android_policy()._sources(candidate).entries)
                approved.append(android_caller.read_bytes())
        if (not path.is_file() or any(parent.is_symlink() for parent in
                                     (candidate / ".github", candidate / ".github/workflows", path))
                or not canonical.is_file()
                or path.read_bytes() not in approved):
            raise ValueError(f"direct-browser workflow differs from trusted orchestration: {name}")


def direct_candidate_plan(candidate: Path, event: dict, sha: str, *, policy_root: Path = ROOT) -> dict:
    repository = event.get("repository") or {}
    if repository.get("full_name") != "noah-l-frank/overte" or repository.get("id") != 1319052603:
        raise ValueError("direct-browser repository identity mismatch")
    paths, regular = changed_paths(candidate, event, sha, allow_executable=True)
    pr = event.get("pull_request")
    if pr:
        base_repository = pr["base"].get("repo") or {}
        if (base_repository.get("full_name") != repository["full_name"]
                or base_repository.get("id") != repository["id"]):
            raise ValueError("direct-browser base repository identity mismatch")
    if pr is None and "before" in event:
        before = event["before"]
        if event.get("after") != sha or not re.fullmatch(r"[0-9a-f]{40}", before):
            raise ValueError("invalid direct-browser push identity")
        if before != "0" * 40:
            paths, regular = inventory_paths(candidate, before, sha, allow_executable=True)
    verified_inventory = bool(pr) or (event.get("before") not in {None, "0" * 40})
    result = direct_browser_plan(paths, regular, verified_empty=verified_inventory and not paths)
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=candidate,
                                   text=True, stderr=subprocess.PIPE, timeout=30).strip()
    result.update(schema=1, candidate=sha, tree=tree, repository=repository["full_name"],
                  base=pr["base"]["sha"] if pr else event.get("before", ""),
                  head=pr["head"]["sha"] if pr else sha)
    policy = hashlib.sha256((policy_root / "tools/repository-checks/check.py").read_bytes())
    for name in DIRECT_WORKFLOWS:
        policy.update(name.encode())
        policy.update((policy_root / "tools/repository-checks/workflows" / name).read_bytes())
    result["policy"] = policy.hexdigest()
    result["plan"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def direct_outputs(plan: dict) -> dict[str, str]:
    return {"direct_browser": str(plan["browser"]).lower(), "direct_native": str(plan["native"]).lower(),
            "direct_plan": plan["plan"], "candidate": plan["candidate"]}


def verify_direct(needs: dict, plan: dict) -> dict[str, str]:
    if not isinstance(needs, dict) or set(needs) != {"route", "browser", "native"}:
        raise ValueError("incomplete direct-browser dependencies")
    if needs["route"].get("result") != "success" or needs["route"].get("outputs") != direct_outputs(plan):
        raise ValueError("direct-browser route/candidate/plan mismatch")
    for lane in ("browser", "native"):
        expected = "success" if plan[lane] else "skipped"
        if needs[lane].get("result") != expected:
            raise ValueError(f"direct-browser {lane}: expected {expected}")
    return {"verified": "true", "candidate": plan["candidate"], "plan": plan["plan"]}


def plan(event: dict, paths: list[str], config: dict, branches: dict,
         documentation_safe: bool = True) -> dict[str, str]:
    """Unknown paths receive full validation; bounded tool manifests get tool checks."""
    if any(not isinstance(path, str) or not path or "\x00" in path
           or "\\" in path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
           for path in paths):
        raise ValueError("invalid changed path")
    mode = "full"
    projects = tool_dependency_projects(paths, documentation_safe)
    if projects:
        mode = "tool-dependencies"
    if documentation_safe and paths and all(PurePosixPath(path).suffix in config["documentation_suffixes"] for path in paths):
        mode = "documentation"
    security = not paths or any(fnmatch.fnmatchcase(path, pattern)
                               for path in paths for pattern in config["workflow_security_paths"])
    pr = event.get("pull_request")
    if pr is not None:
        repository = event["repository"]
        base, head = pr["base"], pr["head"]
        if (repository["full_name"] != config["repository"]
                or repository["id"] != config["repository_id"]
                or base["repo"]["id"] != config["repository_id"]
                or base["repo"]["full_name"] != config["repository"]):
            raise ValueError("pull request repository identity mismatch")
        target = branches.get(base["ref"])
        same_repository = (head.get("repo") or {}).get("id") == config["repository_id"]
        same_repository &= (head.get("repo") or {}).get("full_name") == config["repository"]
        if target and target["parent"] and same_repository:
            direct = head["ref"] == target["parent"]
            reconcile = re.fullmatch(r"reconcile/" + re.escape(target["scope"])
                                     + r"/[a-z0-9]+(?:-[a-z0-9]+)*", head["ref"])
            if direct or reconcile:
                # Direction, exact ancestry, current refs and actual candidate tests
                # are enforced by the independently required trusted sync gate.
                mode = "delegated-sync"
    result = {"mode": mode, "security": str(security).lower()}
    if mode == "tool-dependencies":
        result["tool_projects"] = ",".join(projects)
    return result


def changed_paths(candidate: Path, event: dict, expected_sha: str, *,
                  allow_executable: bool = False) -> tuple[list[str], bool]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=candidate, text=True,
                                       stderr=subprocess.PIPE, timeout=30)

    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("expected candidate must be a complete commit SHA")
    if git("rev-parse", "HEAD").strip() != expected_sha:
        raise ValueError("checkout is not the event candidate")
    pr = event.get("pull_request")
    if pr is None:
        return [], False  # Manual validation always takes the conservative full route.
    base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base_sha, head_sha)):
        raise ValueError("invalid pull request commit identity")
    parents = git("show", "--no-patch", "--format=%P", expected_sha).split()
    if parents != [base_sha, head_sha]:
        raise ValueError("candidate does not merge the exact event base and head")
    return inventory_paths(candidate, base_sha, expected_sha, allow_executable=allow_executable)


def inventory_paths(candidate: Path, base_sha: str, expected_sha: str, *,
                    allow_executable: bool = False) -> tuple[list[str], bool]:
    fields = subprocess.check_output(
        ["git", "diff", "--raw", "--no-renames", "-z", base_sha, expected_sha, "--"],
        cwd=candidate, text=True, stderr=subprocess.PIPE, timeout=30).rstrip("\0").split("\0")
    if fields == [""]:
        return [], False
    if len(fields) % 2:
        raise ValueError("incomplete candidate change inventory")
    paths, documentation_safe = [], True
    for index in range(0, len(fields), 2):
        metadata = fields[index].split()
        if len(metadata) != 5 or not metadata[0].startswith(":"):
            raise ValueError("invalid candidate change metadata")
        modes = (metadata[0][1:], metadata[1])
        allowed_modes = {"000000", "100644", "100755"} if allow_executable else {"000000", "100644"}
        documentation_safe &= all(mode in allowed_modes for mode in modes)
        paths.append(fields[index + 1])
    return paths, documentation_safe


def native_required(config: dict, event: dict | None) -> bool:
    """Scope activation by trusted event base, while older descendants still work."""
    if config.get("native_required", False):
        return True
    targets = config.get("native_required_branches", [])
    if not targets:
        return False
    if not isinstance(event, dict):
        raise ValueError("native activation requires a trusted event")
    repository = event.get("repository") or {}
    if (repository.get("full_name") != config["repository"]
            or repository.get("id") != config["repository_id"]):
        raise ValueError("native activation repository mismatch")
    pr = event.get("pull_request")
    if pr is None:
        return True  # Manual runs have no PR base and always require the full native route.
    base = pr.get("base") or {}
    base_repository = base.get("repo") or {}
    if (base_repository.get("full_name") != config["repository"]
            or base_repository.get("id") != config["repository_id"]
            or not isinstance(base.get("ref"), str) or not base["ref"]):
        raise ValueError("invalid native activation base")
    return base["ref"] in targets


def verify(needs: dict, require_native: bool = True, *, require_direct: bool = False,
           direct_plan: dict | None = None, package_plan: dict | None = None,
           require_packages: bool = False, require_browser: bool = False, browser_plan: dict | None = None,
           android_plan: dict | None = None, require_android: bool = False) -> dict:
    expected_jobs = {"route", "project", "documentation", "workflow-security", "native"}
    has_browser = isinstance(needs, dict) and 'browser-client' in needs
    if has_browser:
        expected_jobs.add('browser-client')
    elif require_browser:
        raise ValueError('required Browser aggregate missing')
    has_android = isinstance(needs, dict) and "android" in needs
    if has_android:
        expected_jobs.add("android")
    elif require_android:
        raise ValueError("required Android aggregate missing")
    has_direct = isinstance(needs, dict) and "direct-browser" in needs
    if has_direct:
        expected_jobs.add("direct-browser")
    elif require_direct:
        raise ValueError("required direct-browser aggregate missing")
    if not require_native and isinstance(needs, dict) and set(needs) == expected_jobs - {"native"}:
        # Bootstrap compatibility is controlled only by the trusted default-branch
        # configuration. Once activated, missing native jobs fail closed.
        needs = {**needs, "route": {**needs["route"], "outputs": {
            **needs["route"].get("outputs", {}), "native": "skip"}}, "native": {"result": "skipped"}}
    if not isinstance(needs, dict) or set(needs) != expected_jobs:
        raise ValueError("incomplete aggregate dependencies")
    if needs["route"].get("result") != "success":
        raise ValueError("routing did not succeed")
    outputs = needs["route"].get("outputs", {})
    mode, security = outputs.get("mode"), outputs.get("security")
    if mode not in MODES or security not in {"true", "false"}:
        raise ValueError("missing or invalid trusted route")
    native = outputs.get("native")
    if native not in {"skip", "core", "full"}:
        raise ValueError("missing or invalid native route")
    required = {"native": "skipped" if native == "skip" else "success",
                "documentation": "success",
                "project": "success" if mode in {"full", "tool-dependencies"} else "skipped",
                "workflow-security": "success" if security == "true" else "skipped"}
    package_contract = require_packages or "package_plan" in outputs or any(
        key.startswith("package_") for key in needs["project"].get("outputs", {}))
    if package_contract:
        if package_plan is None:
            raise ValueError("package verification requires independently recomputed candidate inputs")
        packages = package_policy()
        if any(outputs.get(key) != value for key, value in packages.outputs(package_plan).items()):
            raise ValueError("required package route/candidate/plan mismatch")
        selected = bool(package_plan["package_set"]) or package_plan["host_mode"] in {"full", "tool-dependencies"}
        required["project"] = "success" if selected else "skipped"
        job = needs["project"]
        if selected and job.get("outputs") != packages.receipt(package_plan):
            raise ValueError("required package project receipt missing or stale")
        if not selected and any(job.get("outputs", {}).values()):
            raise ValueError("unexpected unselected package receipt")
    for job, conclusion in required.items():
        if needs[job].get("result") != conclusion:
            raise ValueError(f"{job}: expected {conclusion}, got {needs[job].get('result', 'missing')}")
    if has_direct:
        if direct_plan is None:
            raise ValueError("direct-browser requires independently verified candidate plan")
        if any(outputs.get(key) != value for key, value in direct_outputs(direct_plan).items()):
            raise ValueError("aggregate direct-browser route/candidate/plan mismatch")
        selected = direct_plan["browser"] or direct_plan["native"]
        job = needs["direct-browser"]
        expected = "success" if selected else "skipped"
        receipt = {"verified": "true", "candidate": direct_plan["candidate"], "plan": direct_plan["plan"]}
        if job.get("result") != expected:
            raise ValueError(f"direct-browser: expected {expected}")
        if selected and job.get("outputs") != receipt:
            raise ValueError("missing or mismatched direct-browser receipt")
        if not selected and any(job.get("outputs", {}).values()):
            raise ValueError("unexpected unselected direct-browser receipt")
    if has_browser:
        if browser_plan is None:
            raise ValueError('Browser requires independently recomputed candidate inputs')
        browser_policy().verify_outer(needs['browser-client'], outputs, browser_plan)
    if has_android:
        if android_plan is None:
            raise ValueError("Android requires an independently recomputed candidate plan")
        owner = android_policy()
        if any(outputs.get(key) != value for key, value in owner.outputs(android_plan).items()):
            raise ValueError("aggregate Android routing/candidate/inventory mismatch")
        owner.verify_outer(needs["android"], android_plan)
    return {"status": "PASS", "mode": mode,
            "delegated_requirement": "sync-test-reuse" if mode == "delegated-sync" else None}


def android_policy():
    spec = importlib.util.spec_from_file_location("required_android_orchestration", ROOT / "tools/repository-checks/android_gate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def package_policy():
    spec = importlib.util.spec_from_file_location("required_package_policy", ROOT / "tools/repository-checks/package_checks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def browser_policy():
    spec = importlib.util.spec_from_file_location('required_browser_policy', ROOT / 'tools/repository-checks/browser_cpu.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    metadata = commands.add_parser("metadata-event")
    metadata.add_argument("--event", type=Path, required=True)
    metadata.add_argument("--event-name", required=True)
    metadata.add_argument("--output", type=Path, required=True)
    route = commands.add_parser("plan")
    route.add_argument("--event", type=Path, required=True)
    route.add_argument("--candidate", type=Path, required=True)
    route.add_argument("--sha", required=True)
    route.add_argument("--output", type=Path, required=True)
    aggregate = commands.add_parser("verify")
    aggregate.add_argument("--needs-json", required=True)
    aggregate.add_argument("--candidate", type=Path)
    aggregate.add_argument("--sha", default=os.environ.get("GITHUB_SHA"))
    # Older platform callers inherit the event through the runner environment.
    aggregate.add_argument("--event", type=Path, default=os.environ.get("GITHUB_EVENT_PATH"))
    direct = commands.add_parser("direct-plan")
    direct.add_argument("--event", type=Path, required=True)
    direct.add_argument("--candidate", type=Path, required=True)
    direct.add_argument("--sha", required=True)
    direct.add_argument("--output", type=Path, required=True)
    direct.add_argument("--expected-candidate", default="")
    direct.add_argument("--expected-plan", default="")
    direct.add_argument("--expected-browser", default="false")
    direct.add_argument("--expected-native", default="false")
    inner = commands.add_parser("direct-verify")
    inner.add_argument("--event", type=Path, required=True)
    inner.add_argument("--candidate", type=Path, required=True)
    inner.add_argument("--sha", required=True)
    inner.add_argument("--needs-json", required=True)
    inner.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "metadata-event":
            result = classify_metadata_event(args.event, args.event_name)
            with args.output.open("a") as output:
                output.write("metadata_only=" + result["metadata_only"] + "\n")
            print(json.dumps(result, sort_keys=True))
            return 0
        config, branches = configuration()
        if args.command == "plan":
            event = json.loads(args.event.read_text())
            paths, documentation_safe = changed_paths(args.candidate, event, args.sha)
            spec = importlib.util.spec_from_file_location(
                "ios_build_policy", ROOT / "tools/ios-build-qualification/check.py")
            build_policy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(build_policy)
            build_policy.validate_wiring(args.candidate, event)
            if direct_browser_required(config, event):
                validate_direct_wiring(args.candidate)
            result = plan(event, paths, config, branches, documentation_safe)
            result.update(direct_outputs(direct_candidate_plan(args.candidate, event, args.sha)))
            packages = package_policy()
            if packages.activated(event) or packages.has_staged_caller(args.candidate):
                packages.validate_wiring(args.candidate)
                result.update(packages.outputs(packages.candidate_plan(args.candidate, event, args.sha)))
            browser = browser_policy()
            event_name = os.environ.get('GITHUB_EVENT_NAME') or ('pull_request' if 'pull_request' in event else 'workflow_dispatch')
            if browser.required(args.candidate, event, args.sha, event_name):
                result.update(browser.outer_outputs(browser.route(event, event_name, args.candidate, args.sha)))
            android = android_policy()
            if android.activated(event) or android.has_staged_caller(args.candidate):
                android.validate_execution_generation(args.candidate, event)
                result.update(android.outputs(android.candidate_plan(
                    args.candidate, event, args.sha, event_name=os.environ.get("GITHUB_EVENT_NAME", "pull_request"))))
            with args.output.open("a") as output:
                output.write("".join(f"{key}={value}\n" for key, value in result.items()))
        elif args.command == "verify":
            event = json.loads(args.event.read_text()) if args.event is not None else None
            needs = json.loads(args.needs_json)
            direct_plan = None
            packages = package_policy()
            package_plan = None
            package_required = packages.activated(event or {})
            route_outputs = needs.get("route", {}).get("outputs", {}) if isinstance(needs, dict) else {}
            project_outputs = needs.get("project", {}).get("outputs", {}) if isinstance(needs, dict) else {}
            if package_required or "package_plan" in route_outputs or any(key.startswith("package_") for key in project_outputs):
                if args.candidate is None or event is None or not args.sha:
                    raise ValueError("package verification requires exact candidate and event")
                packages.validate_wiring(args.candidate)
                package_plan = packages.candidate_plan(args.candidate, event, args.sha)
            if isinstance(needs, dict) and "direct-browser" in needs:
                if args.candidate is None or event is None or not args.sha:
                    raise ValueError("direct-browser verification requires exact candidate and event")
                validate_direct_wiring(args.candidate)
                direct_plan = direct_candidate_plan(args.candidate, event, args.sha)
            browser = browser_policy()
            event_name = os.environ.get('GITHUB_EVENT_NAME') or ('pull_request' if event and 'pull_request' in event else 'workflow_dispatch')
            browser_required = browser.required(args.candidate, event or {}, args.sha, event_name)
            browser_plan = None
            if browser_required or 'browser_plan' in route_outputs or (isinstance(needs, dict) and 'browser-client' in needs):
                if args.candidate is None or event is None or not args.sha:
                    raise ValueError('Browser verification requires exact candidate and event')
                browser_required = True
                browser_plan = browser.route(event, event_name, args.candidate, args.sha)
            android = android_policy()
            android_plan = None
            android_required = android.activated(event or {})
            if android_required or "android" in needs or any(key.startswith("android_") for key in route_outputs):
                if args.candidate is None or event is None or not args.sha:
                    raise ValueError("Android verification requires exact candidate and event")
                android.admit(args.candidate, event)
                android_plan = android.candidate_plan(args.candidate, event, args.sha,
                    event_name=os.environ.get("GITHUB_EVENT_NAME", "pull_request"))
            result = verify(needs, native_required(config, event),
                            require_direct=direct_browser_required(config, event), direct_plan=direct_plan,
                            package_plan=package_plan, require_packages=package_required,
                            require_browser=browser_required, browser_plan=browser_plan,
                            android_plan=android_plan, require_android=android_required)
        else:
            event = json.loads(args.event.read_text())
            validate_direct_wiring(args.candidate)
            candidate_plan = direct_candidate_plan(args.candidate, event, args.sha)
            if args.command == "direct-plan":
                result = direct_outputs(candidate_plan)
                if args.expected_candidate or args.expected_plan:
                    expected = {"candidate": args.expected_candidate, "direct_plan": args.expected_plan,
                                "direct_browser": args.expected_browser, "direct_native": args.expected_native}
                    if result != expected:
                        raise ValueError("reusable caller differs from exact direct-browser plan")
            else:
                result = verify_direct(json.loads(args.needs_json), candidate_plan)
            with args.output.open("a") as output:
                output.write("".join(f"{key}={value}\n" for key, value in result.items()))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f"Repository checks failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
