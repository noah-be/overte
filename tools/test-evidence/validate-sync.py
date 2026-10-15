#!/usr/bin/env python3
"""Consume exact-parent proofs against the actual isolated candidate runtime."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

import execution
import inputs
import runtime


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = "overte-trusted-sync-validation-v1"
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
    request = gate.classify_event({"repository": repository, "pull_request": pr}, config, api)
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
    documents = gate.paginate_pull_files(api, request.repository, request.number)
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


def _parent_provenance(evidence, reused):
    if evidence is None:
        return None
    return {key: evidence[key] for key in (
        "evidence_digest", "parent_branch", "parent_commit", "parent_tree", "workflow", "qualified_at", "expires_at",
    )} | {"reused_results": {name: evidence["results"]["suites"][name] for name in reused}}


def validate_sync(args, *, api=None):
    """Validate a synchronization and return an independently checked receipt.

    The API adapter performs only trusted reads. The gate's source preview does
    not authorize skipping: actual installed runtime and the local immutable
    candidate tree determine the final shared-suite selection.
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
    bounded = args.mode == "reuse" and request.profile in ("documentation", "tool-dependencies")
    if args.mode == "reuse":
        # Keep every branch differential assertion even when all common suites
        # have matching proof. Bounded profiles share this one invocation.
        _candidate_differential(candidate, request, gate, api)
    if bounded:
        with candidate_environment():
            if request.profile == "tool-dependencies":
                projects = list(gate.tool_dependencies.affected_projects(list(request.changed_paths)))
                if not projects:
                    raise ValidationError("bounded tool profile has no validated affected project")
                gate.tool_dependencies.run(candidate, projects)
        _bounded_junit(args.junit, projects)
        mode = request.profile
    else:
        required = list(registry["suites"])
        if args.mode == "reuse":
            try:
                evidence = gate.verify_evidence(api, config, request)
            except (gate.EvidenceError, gate.GateError):
                # Absent/expired/untrusted evidence cannot justify any omission.
                evidence = None
            if evidence is not None:
                if evidence.get("candidate_inputs") != local_tree:
                    raise ValidationError("local immutable candidate inputs differ from verified API inputs")
                try:
                    actual_environment = runtime.capture_host_environment()
                    plan = inputs.plan_reuse(
                        registry, evidence["parent_inputs"], local_tree, evidence["results"]["suites"],
                        evidence["environment"], actual_environment,
                    )
                except (runtime.RuntimeIdentityError, inputs.InputError, KeyError, TypeError):
                    plan = {"reused": [], "required": list(registry["suites"])}
                required, reused = plan["required"], plan["reused"]
        execution_path = Path(args.receipt).with_name(Path(args.receipt).name + ".execution.json")
        with candidate_environment():
            status, returned = execution.execute(
                candidate, suite_names=required, include_platform=True, junit=args.junit, receipt_path=execution_path,
            )
        observed = _read_execution(execution_path, returned)
        if status != 0:
            raise ValidationError("a selected shared or product suite failed")
        execution.validate_receipt(observed, registry, local_tree)
        if (observed["candidate_commit"], observed["candidate_tree"]) != initial or observed["include_platform"] is not True:
            raise ValidationError("execution receipt is not bound to the exact candidate and product suites")
        expected_product = dict(execution.platform_suites(candidate, registry["suites"]))
        if set(observed["platform_results"]) != set(expected_product) or any(
            observed["platform_results"][name]["command"] != command for name, command in expected_product.items()
        ):
            raise ValidationError("execution receipt omits or alters a declared product suite")
        executed = list(observed["results"])
        reused = [name for name in reused if name not in observed["results"]]
        if reused:
            if observed["reusable"] is not True:
                raise ValidationError("actual execution environment cannot support remaining reused proof")
            try:
                final_plan = inputs.plan_reuse(
                    registry, evidence["parent_inputs"], local_tree, evidence["results"]["suites"],
                    evidence["environment"], observed["environment"],
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
        "bounded_projects": projects, "execution": observed, "parent_evidence": _parent_provenance(evidence, reused),
        "conclusion": "success", "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_digest"] = execution.digest(result)
    execution._write_receipt(args.receipt, result)
    return result


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
    args = parser.parse_args(argv)
    try:
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
