#!/usr/bin/env python3
"""Default-off trusted Browser ownership, routing and required result handoff.

Candidate files are immutable Git data. Only independently trusted policy and
complete approved callers authorize selection; arbitrary JSON is not proof.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/browser-client.yml"
TEMPLATE = "tools/repository-checks/workflows/browser-client.yml"
OUTER_WORKFLOW = ".github/workflows/repository-checks.yml"
OUTER_TEMPLATE = "tools/repository-checks/workflows/browser/repository-checks.yml"
CONFIGURATION = ".github/repository-checks.json"
REPOSITORY = {"full_name": "noah-l-frank/overte", "id": 1319052603}
REVIEWED_REVISION = "141977b15cac4a73bd35705103bc25874a431a09"
REVIEWED_WORKFLOW = "db09fbf3858e022d1f6f50eda61ecb657666cbe5"
REVIEWED_BOUNDARY = "sha256:9d022439f2474aa2d8c88d6eaa973a9b5d9bf3d2e81ac1dd63ac7b18086bda02"
REVIEWED_BROWSER_BOUNDARY = "sha256:8e1da7f4f7f586f07207e42a58cee0d1215e7f7252ee48bc188d5695b6ebfb7b"
REVIEWED_OUTER = "81400ce4f8ce5eee1a7d95976378bc03e2d6fb05"
REVIEWED_CONFIGURATION = "b4cbe180ed6816ae3f1930f61a7b36902ae13ca4"
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
    OUTER_TEMPLATE, "tools/repository-checks/check.py", "tools/repository-checks/package_checks.py",
    ".github/package-workflow-generations.json", "tests/repository-checks-test.py",
    "tests/host-producer-preparation-test.py",
})
# Actual external source/build/fixture readers, not a browser-directory trigger.
EXTERNAL_INPUTS = frozenset({
    "LICENSE", "LICENSES/Apache-2.0.txt",
    "interface/resources/meshes/defaultAvatar_full.fst",
    *('interface/resources/meshes/mannequin/' + name for name in (
        'mannequin.fbx', 'lambert1_Base_Color.png', 'lambert1_Normal_OpenGL.png',
        'lambert1_Roughness.png', 'Eyes.png')),
    *('interface/resources/fonts/' + name for name in (
        'Raleway-Regular.ttf', 'Raleway-Light.ttf', 'Raleway-Bold.ttf', 'Raleway-SemiBold.ttf',
        'FiraSans-SemiBold.ttf', 'AnonymousPro-Regular.ttf', 'hifi-glyphs.ttf', 'vircadia_glyphs.ttf')),
    'scripts/system/create/entityProperties/html/entityProperties.html',
    'scripts/system/create/entityProperties/html/js/draggableNumber.js',
    'scripts/system/create/entityProperties/html/js/entityProperties.js',
    'scripts/system/create/entityProperties/html/tabs/spatial.png',
    'scripts/system/html/css/edit-style.css', 'scripts/system/html/css/tabs.css',
    'scripts/system/snapshot.js', 'scripts/system/places/places.js', 'scripts/system/places/placesHtml.js',
    *('docs/browser-client/' + name for name in (
        'BROWSER_MICROPHONE_CONTROLS.md', 'MOVEMENT_INPUT.md', 'SOFTWARE_GRAPHICS.md', 'TABLET_SIT_ACCEPTANCE.md')),
})
INDEPENDENT_ROOTS = (
    '.github/', 'tools/', 'tests/', 'docs/', 'libraries/', 'interface/', 'scripts/',
    'assignment-client/', 'domain-server/', 'ice-server/', 'cmake/', 'android/', 'ios/',
    'launchers/', 'pkg-scripts/', 'provenance/', 'server-console/', 'script-archive/',
    'browser-direct-client/', 'unpublishedScripts/',
)
INDEPENDENT_FILES = frozenset({'README.md', 'CONTRIBUTING.md', 'AGENTS.md', '.gitignore', '.gitattributes',
                               'CMakeLists.txt', 'conanfile.py', 'conan.lock', 'requirements.txt'})
PACKAGE_PATHS = frozenset({"browser-client/package.json", "browser-client/package-lock.json"})
JOBS = {"route", "cpu", "browser", "native-journey"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
_DOMAIN = "overte-browser-cpu-history-selection-v1"
_inputs = None


def inventory():
    # Older inactive sparse callers do not materialize test-evidence. Loading
    # this default-off capability must not expand their checkout requirements.
    global _inputs
    if _inputs is None:
        spec = importlib.util.spec_from_file_location("trusted_browser_cpu_inventory", ROOT / "tools/test-evidence/inputs.py")
        require(spec is not None and spec.loader is not None, "trusted Git inventory validator unavailable")
        _inputs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_inputs)
    return _inputs


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
    inventory()._validate_tree(entries)
    return {"revision": revision, "tree": tree, "entries": entries}


def canonical_workflow(policy_root=ROOT):
    return trusted_bytes(TEMPLATE, policy_root)


def trusted_bytes(relative, policy_root=ROOT):
    path = policy_root
    for part in Path(relative).parts:
        path = path / part
        require(not path.is_symlink(), "trusted Browser policy contains a symbolic link")
    require(path.is_file() and path.stat().st_size <= 1_000_000, "trusted canonical browser policy unavailable")
    value = path.read_bytes()
    require(len(value) <= 1_000_000, "trusted Browser policy is oversized")
    return value


@lru_cache(maxsize=16)
def _blob(data):
    # These public source identities use Git's object format, rather than a
    # digest for protecting sensitive data. Delegate its encoding and collision
    # detection to Git; --stdin without -w neither filters nor writes objects.
    result = subprocess.run(["git", "--no-replace-objects", "hash-object", "--stdin"],
                            cwd=ROOT, input=data, check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=10).stdout.decode("ascii").strip()
    require(SHA.fullmatch(result), "trusted source requires a SHA-1 Git object identity")
    return result


def _entry(sha):
    return {"mode": "100644", "type": "blob", "sha": sha}


def configuration_variants(policy_root=ROOT):
    config = json.loads(trusted_bytes(CONFIGURATION, policy_root))
    require(config.get('repository') == REPOSITORY['full_name'] and config.get('repository_id') == REPOSITORY['id'],
            'foreign Browser activation policy')
    result = {REVIEWED_CONFIGURATION}
    for targets in (None, [], ['main']):
        value = dict(config)
        if targets is None:
            value.pop('browser_client_required_branches', None)
        else:
            value['browser_client_required_branches'] = targets
        result.add(_blob((json.dumps(value, indent=2) + '\n').encode()))
    return result


def approved_outer_workflows(policy_root=ROOT):
    """Exact additive callers; a complete trusted tuple is still mandatory."""
    paths = [OUTER_TEMPLATE]
    paths += ["tools/repository-checks/workflows/android-owned/" + name for name in (
        "repository-checks-browser.yml", "repository-checks-browser-direct.yml")
        if (Path(policy_root) / "tools/repository-checks/workflows/android-owned" / name).is_file()]
    return {_blob(trusted_bytes(path, policy_root)) for path in paths}


def _normalizations(policy_root):
    return {
        WORKFLOW: ({REVIEWED_WORKFLOW, _blob(canonical_workflow(policy_root))}, REVIEWED_WORKFLOW),
        OUTER_WORKFLOW: ({REVIEWED_OUTER} | approved_outer_workflows(policy_root), REVIEWED_OUTER),
        CONFIGURATION: (configuration_variants(policy_root), REVIEWED_CONFIGURATION),
    }


def _boundary(current, policy_root=ROOT, *, browser_only=False):
    selected = []
    approved = _normalizations(policy_root)
    for path, entry in sorted(current["entries"].items()):
        expected = "100755" if path == "tests/run-project-tests.py" else "100644"
        if ((path in CPU_PATHS and not browser_only) or path in INDEPENDENT_POLICY_PATHS) and entry["mode"] == expected:
            continue
        if browser_only and not (path.startswith('browser-client/') or path in EXTERNAL_INPUTS or path == WORKFLOW):
            continue
        value = dict(entry)
        if path in approved and entry['mode'] == '100644' and entry['type'] == 'blob' and entry['sha'] in approved[path][0]:
            value['sha'] = approved[path][1]
        selected.append({"path": path, **value})
    return digest({"domain": _DOMAIN + ('-browser-readers' if browser_only else '-reader-boundary'), 'entries': selected})


def review_boundary(repository, revision, *, policy_root=ROOT):
    """Return a review proposal; callers must never auto-approve a new reader."""
    current = snapshot(repository, revision)
    return {"revision": revision, "tree": current["tree"], "boundary": _boundary(current, policy_root),
            "browser_boundary": _boundary(current, policy_root, browser_only=True)}


def _policy(policy_root):
    return digest({"domain": _DOMAIN, "reviewed_revision": REVIEWED_REVISION,
                   "reviewed_boundary": REVIEWED_BOUNDARY, "cpu_paths": sorted(CPU_PATHS),
                   "independent_policy_paths": sorted(INDEPENDENT_POLICY_PATHS),
                   "legacy_workflow": REVIEWED_WORKFLOW, "canonical_workflow": _blob(canonical_workflow(policy_root)),
                   "outer_workflow": sorted(approved_outer_workflows(policy_root)),
                   "activation": json.loads(trusted_bytes(CONFIGURATION, policy_root)).get('browser_client_required_branches', []),
                   "browser_boundary": REVIEWED_BROWSER_BOUNDARY, "external_inputs": sorted(EXTERNAL_INPUTS),
                   "independent_roots": INDEPENDENT_ROOTS, "independent_files": sorted(INDEPENDENT_FILES),
                   "controller": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "inventory": hashlib.sha256((ROOT / "tools/test-evidence/inputs.py").read_bytes()).hexdigest()})


def classify(previous, current, *, policy_root=ROOT):
    """Pure classification requires two complete authenticated snapshot maps."""
    for value in (previous, current):
        inventory()._validate_tree(value["entries"])
    old, new = previous["entries"], current["entries"]
    changes = [{"path": path, "old": old.get(path), "new": new.get(path)}
               for path in sorted(old.keys() | new.keys()) if old.get(path) != new.get(path)]
    paths = {item["path"] for item in changes}
    regular = all(entry["mode"] in {"100644", "100755"} for tree in (old, new) for entry in tree.values())
    cpu_modes = all(entry is None or entry["mode"] == "100644"
                    for item in changes if item["path"] in CPU_PATHS for entry in (item["old"], item["new"]))
    boundary = [_boundary(value, policy_root) for value in (previous, current)]
    browser_boundary = [_boundary(value, policy_root, browser_only=True) for value in (previous, current)]
    bootstrap = (bool(paths & CPU_PATHS) and paths <= CPU_PATHS | {WORKFLOW, OUTER_WORKFLOW, CONFIGURATION}
                 and old.get(WORKFLOW) == _entry(REVIEWED_WORKFLOW)
                 and old.get(OUTER_WORKFLOW) == _entry(REVIEWED_OUTER)
                 and new.get(WORKFLOW) == _entry(_blob(canonical_workflow(policy_root)))
                 and new.get(OUTER_WORKFLOW) == _entry(_blob(trusted_bytes(OUTER_TEMPLATE, policy_root)))
                 and all(tree.get(CONFIGURATION) in [_entry(sha) for sha in configuration_variants(policy_root)] for tree in (old, new)))
    independent = all(path not in EXTERNAL_INPUTS and not path.startswith('browser-client/')
                      and path not in {WORKFLOW, TEMPLATE, OUTER_TEMPLATE, OUTER_WORKFLOW, CONFIGURATION}
                      and (path in INDEPENDENT_FILES or path.startswith(INDEPENDENT_ROOTS)) for path in paths)
    if not changes:
        reason = "empty-inventory-requires-full"
    elif not regular or not cpu_modes:
        reason = "nonregular-mode-or-alias-requires-full"
    elif independent and browser_boundary == [REVIEWED_BROWSER_BOUNDARY, REVIEWED_BROWSER_BOUNDARY]:
        reason = "unchanged-reviewed-browser-inputs"
    elif boundary != [REVIEWED_BOUNDARY, REVIEWED_BOUNDARY]:
        reason = "reader-boundary-not-reviewed"
    elif paths <= CPU_PATHS or bootstrap:
        reason = "approved-workflow-bootstrap-and-cpu-history" if bootstrap else "cpu-history-only"
    else:
        reason = "other-or-mixed-inputs-require-full"
    mode = ('skip' if reason == 'unchanged-reviewed-browser-inputs' else
            'cpu' if reason in {'cpu-history-only', 'approved-workflow-bootstrap-and-cpu-history'} else 'full')
    return {"mode": mode,
            "audit": bool(paths & PACKAGE_PATHS), "reason": reason, "changes": changes,
            "base_boundary": boundary[0], "candidate_boundary": boundary[1],
            "base_browser_boundary": browser_boundary[0], "candidate_browser_boundary": browser_boundary[1]}


def validate_wiring(current, *, policy_root=ROOT):
    require(current["entries"].get(WORKFLOW) == {"mode": "100644", "type": "blob",
                                                "sha": _blob(canonical_workflow(policy_root))},
            "browser workflow differs from trusted canonical orchestration")
    require(current['entries'].get(OUTER_WORKFLOW) in [_entry(sha) for sha in approved_outer_workflows(policy_root)],
            'Browser requires the exact paired sole-owner outer workflow')
    if current['entries'].get(OUTER_WORKFLOW) != _entry(_blob(trusted_bytes(OUTER_TEMPLATE, policy_root))):
        spec = importlib.util.spec_from_file_location("browser_complete_package_tuple", ROOT / "tools/repository-checks/package_checks.py")
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        package.ROOT = Path(policy_root)
        package.validate_tree_wiring(current['entries'])


def target_branch(event, event_name):
    require(isinstance(event, dict) and isinstance(event.get('repository'), dict)
            and all(event['repository'].get(k) == v for k, v in REPOSITORY.items()), 'foreign browser repository')
    if 'pull_request' in event:
        pr = event['pull_request']
        base = pr.get('base') if isinstance(pr, dict) else None
        require(isinstance(base, dict) and isinstance(base.get('repo'), dict)
                and all(base['repo'].get(k) == v for k, v in REPOSITORY.items()), 'foreign PR base')
        branch = base.get('ref')
        require(not isinstance(branch, str) or not branch.startswith('refs/'), 'invalid Browser base ref')
    else:
        ref = event.get('ref')
        require(isinstance(ref, str), 'missing Browser branch ref')
        if ref.startswith('refs/heads/'):
            branch = ref[len('refs/heads/'):]
        else:
            require(event_name == 'workflow_dispatch' and not ref.startswith('refs/')
                    and os.environ.get('GITHUB_REF') == 'refs/heads/' + ref
                    and os.environ.get('GITHUB_REF_TYPE') == 'branch', 'unsupported Browser branch ref')
            branch = ref
    require(isinstance(branch, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', branch)
            and not branch.endswith('/') and '//' not in branch and '..' not in branch
            and all(not part.startswith('.') and not part.endswith(('.', '.lock')) for part in branch.split('/')),
            'invalid Browser branch identity')
    if event_name == 'workflow_dispatch' and os.environ.get('GITHUB_REF'):
        require(os.environ['GITHUB_REF'] == 'refs/heads/' + branch
                and os.environ.get('GITHUB_REF_TYPE', 'branch') == 'branch', 'conflicting manual Browser branch')
    return branch


def activated(event, event_name, *, policy_root=ROOT):
    targets = json.loads(trusted_bytes(CONFIGURATION, policy_root)).get('browser_client_required_branches', [])
    require(isinstance(targets, list) and all(isinstance(target, str) for target in targets)
            and len(targets) == len(set(targets)), 'invalid Browser activation targets')
    if not targets:
        return False
    return target_branch(event, event_name) in targets


def _contract_at(candidate, revision, policy_root):
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        return False
    expected = {WORKFLOW: _blob(canonical_workflow(policy_root)),
                OUTER_WORKFLOW: _blob(trusted_bytes(OUTER_TEMPLATE, policy_root))}
    raw = git(candidate, 'ls-tree', '-z', revision, '--', *expected)
    for row in raw.split(b'\0'):
        if not row:
            continue
        metadata, path = row.split(b'\t', 1)
        mode, kind, sha = metadata.decode('ascii').split()
        if mode == '100644' and kind == 'blob' and (expected.get(path.decode()) == sha or
                path.decode() == OUTER_WORKFLOW and sha in approved_outer_workflows(policy_root)):
            return True
    return False


def required(candidate, event, expected_sha, event_name, *, policy_root=ROOT):
    """Trusted activation or deployed protected-base capability prevents rollback.

    Detection of either new file requires the whole pair. Candidate settings
    never authorize omission; old inactive sparse callers retain compatibility.
    """
    if activated(event, event_name, policy_root=policy_root):
        return True
    if candidate is None:
        return False
    base = event.get('pull_request', {}).get('base', {}).get('sha') if isinstance(event.get('pull_request'), dict) else None
    return any(_contract_at(candidate, revision, policy_root) for revision in (expected_sha, base))


def route(event, event_name, candidate, expected_sha, *, policy_root=ROOT):
    target = target_branch(event, event_name)
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
    binding = {"candidate": expected_sha, "tree": current["tree"], "base": base, "head": head, 'target': target,
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
        selected = expected['mode'] != 'skip' and ((name == "cpu") == (expected["mode"] == "cpu"))
        require(needs[name].get("result") == ("success" if selected else "skipped"),
                "missing, failed or unexpectedly executed browser job: " + name)
    # Manual startup diagnostics intentionally do not prove full journeys. They
    # cannot satisfy the future independently required pull-request handoff.
    diagnostic = event_name == "workflow_dispatch" and event.get("inputs", {}).get("startup_diagnostics") in (True, "true")
    return {"candidate": expected_sha, "plan": expected["plan"], "verified": "diagnostic-only" if diagnostic else "true"}


def outer_outputs(plan):
    return {'browser_mode': plan['mode'], 'browser_candidate': plan['candidate'], 'browser_plan': plan['plan']}


def verify_outer(job, outputs, plan):
    require(all(outputs.get(key) == value for key, value in outer_outputs(plan).items()),
            'outer Browser route differs from independently recomputed candidate plan')
    selected = plan['mode'] != 'skip'
    require(isinstance(job, dict) and job.get('result') == ('success' if selected else 'skipped'),
            'selected Browser callee failed, is missing, or was unexpectedly skipped')
    receipt = job.get('outputs', {})
    if selected:
        require(receipt == {'candidate': plan['candidate'], 'plan': plan['plan'], 'verified': 'true'},
                'outer Browser receipt is missing, diagnostic, forged or stale')
    else:
        require(isinstance(receipt, dict) and set(receipt) <= {'candidate', 'plan', 'verified'}
                and all(value == '' for value in receipt.values()), 'unexpected unselected Browser receipt')


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
        if name == 'route':
            command.add_argument('--expected-candidate', default='')
            command.add_argument('--expected-plan', default='')
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
            if args.command == 'route' and args.event_name == 'pull_request':
                require(args.expected_candidate == value['candidate'] and args.expected_plan == value['plan'],
                        'reusable Browser caller differs from independently recomputed candidate plan')
            with args.output.open("a") as handle:
                handle.write("".join(f"{key}={value}\n" for key, value in value.items()))
            print(json.dumps(value, sort_keys=True))
        return 0
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print("Browser selection failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
