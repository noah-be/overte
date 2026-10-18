#!/usr/bin/env python3
"""Consume exact-parent proofs against the actual isolated candidate runtime."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True

import execution
import inputs
import runtime


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = "overte-trusted-sync-validation-v1"
CI_EXECUTION_PRODUCER = "overte-trusted-sync-ci-execution-v1"
_CANDIDATE_PRIVATE_ENVIRONMENT = (
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STATE",
    "GITHUB_STEP_SUMMARY", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_RUNTIME_URL", "ACTIONS_RESULTS_URL",
)


class ValidationError(ValueError):
    """The isolated candidate does not establish a complete current result."""


def _trusted_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValidationError("trusted synchronization validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _gate():
    return _trusted_module("isolated_sync_gate", ROOT / "tools/sync-test-reuse/gate.py")


@contextmanager
def candidate_environment():
    """Keep API credentials/Actions command files out of candidate subprocesses."""
    previous = {name: os.environ.pop(name) for name in _CANDIDATE_PRIVATE_ENVIRONMENT if name in os.environ}
    try:
        yield
    finally:
        for name in _CANDIDATE_PRIVATE_ENVIRONMENT:
            os.environ.pop(name, None)
        os.environ.update(previous)


def _request(args, gate, config, api):
    if args.repository != config["repository"] or type(args.pull_request) is not int or args.pull_request < 1:
        raise ValidationError("requested synchronization repository or pull request is invalid")
    repository = api.json(f"repos/{args.repository}")
    if not isinstance(repository, dict) or repository.get("full_name") != config["repository"] \
            or repository.get("id") != config["repository_id"]:
        raise ValidationError("actual synchronization repository identity differs from trusted policy")
    pr = api.json(f"repos/{args.repository}/pulls/{args.pull_request}")
    if not isinstance(pr, dict) or pr.get("number") != args.pull_request:
        raise ValidationError("actual pull request identity is incomplete")
    event = {"number": args.pull_request, "repository": repository, "pull_request": pr}
    context = gate.effective_pr_context(event, api) if os.environ.get('GITHUB_ACTIONS') == 'true' else None
    request = (gate.classify_event(event, config, api, pr_context=context) if context is not None
               else gate.classify_event(event, config, api))
    if request is None:
        raise ValidationError("ordinary pull requests cannot use synchronization validation")
    expected = (args.repository, args.pull_request, args.base_sha, args.head_sha, args.merge_sha, args.profile)
    actual = (request.repository, request.number, request.base_sha, request.head_sha, request.merge_sha, request.profile)
    if actual != expected:
        raise ValidationError("live synchronization candidate or profile differs from dispatch identity")
    if request.repair_paths and args.mode == "reuse":
        raise ValidationError("attested product repairs require complete synchronization fallback")
    return request


def _recheck(api, gate, request):
    if getattr(request, 'event_base_sha', None) is not None:
        gate.recheck_effective_request(api, request)
        if gate.branch_sha(api, request.repository, request.parent) != request.parent_sha:
            raise ValidationError('direct parent moved during effective-base validation')
        return
    current = api.json(f"repos/{request.repository}/pulls/{request.number}")
    try:
        actual = (current["number"], current["state"], current["base"]["ref"], current["base"]["sha"],
                  current["head"]["ref"], current["head"]["sha"], current["head"]["repo"]["id"],
                  current["merge_commit_sha"])
    except (KeyError, TypeError) as error:
        raise ValidationError("live pull request identity is unavailable after validation") from error
    expected = (request.number, "open", request.base, request.base_sha, request.head, request.head_sha,
                request.head_repository_id, request.merge_sha)
    if actual != expected or current.get("mergeable") is False:
        raise ValidationError("pull request moved or became unmergeable during validation")
    if gate.branch_sha(api, request.repository, request.base) != request.base_sha \
            or gate.branch_sha(api, request.repository, request.parent) != request.parent_sha:
        raise ValidationError("target or parent branch moved during validation")


def _differential(candidate, request, documents):
    differential = _trusted_module("isolated_sync_differential", ROOT / "tools/sync-test-reuse/differential.py")
    with tempfile.TemporaryDirectory(prefix="overte-sync-inputs-") as temporary:
        path = Path(temporary) / "changed-files.json"
        path.write_bytes(execution.canonical_json(documents))
        changes = differential.load_changes(path, structured=True)
    current = differential.current_paths(candidate, changes)
    changed = [path for change in changes for path in (change.filename, change.previous_filename) if path is not None]
    differential.ensure_no_conflict_markers(candidate, current)
    differential.validate_json(candidate, current)
    differential.required_roots(candidate, request.profile, changed)
    differential.syntax_contracts(candidate, current)


def _candidate_differential(candidate, request, gate, api):
    documents = (gate.immutable_change_documents(api, request.repository, request.base_sha, request.merge_sha)
                 if getattr(request, 'event_base_sha', None) is not None
                 else gate.paginate_pull_files(api, request.repository, request.number))
    if gate.changed_paths(documents) != set(request.changed_paths):
        raise ValidationError("synchronization file inventory changed during validation")
    with candidate_environment():
        _differential(candidate, request, documents)


def _bounded_junit(path, projects):
    cases = ["sync-differential", *["tool-dependencies:" + project for project in projects]]
    root = ET.Element("testsuite", name="overte-sync-bounded", tests=str(len(cases)), failures="0", errors="0", skipped="0")
    for name in cases:
        ET.SubElement(root, "testcase", classname="overte.sync", name=name)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValidationError("bounded test report destination is unsafe")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _read_execution(path, returned):
    try:
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 5_000_000:
            raise ValidationError("trusted execution receipt is unavailable or unsafe")
        persisted = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=inputs._unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, inputs.InputError) as error:
        raise ValidationError("trusted execution receipt was not persisted completely") from error
    if persisted != returned:
        raise ValidationError("persisted execution receipt differs from trusted observations")
    return persisted


def _parent_provenance(evidence, reused, gate):
    if evidence is None:
        return None
    if isinstance(evidence, getattr(gate, 'NativeParentEvidence', ())):
        return {key: evidence[key] for key in ('kind', 'parent_branch', 'parent_commit', 'parent_tree',
            'original_commit', 'original_git_context', 'qualified_at', 'expires_at', 'original_proof')} | {
            'qualification': False, 'reusable': False,
            'reused_results': {name: evidence['results']['suites'][name] for name in reused}}
    return {key: evidence[key] for key in (
        "evidence_digest", "parent_branch", "parent_commit", "parent_tree", "workflow", "qualified_at", "expires_at",
    )} | {"reused_results": {name: evidence["results"]["suites"][name] for name in reused}}


def _ci_policy():
    paths = ("tools/test-evidence/validate-sync.py", "tools/test-evidence/execution.py",
             "tools/test-evidence/inputs.py", "tools/test-evidence/runtime.py",
             "tools/sync-test-reuse/gate.py", "tools/sync-test-reuse/differential.py",
             "tools/repository-checks/host_selection.py", "tools/repository-checks/package_checks.py",
             "tools/repository-checks/npm_consumers.py", "tests/run-project-tests.py",
             ".github/test-suites.json", ".github/package-workflow-generations.json",
             ".github/repository-checks.json", "tools/repository-checks/android_handoff.py",
             "tools/repository-checks/android_gate.py")
    result = {}
    for relative in paths:
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
            if relative == ".github/repository-checks.json":
                # Bind absence/unsafe ownership configuration while selecting
                # complete fallback; it can never admit the affected lane.
                result[relative] = None
                continue
            raise ValidationError("trusted synchronization selection policy is unavailable")
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _repository_owner_policy():
    path = ROOT / ".github/repository-checks.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000 \
            or path.stat().st_mode & 0o111:
        raise ValidationError("mandatory repository owner configuration is unavailable")
    return json.loads(path.read_text(), object_pairs_hook=inputs._unique_object)


def _sync_platform_owner(args, request, candidate, api):
    """Only complete fallback may name a separately enforced pending owner."""
    if args.mode != "fallback" or request.base not in {
            "android-main", "android-phone", "android-vr", "android-vr-pico"}:
        return {}
    config = _repository_owner_policy()
    if not isinstance(config, dict) or config.get("repository") != request.repository \
            or type(config.get("repository_id")) is not int or config["repository_id"] != request.repository_id \
            or not isinstance(config.get("required_contexts"), list) \
            or "repository-checks" not in config["required_contexts"]:
        raise ValidationError("pending Android ownership requires the mandatory canonical repository gate")
    handoff = _trusted_module("sync_android_platform_owner", ROOT / "tools/repository-checks/android_handoff.py")
    return handoff.sync_platform_owner(candidate, request, api)


def _ci_selection(args, request, candidate, initial, registry, api):
    """Plan from trusted policy and immutable inputs; never certify execution."""
    bounded = args.mode == "reuse" and request.profile in ("documentation", "tool-dependencies")
    result = {"schema": 1, "kind": "sync-ci-selection", "reusable": False,
              "repository": request.repository, "repository_id": request.repository_id,
              "pull_request": request.number, "base": request.base_sha, "head": request.head_sha,
              "candidate": initial[0], "tree": initial[1], "parent": request.parent_sha,
              "target": request.base, "profile": request.profile, "requested_mode": args.mode,
              "lane": "legacy-bounded" if bounded else "complete",
              "full_host": not bounded, "suites": [], "omitted_suites": [],
              "external_package_set": [], "package_plan": None,
              "registry": execution.digest(registry), "policy": _ci_policy()}
    if not request.changed_paths and not request.repair_paths:
        gate = _gate()
        checker = getattr(gate, 'verified_empty_sync', None)
        empty = checker(api, gate.load_config(), request, candidate) if callable(checker) else None
        if empty is not None:
            if type(empty) is not dict or empty.get('kind') != 'verified-empty-sync-v1' \
                    or empty.get('qualification') is not False or empty.get('reusable') is not False \
                    or empty.get('immutable', {}).get('candidate') != initial[0] \
                    or empty['immutable'].get('tree') != initial[1]:
                raise ValidationError('empty synchronization source proof is invalid')
            result.update(lane='verified-empty', full_host=False, empty_source=empty,
                omitted_suites=list(registry['suites']))
            result['selection'] = execution.digest(result)
            return result
    if not bounded and not request.repair_paths:
        try:
            host = _trusted_module("sync_ci_host_policy", ROOT / "tools/repository-checks/host_selection.py")
            packages = host.package_policy()
            packages.validate_wiring(candidate)
            if not packages.consumer_generation(candidate):
                raise ValidationError("complete required package owner is unavailable")
            event = {"repository": api.json(f"repos/{request.repository}"),
                     "pull_request": api.json(f"repos/{request.repository}/pulls/{request.number}")}
            owner_config = _repository_owner_policy()
            if not isinstance(owner_config, dict) or owner_config.get("repository") != request.repository \
                    or type(owner_config.get("repository_id")) is not int \
                    or owner_config["repository_id"] != request.repository_id \
                    or not isinstance(owner_config.get("required_contexts"), list) \
                    or "repository-checks" not in owner_config["required_contexts"] \
                    or not (packages.activated(event) or packages.has_staged_caller(candidate)):
                raise ValidationError("the exact package owner has no mandatory repository aggregate")
            if getattr(request, 'event_base_sha', None) is not None:
                gate = _gate()
                context = gate.recheck_effective_request(api, request, event_pr=event['pull_request'])
                plan = packages.candidate_plan(candidate, event, initial[0], pr_context=context.planning())
            else:
                plan = packages.candidate_plan(candidate, event, initial[0])
            if plan.get("unknown") is not False or plan.get("consumer_generation") is not True \
                    or (plan.get("base"), plan.get("head"), plan.get("candidate"), plan.get("tree")) != (
                        request.base_sha, request.head_sha, initial[0], initial[1]) \
                    or set(plan["paths"]) != set(request.changed_paths):
                raise ValidationError("required package plan differs from the live synchronization")
            # The exact five-file caller is independently enforced by the
            # required repository aggregate, including external npm receipts.
            tree = inputs.full_tree(candidate, initial[0])
            base_tree = inputs.full_tree(candidate, request.base_sha)
            selected = host.select(tree, plan["paths"], host.regular_ci_inventory(plan, base_tree, tree),
                unknown=plan["unknown"], trusted_tree=inputs.full_tree(ROOT, "HEAD"), candidate_root=candidate,
                trusted_root=ROOT, target=request.base, base_tree=base_tree,
                package_paths=host.package_owned_paths(plan))
            if selected["include_platform"] is not False or not selected["suites"] \
                    or host.additional_suites(host.candidate_registry(candidate), registry):
                raise ValidationError("complete product/shared fallback remains required")
            if len(set(selected["suites"])) != len(selected["suites"]) \
                    or any(name not in registry["suites"] for name in selected["suites"]):
                raise ValidationError("affected synchronization suite inventory is invalid")
            result.update(lane="affected-ci", full_host=selected["full_host"], suites=selected["suites"],
                omitted_suites=[name for name in registry["suites"] if name not in selected["suites"]],
                external_package_set=plan["package_set"], package_plan=plan["plan"],
                dependency_selection=selected, package_policy=plan["policy"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, subprocess.SubprocessError):
            # No successful diagnostic, unknown reader or missing package owner
            # can authorize omitting complete fallback and its product checks.
            pass
    pending = _sync_platform_owner(args, request, candidate, api) if result["lane"] == "complete" else {}
    if pending:
        result["pending_platform_owners"] = pending
        owner = _trusted_module("sync_android_policy_identity", ROOT / "tools/repository-checks/android_gate.py")
        result["platform_owner_policy"] = owner._policy_identity(ROOT)
    result["selection"] = execution.digest(result)
    return result


def select_sync(args, *, api=None):
    """Early prerequisite selection with the same live topology/source bookends."""
    gate = _gate(); config = gate.load_config(); api = api or gate.GitHubApi()
    request = _request(args, gate, config, api)
    candidate = Path(args.candidate).resolve(strict=True)
    initial = execution.checkout_identity(candidate)
    if initial[0] != request.merge_sha:
        raise ValidationError("selection checkout is not the exact synchronization candidate")
    registry = inputs.load_registry(ROOT / ".github/test-suites.json")
    result = _ci_selection(args, request, candidate, initial, registry, api)
    if result['lane'] == 'verified-empty':
        result = {**result, 'consumer_setup':'none', 'empty_setup':result['selection']}
        scheduling = None
    else:
        scheduling, _ = _native_zero_setup(args, gate, api, config, request, candidate, initial, registry, result)
    if scheduling is not None:
        # Additional outputs schedule prerequisites only. The existing pure
        # source selection digest remains independent of transient API proof.
        result = {**result, 'consumer_setup': 'none', 'native_setup': scheduling}
    if execution.checkout_identity(candidate) != initial:
        raise ValidationError("candidate changed during synchronization selection")
    _recheck(api, gate, request)
    return result


def _ci_commands(selection, registry, *, suite_names=None):
    names = selection["suites"] if suite_names is None else suite_names
    if type(names) is not list or names != [name for name in selection["suites"] if name in names]:
        raise ValidationError("remaining CI commands must be an exact ordered subset of the trusted selection")
    return {name: registry["suites"][name]["command"] for name in names}


def _execute_ci(candidate, initial, selection, registry, junit, receipt_path, *, suite_names=None):
    """Observe every selected invocation without creating reusable fingerprints."""
    controller = execution._runner()
    commands = _ci_commands(selection, registry, suite_names=suite_names)
    suites = [controller.Suite(name, registry["suites"][name]["layer"], tuple(
        sys.executable if index == 0 and value == "python" else value
        for index, value in enumerate(command))) for name, command in commands.items()]
    observations, cancelled, previous = [], [], {}
    def interrupted(signum, _frame):
        if not cancelled:
            cancelled.append(signum)
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    old_root = controller.ROOT
    controller.ROOT = candidate
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        with execution.candidate_process_environment():
            status = controller.run_suites(SimpleNamespace(timeout=240, host_timeout=900,
                native_build_dir=None, junit=junit, fail_fast=False), suites, cancelled,
                result_callback=observations.append)
    finally:
        controller.ROOT = old_root
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    if execution.checkout_identity(candidate) != initial:
        raise ValidationError("candidate changed during affected synchronization execution")
    actual_names = [item["name"] for item in observations]
    complete = actual_names == list(commands) and all(item["status"] == "passed" for item in observations)
    status = status or (0 if complete and not cancelled else 1)
    receipt = {"schema": 1, "producer": CI_EXECUTION_PRODUCER, "reusable": False,
        "candidate_commit": initial[0], "candidate_tree": initial[1], "selection": selection["selection"],
        "registry": execution.digest(registry), "include_platform": False,
        "requested_suites": list(commands), "results": [
            {"name": item["name"], "status": item["status"], "command": commands.get(item["name"])}
            for item in observations], "conclusion": "success" if status == 0 else "failure",
        "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    receipt["receipt_digest"] = execution.digest(receipt)
    execution._write_receipt(receipt_path, receipt)
    return status, receipt


def _verify_ci_execution(observed, selection, registry, initial, *, suite_names=None):
    fields = {"schema", "producer", "reusable", "candidate_commit", "candidate_tree", "selection", "registry",
              "include_platform", "requested_suites", "results", "conclusion", "started_at", "completed_at", "receipt_digest"}
    if not isinstance(observed, dict) or set(observed) != fields:
        raise ValidationError("affected synchronization execution receipt format is invalid")
    unsigned = dict(observed); claimed = unsigned.pop("receipt_digest")
    commands = _ci_commands(selection, registry, suite_names=suite_names)
    if type(observed["schema"]) is not int or observed["schema"] != 1 \
            or observed["producer"] != CI_EXECUTION_PRODUCER or observed["reusable"] is not False \
            or observed["include_platform"] is not False or observed["conclusion"] != "success" \
            or (observed["candidate_commit"], observed["candidate_tree"]) != initial \
            or observed["selection"] != selection["selection"] or observed["registry"] != execution.digest(registry) \
            or claimed != execution.digest(unsigned) or observed["requested_suites"] != list(commands) \
            or observed["results"] != [{"name": name, "status": "passed", "command": command}
                                       for name, command in commands.items()]:
        raise ValidationError("affected synchronization execution lacks exact selected successful coverage")
    for field in ("started_at", "completed_at"):
        if not isinstance(observed[field], str):
            raise ValidationError("affected synchronization execution time is invalid")
        stamp = datetime.fromisoformat(observed[field].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
            raise ValidationError("affected synchronization execution time is unqualified")
    if observed["started_at"] > observed["completed_at"]:
        raise ValidationError("affected synchronization execution time order is invalid")


def _native_ci_reuse(args, gate, api, config, request, registry, local_tree, selection, *, native_evidence=None):
    """Intersect original native proof with independently selected current work.

    No legacy JSON class or preview chooses a suite. The actual native adapter
    must validate original M/E first; current immutable inputs then determine
    which of the already selected commands still need execution.
    """
    selected = selection["suites"]
    if args.mode != "reuse" or not callable(getattr(gate, 'native_parent_evidence', None)):
        return None, [], list(selected)
    if native_evidence is None:
        try:
            evidence = gate.native_parent_evidence(api, config, request)
        except (gate.EvidenceError, gate.GateError):
            return None, [], list(selected)
    else:
        evidence = native_evidence
    if not isinstance(evidence, getattr(gate, 'NativeParentEvidence', ())):
        return None, [], list(selected)
    if evidence.get('candidate_inputs') != local_tree:
        raise ValidationError('local immutable CI candidate differs from verified native API inputs')
    try:
        plan = inputs.plan_reuse(registry, evidence['parent_inputs'], local_tree,
            evidence['results']['suites'], evidence['environment'], evidence['environment'])
    except (inputs.InputError, KeyError, TypeError):
        # No candidate command has started. Existing real selected execution
        # remains required when proof or its input identity is unavailable.
        return None, [], list(selected)
    reused = [name for name in selected if name in plan['reused']]
    if not reused:
        return None, [], list(selected)
    return evidence, reused, [name for name in selected if name not in reused]


def _native_zero_setup(args, gate, api, config, request, candidate, initial, registry, selection):
    """Schedule no consumer setup only for actual native zero-command coverage.

    This stdlib-only lookup grants no execution or reusable authority. The
    validator independently reconstructs it before the differential and then
    authenticates the original proof again after that actual validation.
    """
    if args.mode != 'reuse' or selection['lane'] not in {'affected-ci','complete'} \
            or request.repair_paths or selection.get('pending_platform_owners') \
            or execution.platform_suites(candidate, registry['suites']):
        return None, None
    selected = selection['suites'] if selection['lane'] == 'affected-ci' else list(registry['suites'])
    tree = inputs.full_tree(candidate, initial[0])
    evidence, reused, required = _native_ci_reuse(args, gate, api, config, request, registry, tree,
        {'suites': selected})
    if evidence is None or required or reused != selected:
        return None, None
    if gate.parse_time(evidence['expires_at'], 'expires_at') <= datetime.now(timezone.utc):
        return None, None
    value = {'schema':1, 'kind':'native-zero-command-setup-v1',
        'base':request.base_sha, 'head':request.head_sha, 'candidate':initial[0], 'tree':initial[1],
        'selection':selection['selection'], 'suites':selected,
        'original_commit':evidence['original_commit'], 'parent_commit':evidence['parent_commit'],
        'qualified_at':evidence['qualified_at'], 'expires_at':evidence['expires_at'],
        'original_proof':evidence['original_proof']}
    return execution.digest(value), evidence


def _recheck_native_ci(gate, api, config, request, evidence, registry, local_tree, reused):
    try:
        final = gate.native_parent_evidence(api, config, request)
    except (gate.EvidenceError, gate.GateError) as error:
        raise ValidationError('original native CI proof became unavailable after selected validation') from error
    if not isinstance(final, getattr(gate, 'NativeParentEvidence', ())) or final != evidence:
        raise ValidationError('original native CI proof changed after selected validation')
    try:
        plan = inputs.plan_reuse(registry, final['parent_inputs'], local_tree,
            final['results']['suites'], final['environment'], final['environment'])
    except (inputs.InputError, KeyError, TypeError) as error:
        raise ValidationError('original native CI input identities became unverifiable') from error
    if set(reused) - set(plan['reused']) or gate.parse_time(final['expires_at'], 'expires_at') <= datetime.now(timezone.utc):
        raise ValidationError('original native CI proof no longer covers selected current inputs or expired')


def validate_sync(args, *, api=None):
    """Validate a synchronization and return an independently checked receipt.

    The API adapter performs only trusted reads. The gate's source preview does
    not authorize skipping: authenticated original native M/E or actual current
    execution and immutable candidate inputs determine the final suite coverage.
    """
    gate = _gate()
    config = gate.load_config()
    api = api or gate.GitHubApi()
    request = _request(args, gate, config, api)
    candidate = Path(args.candidate).resolve(strict=True)
    initial = execution.checkout_identity(candidate)
    if initial[0] != request.merge_sha:
        raise ValidationError("checked-out candidate is not the exact dispatched merge commit")
    local_tree = inputs.full_tree(candidate, initial[0])
    registry = inputs.load_registry(ROOT / ".github/test-suites.json")
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    evidence, observed, reused, executed, projects = None, None, [], [], []
    native_parent = False
    ci_required = None
    prepared_native = None
    external_packages = []
    selection = None
    if getattr(args, "expected_selection", ""):
        selection = _ci_selection(args, request, candidate, initial, registry, api)
        if args.expected_selection != selection["selection"]:
            raise ValidationError("synchronization selection differs from the prerequisite plan")
    empty_setup = getattr(args, 'expected_empty_setup', '')
    empty_lane = selection is not None and selection['lane'] == 'verified-empty'
    if empty_setup or empty_lane:
        if not empty_lane or not empty_setup or empty_setup != selection['selection'] \
                or getattr(args, 'expected_native_setup', ''):
            raise ValidationError('empty synchronization setup does not match its exact source selection')
        # The real topology was checked by _request. No original receipt/runtime
        # or candidate test may be queried or manufactured for zero work.
        _candidate_differential(candidate, request, gate, api)
        if execution.checkout_identity(candidate) != initial \
                or _ci_selection(args, request, candidate, initial, registry, api) != selection:
            raise ValidationError('empty synchronization changed during differential validation')
        _recheck(api, gate, request)
        if _ci_selection(args, request, candidate, initial, registry, api) != selection:
            raise ValidationError('empty synchronization final source/native bookend changed')
        result = {'schema':1,'kind':'sync-no-execution-validation-v1','producer':PRODUCER,
            'reusable':False,'qualification':False,'repository':request.repository,
            'repository_id':request.repository_id,'pull_request':request.number,
            'candidate':{'base_branch':request.base,'base_commit':request.base_sha,
                'head_branch':request.head,'head_commit':request.head_sha,
                'merge_commit':initial[0],'merge_tree':initial[1],
                'parent_branch':request.parent,'parent_commit':request.parent_sha,
                'profile':request.profile,'classification':request.classification},
            'requested_mode':args.mode,'mode':'verified-empty','reused_suites':[],
            'executed_suites':[],'bounded_projects':[],'execution':None,'parent_evidence':None,
            'ci_selection':selection,'not_selected_suites':list(registry['suites']),
            'conclusion':'success','started_at':started,
            'completed_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
        result['validation_digest'] = execution.digest(result)
        execution._write_receipt(args.receipt, result)
        return result
    affected = selection is not None and selection["lane"] == "affected-ci"
    bounded = args.mode == "reuse" and request.profile in ("documentation", "tool-dependencies")
    pending = _sync_platform_owner(args, request, candidate, api) if not affected and not bounded else {}
    no_setup = getattr(args, 'expected_native_setup', '')
    if no_setup:
        if selection is None:
            raise ValidationError('no-setup scheduling requires the independently bound source selection')
        scheduling, prepared_native = _native_zero_setup(args, gate, api, config, request,
            candidate, initial, registry, selection)
        if scheduling is None or scheduling != no_setup:
            raise ValidationError('native zero-command setup plan changed; prepared fallback is unavailable')
    if args.mode == "reuse" or affected:
        # Keep every branch differential assertion even when all common suites
        # have matching proof. Bounded profiles share this one invocation.
        _candidate_differential(candidate, request, gate, api)
    if affected:
        # Recompute after the differential and again at final validation. A
        # preparation output never selects the commands or certifies execution.
        if _ci_selection(args, request, candidate, initial, registry, api) != selection:
            raise ValidationError("affected synchronization selection changed before execution")
        evidence, reused, ci_required = _native_ci_reuse(args, gate, api, config, request, registry, local_tree, selection,
            native_evidence=prepared_native)
        if no_setup and (evidence is None or ci_required):
            raise ValidationError('unprepared selected CI commands cannot run after native proof changed')
        if ci_required:
            execution_path = Path(args.receipt).with_name(Path(args.receipt).name + ".ci-execution.json")
            status, returned = _execute_ci(candidate, initial, selection, registry, args.junit, execution_path,
                suite_names=ci_required)
            observed = _read_execution(execution_path, returned)
            if status != 0:
                raise ValidationError("an affected synchronization suite failed")
            _verify_ci_execution(observed, selection, registry, initial, suite_names=ci_required)
            executed = list(ci_required)
        else:
            # Differential validation actually ran above. There is no unused
            # consumer environment or execution receipt to manufacture.
            _bounded_junit(args.junit, [])
        if reused:
            _recheck_native_ci(gate, api, config, request, evidence, registry, local_tree, reused)
        if set(reused) & set(executed) or set(reused) | set(executed) != set(selection["suites"]):
            raise ValidationError('selected CI proof and execution do not provide exact disjoint coverage')
        external_packages = list(selection["external_package_set"])
        mode = "affected-ci"
    elif bounded:
        with candidate_environment():
            if request.profile == "tool-dependencies":
                paths = list(request.changed_paths)
                s3 = "script-archive/marketplace/S3Server"
                if any(path == s3 or path.startswith(s3 + "/") for path in paths):
                    packages = gate.package_checks
                    identity = {"full_name": request.repository, "id": request.repository_id}
                    policy_event = {"repository": identity,
                                    "pull_request": {"base": {"ref": request.base, "repo": identity}}}
                    if not packages.activated(policy_event):
                        raise ValidationError("S3 bounded checks are not activated by trusted policy")
                    packages.validate_wiring(candidate)
                    selected = list(gate.tool_dependencies.affected_projects(paths, include_s3=True))
                    external_packages = [s3] if s3 in selected else []
                    projects = [project for project in selected if project != s3]
                else:
                    projects = list(gate.tool_dependencies.affected_projects(paths))
                if not projects and not external_packages:
                    raise ValidationError("bounded tool profile has no validated affected project")
                if projects:
                    gate.tool_dependencies.run(candidate, projects)
        _bounded_junit(args.junit, projects)
        mode = request.profile
    else:
        required = list(registry["suites"])
        if args.mode == "reuse":
            if prepared_native is not None:
                evidence = prepared_native
            else:
                try:
                    evidence = gate.verify_evidence(api, config, request)
                except (gate.EvidenceError, gate.GateError):
                    # Absent/expired/untrusted evidence cannot justify any omission.
                    evidence = None
            if evidence is not None:
                if evidence.get("candidate_inputs") != local_tree:
                    raise ValidationError("local immutable candidate inputs differ from verified API inputs")
                native_parent = isinstance(evidence, getattr(gate, 'NativeParentEvidence', ()))
                try:
                    # Original native schema3 E was independently admitted by
                    # the parent adapter. It is not a consumer-E measurement.
                    actual_environment = evidence['environment'] if native_parent else execution.capture_execution_environment()
                    plan = inputs.plan_reuse(
                        registry, evidence["parent_inputs"], local_tree, evidence["results"]["suites"],
                        evidence["environment"], actual_environment,
                    )
                except (runtime.RuntimeIdentityError, inputs.InputError, KeyError, TypeError):
                    plan = {"reused": [], "required": list(registry["suites"])}
                required, reused = plan["required"], plan["reused"]
        # A native proof covers the common suites independently of this
        # consumer's legacy runtime. With no remaining command or platform
        # owner there is no execution E/receipt to manufacture or measure.
        product = execution.platform_suites(candidate, registry["suites"])
        if no_setup and (not native_parent or required or product or pending):
            raise ValidationError('unprepared shared or platform commands cannot replace the scheduled native proof')
        if native_parent and not required and not product and not pending:
            _bounded_junit(args.junit, [])
        else:
            execution_path = Path(args.receipt).with_name(Path(args.receipt).name + ".execution.json")
            with candidate_environment():
                status, returned = execution.execute(
                    candidate, suite_names=required, include_platform=True, junit=args.junit, receipt_path=execution_path,
                    _platform_owner=lambda: pending,
                )
            observed = _read_execution(execution_path, returned)
            if status != 0:
                raise ValidationError("a selected shared or product suite failed")
            execution.validate_receipt(observed, registry, local_tree)
            if (observed["candidate_commit"], observed["candidate_tree"]) != initial or observed["include_platform"] is not True:
                raise ValidationError("execution receipt is not bound to the exact candidate and product suites")
            expected_product = dict(execution.platform_suites(candidate, registry["suites"]))
            if pending:
                partition = observed.get("platform_selection", {})
                if observed["schema"] != 2 or observed["reusable"] is not False or observed["environment"] is not None \
                        or partition.get("original") != list(expected_product) or partition.get("delegated") != pending:
                    raise ValidationError("pending Android owner differs from the exact observed product partition")
                expected_product = {name: command for name, command in expected_product.items() if name not in pending}
            elif observed["schema"] != 1:
                raise ValidationError("unexpected pending product ownership without authenticated source PR")
            if set(observed["platform_results"]) != set(expected_product) or any(
                observed["platform_results"][name]["command"] != command for name, command in expected_product.items()
            ):
                raise ValidationError("execution receipt omits or alters a declared product suite")
            executed = list(observed["results"])
            reused = [name for name in reused if name not in observed["results"]]
        if reused:
            if not native_parent and observed["reusable"] is not True:
                raise ValidationError("actual execution environment cannot support remaining reused proof")
            if native_parent:
                try:
                    final_evidence = gate.native_parent_evidence(api, config, request)
                except (gate.EvidenceError, gate.GateError) as error:
                    raise ValidationError('original native parent proof became unavailable after candidate execution') from error
                if not isinstance(final_evidence, gate.NativeParentEvidence) or final_evidence != evidence:
                    raise ValidationError('original native parent proof changed after candidate execution')
            try:
                final_plan = inputs.plan_reuse(
                    registry, evidence["parent_inputs"], local_tree, evidence["results"]["suites"],
                    evidence["environment"], evidence['environment'] if native_parent else observed["environment"],
                )
            except (inputs.InputError, KeyError, TypeError) as error:
                raise ValidationError("remaining reusable input identities became unverifiable") from error
            if set(reused) - set(final_plan["reused"]):
                raise ValidationError("actual execution environment no longer matches reused suite proof")
            if gate.parse_time(evidence["expires_at"], "expires_at") <= datetime.now(timezone.utc):
                raise ValidationError("parent suite evidence expired during candidate validation")
        if set(reused) & set(executed) or set(reused) | set(executed) != set(registry["suites"]):
            raise ValidationError("shared suite evidence and execution do not provide exact disjoint coverage")
        mode = "partial-reuse" if reused and executed else "reuse" if reused else "fallback"
    if execution.checkout_identity(candidate) != initial:
        raise ValidationError("candidate source changed during synchronization validation")
    if selection is not None:
        final_selection = _ci_selection(args, request, candidate, initial, registry, api)
        if final_selection != selection:
            raise ValidationError("synchronization selection changed during final validation")
        if affected:
            if observed is not None:
                _verify_ci_execution(observed, final_selection, registry, initial, suite_names=ci_required)
            elif ci_required or set(reused) != set(final_selection['suites']):
                raise ValidationError('selected CI work has neither original native proof nor actual execution')
    final_pending = _sync_platform_owner(args, request, candidate, api) if not affected and not bounded else {}
    if final_pending != pending:
        raise ValidationError("Android sync ownership or source PR labels changed during execution")
    _recheck(api, gate, request)
    result = {
        "schema": 1, "producer": PRODUCER, "repository": request.repository,
        "repository_id": request.repository_id, "pull_request": request.number,
        "candidate": {"base_branch": request.base, "base_commit": request.base_sha,
                      "head_branch": request.head, "head_commit": request.head_sha,
                      "merge_commit": initial[0], "merge_tree": initial[1],
                      "parent_branch": request.parent, "parent_commit": request.parent_sha,
                      "profile": request.profile, "classification": request.classification},
        "requested_mode": args.mode, "mode": mode, "reused_suites": reused, "executed_suites": executed,
        "bounded_projects": projects, "execution": observed, "parent_evidence": _parent_provenance(evidence, reused, gate),
        "conclusion": "success", "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if pending:
        result.update(pending_platform_owners=pending, reusable=False, qualification=False)
    if external_packages:
        # The required project aggregate owns these checks. This consumer does
        # not claim their execution or fabricate a successful JUnit case.
        result["external_package_set"] = external_packages
    if selection is not None:
        result["ci_selection"] = selection
        if affected:
            result['not_selected_suites'] = [name for name in registry['suites'] if name not in selection['suites']]
    result["receipt_digest"] = execution.digest(result)
    execution._write_receipt(args.receipt, result)
    return result


def requires_artifact_namespace(selection):
    """Schedule one utility from trusted selection; never change its authority.

    Only select_sync supplies these outputs. Existing validation independently
    rechecks empty/native-zero proofs before it can omit consumer execution.
    """
    def token(value):
        return type(value) is str and len(value) == 71 and value.startswith('sha256:') \
            and all(character in '0123456789abcdef' for character in value[7:])

    if type(selection) is not dict or type(selection.get('schema')) is not int \
            or selection['schema'] != 1 or selection.get('kind') != 'sync-ci-selection' \
            or selection.get('reusable') is not False or not token(selection.get('selection')) \
            or type(selection.get('full_host')) is not bool \
            or selection.get('requested_mode') not in ('reuse', 'fallback'):
        return True
    lane, names = selection.get('lane'), selection.get('suites')
    if lane not in ('verified-empty', 'legacy-bounded', 'affected-ci', 'complete') \
            or type(names) is not list or any(type(name) is not str or not name \
                or any(character not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for character in name)
                for name in names) or len(names) != len(set(names)):
        return True
    if lane == 'verified-empty':
        return not (selection['full_host'] is False and not names \
            and selection.get('consumer_setup') == 'none' \
            and selection.get('empty_setup') == selection['selection'] \
            and 'native_setup' not in selection)
    if lane == 'affected-ci' and not names:
        return True
    if lane == 'complete' and selection['full_host'] is not True:
        return True
    if selection.get('consumer_setup', 'required') == 'none':
        return not (lane in ('affected-ci', 'complete') \
            and token(selection.get('native_setup')) and 'empty_setup' not in selection)
    if selection.get('consumer_setup', 'required') != 'required' \
            or 'native_setup' in selection or 'empty_setup' in selection:
        return True
    if lane == 'legacy-bounded':
        return not (selection['full_host'] is False and not names \
            and selection['requested_mode'] == 'reuse' \
            and selection.get('profile') in ('documentation', 'tool-dependencies'))
    if lane == 'complete' or not names:
        return True
    # affected-ci names were already authenticated against the trusted registry.
    # Candidate command variants are retained conservatively if introduced later.
    for name in names:
        for owner in ('project-runner', 'device-control-plane-full'):
            if name == owner or name.startswith(owner + '-candidate-'):
                return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--mode", choices=("reuse", "fallback"), required=True)
    parser.add_argument("--profile", required=True)
    for name in ("base-sha", "head-sha", "merge-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--select-only", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-selection", default="")
    parser.add_argument("--expected-native-setup", default="")
    parser.add_argument("--expected-empty-setup", default="")
    args = parser.parse_args(argv)
    try:
        if args.select_only:
            if args.output is None or args.expected_selection or args.expected_native_setup or args.expected_empty_setup:
                raise ValidationError("prerequisite selection requires an output and no claimed selection")
            selected = select_sync(args)
            with args.output.open("a") as output:
                for key, value in (("selection", selected["selection"]), ("lane", selected["lane"]),
                                   ("full_host", str(selected["full_host"]).lower()),
                                   ("consumer_setup", selected.get('consumer_setup', 'required')),
                                   ("native_setup", selected.get('native_setup', '')),
                                   ("empty_setup", selected.get('empty_setup', '')),
                                   ("requires_artifact_namespace", str(requires_artifact_namespace(selected)).lower())):
                    output.write(key + "=" + value + "\n")
            print(json.dumps(selected, sort_keys=True))
            return 0
        result = validate_sync(args)
    except (ValidationError, execution.ExecutionError, inputs.InputError, runtime.RuntimeIdentityError,
            OSError, ValueError, KeyError, TypeError):
        # Errors from API/candidate processes must not expose tokens/selectors.
        print("isolated synchronization validation failed; complete current proof is unavailable", file=sys.stderr)
        return 2
    print(f"Synchronization validation: {len(result['reused_suites'])} reused, "
          f"{len(result['executed_suites'])} shared suites executed; {result['mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
