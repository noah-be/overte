#!/usr/bin/env python3
"""Dormant producer-proof protocol; no dispatch, retry, skip or workflow writes.

Authenticated* inputs are a trusted adapter's independently read API/Git facts,
never fields copied from an artifact. Their Python types are not authentication.
This module deliberately provides no JSON-to-authenticated-facts constructor.
Only shared execution owners have an implemented inner validator. Every other
selected owner remains unsupported until its complete receipt is implemented.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import re
import stat
import zipfile

import execution
import inputs


class ProtocolError(ValueError):
    """Complete independently authenticated producer proof is unavailable."""


@dataclass(frozen=True)
class Policy:
    repository: str
    repository_id: int
    actions_app_id: int
    workflow_path: str
    workflow_blob: str
    workflow_ref: str
    events: tuple[str, ...]
    controller_digest: str
    runtime_contract: str
    max_age_seconds: int = 86400
    required_execution_schema: int = 1


@dataclass(frozen=True)
class AuthenticatedJob:
    job_id: int
    attempt: int
    status: str
    conclusion: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class AuthenticatedPublication:
    """Native final-job facts read by the trusted adapter, never artifact claims.

    receipt_sha256 is the lowercase hexadecimal SHA256 of the complete canonical
    shared execution receipt, including its receipt_digest field. The adapter
    must authenticate this commitment in the approved native job name and bind
    that job to this exact run, original attempt, check app and workflow source.
    """
    job: AuthenticatedJob
    receipt_sha256: str


@dataclass(frozen=True)
class AuthenticatedRun:
    repository: str
    repository_id: int
    actions_app_id: int
    run_id: int
    attempt: int
    latest_attempt: int
    attempt_started_at: str | None
    workflow_path: str
    workflow_blob: str
    workflow_commit: str
    workflow_ref: str
    event: str
    status: str
    conclusion: str | None
    publisher: AuthenticatedJob | None
    owners: dict[str, AuthenticatedJob]
    final_publisher: AuthenticatedPublication | None = None


@dataclass(frozen=True)
class AuthenticatedArtifact:
    artifact_id: int
    repository_id: int
    run_id: int
    name: str
    archive_digest: str
    expired: bool
    created_at: str
    expires_at: str
    inventory_complete: bool
    matching_artifacts: int


@dataclass(frozen=True)
class Observation:
    run: AuthenticatedRun
    descriptor_archive: bytes | None
    descriptor_artifact: AuthenticatedArtifact | None


@dataclass(frozen=True)
class SharedContext:
    registry: dict
    tree: dict
    environment: dict
    candidate_commit: str
    candidate_tree: str
    git_context: dict | None = None


_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}
_CONCLUSIONS = {"success", "failure", "cancelled", "timed_out", "action_required", "neutral", "skipped", "stale", "startup_failure"}
_MAX_JSON = 1_000_000
_MAX_ARCHIVE = 2_000_000


def canonical(value) -> bytes:
    try:
        result = inputs._canonical(value)
    except inputs.InputError as error:
        raise ProtocolError("proof must contain canonical JSON values") from error
    if len(result) > _MAX_JSON:
        raise ProtocolError("proof exceeds its bounded JSON size")
    return result


def digest(value) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def _fields(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ProtocolError("proof object has missing or unsupported fields")


def _positive(value):
    if type(value) is not int or value < 1:
        raise ProtocolError("API identity requires a positive integer")


def _match(pattern, value):
    if not isinstance(value, str) or not pattern.fullmatch(value) or (pattern is _SHA and set(value) == {"0"}):
        raise ProtocolError("proof identity has an unsupported format")


def _time(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtocolError("proof timestamp must use UTC")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ProtocolError("proof timestamp is invalid") from error
    return result


def _now(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ProtocolError("verification requires an independently supplied current UTC time")


def validate_binding(value):
    _fields(value, {"repository", "repository_id", "pull_request", "head_repository_id", "base_ref", "base_sha",
                    "head_ref", "head_sha", "merge_sha", "merge_tree", "merge_parents"})
    if value["repository"] != "noah-l-frank/overte" or value["repository_id"] != 1319052603:
        raise ProtocolError("candidate repository is outside the reviewed fork")
    for key in ("repository_id", "pull_request", "head_repository_id"):
        _positive(value[key])
    for key in ("base_sha", "head_sha", "merge_sha", "merge_tree"):
        _match(_SHA, value[key])
    for key in ("base_ref", "head_ref"):
        ref = value[key]
        if not isinstance(ref, str) or not ref or len(ref) > 255 or re.search(r"[\x00-\x20\x7f~^:?*\[\\]", ref) \
                or ref.startswith(("/", "-")) or ref.endswith(("/", ".")) or "//" in ref or ".." in ref or "@{" in ref \
                or any(part.startswith(".") or part.endswith(".lock") for part in ref.split("/")):
            raise ProtocolError("candidate ref is unavailable or unsupported")
    if value["merge_parents"] != [value["base_sha"], value["head_sha"]]:
        raise ProtocolError("candidate parents differ from the exact live base and head")
    canonical(value)
    return value


def validate_plan(plan):
    _fields(plan, {"owners"})
    if not isinstance(plan["owners"], dict) or not plan["owners"]:
        raise ProtocolError("producer plan requires an explicit selected owner inventory")
    for name, owner in plan["owners"].items():
        _match(_NAME, name)
        _fields(owner, {"kind", "suites", "include_platform", "platform"})
        _match(_NAME, owner["kind"])
        if not isinstance(owner["suites"], list) or any(not isinstance(item, str) for item in owner["suites"]) \
                or len(set(owner["suites"])) != len(owner["suites"]) or type(owner["include_platform"]) is not bool \
                or not isinstance(owner["platform"], dict) or (not owner["include_platform"] and owner["platform"]):
            raise ProtocolError("selected owner inventory is invalid")
        for suite in owner["suites"]:
            _match(_NAME, suite)
        for platform_name, command in owner["platform"].items():
            _match(_NAME, platform_name)
            if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in command):
                raise ProtocolError("selected platform command is invalid")
    canonical(plan)
    return plan


def policy_digest(policy):
    if not isinstance(policy, Policy):
        raise ProtocolError("trusted producer policy is unavailable")
    if policy.repository != "noah-l-frank/overte" or policy.repository_id != 1319052603:
        raise ProtocolError("producer policy is outside the reviewed fork")
    _positive(policy.actions_app_id)
    _match(_SHA, policy.workflow_blob)
    for value in (policy.controller_digest, policy.runtime_contract):
        _match(_DIGEST, value)
    if not policy.workflow_path.startswith(".github/workflows/") or not policy.workflow_ref.startswith("refs/") \
            or not policy.events or any(event not in {"pull_request", "workflow_dispatch", "push"} for event in policy.events) \
            or type(policy.max_age_seconds) is not int or not 0 < policy.max_age_seconds <= 604800:
        raise ProtocolError("producer workflow or validity policy is unsupported")
    if type(policy.required_execution_schema) is not int or policy.required_execution_schema not in {1, 3}:
        raise ProtocolError("producer execution schema policy is unsupported")
    return digest(asdict(policy))


def _run(run, policy, *, require_latest=True):
    if not isinstance(run, AuthenticatedRun):
        raise ProtocolError("independently authenticated Actions run facts are required")
    for number in (run.run_id, run.attempt, run.latest_attempt):
        _positive(number)
    policy_digest(policy)
    actual = (run.repository, run.repository_id, run.actions_app_id, run.workflow_path, run.workflow_blob, run.workflow_ref)
    expected = (policy.repository, policy.repository_id, policy.actions_app_id, policy.workflow_path, policy.workflow_blob, policy.workflow_ref)
    if actual != expected or run.event not in policy.events:
        raise ProtocolError("actual run repository, app or workflow provenance differs from trusted policy")
    _match(_SHA, run.workflow_commit)
    if run.attempt > run.latest_attempt or (require_latest and run.attempt != run.latest_attempt):
        raise ProtocolError("run facts omit the latest authoritative attempt")
    if run.status not in _PENDING | {"completed"} or (run.status == "completed") != (run.conclusion in _CONCLUSIONS):
        raise ProtocolError("actual run status is unavailable or inconsistent")
    if run.attempt_started_at is not None:
        _time(run.attempt_started_at)
    if not isinstance(run.owners, dict):
        raise ProtocolError("actual owner job facts are unavailable")
    if run.final_publisher is not None and (
            not isinstance(run.final_publisher, AuthenticatedPublication)
            or not isinstance(run.final_publisher.receipt_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", run.final_publisher.receipt_sha256) is None):
        raise ProtocolError("final publisher commitment is not an authenticated complete-receipt hash")
    final_job = run.final_publisher.job if run.final_publisher is not None else None
    for job in [run.publisher, *run.owners.values(), final_job]:
        if job is None:
            continue
        if not isinstance(job, AuthenticatedJob) or job.attempt != run.attempt:
            raise ProtocolError("mixed or unauthenticated job attempts cannot establish reusable proof")
        _positive(job.attempt)
        _positive(job.job_id)
        if job.status not in _PENDING | {"completed"} or (job.status == "completed") != (job.conclusion in _CONCLUSIONS):
            raise ProtocolError("actual job status is unavailable or inconsistent")
        if job.started_at is not None:
            if run.attempt_started_at is not None and _time(job.started_at) < _time(run.attempt_started_at):
                raise ProtocolError("actual job predates its bound run attempt")
        if job.completed_at is not None and (job.started_at is None or _time(job.completed_at) < _time(job.started_at)):
            raise ProtocolError("actual job time order is invalid")


def _source(run):
    if run.publisher is None or run.publisher.started_at is None:
        raise ProtocolError("producer descriptor publishing job is unavailable")
    return {"workflow_path": run.workflow_path, "workflow_blob": run.workflow_blob, "workflow_commit": run.workflow_commit,
            "workflow_ref": run.workflow_ref, "event": run.event, "run_id": run.run_id, "attempt": run.attempt,
            "publisher_job_id": run.publisher.job_id}


def descriptor(binding, plan, policy, run):
    validate_binding(binding)
    validate_plan(plan)
    _run(run, policy)
    value = {"schema": 1, "producer": "overte-producer-descriptor-v1", "binding": binding, "plan": plan,
             "policy": policy_digest(policy), "runtime_contract": policy.runtime_contract, "source": _source(run),
             "started_at": run.publisher.started_at}
    return json.loads(canonical({**value, "descriptor_digest": digest(value)}))


def validate_descriptor(value, binding, plan, policy, run):
    expected = descriptor(binding, plan, policy, run)
    if canonical(value) != canonical(expected):
        raise ProtocolError("descriptor differs from actual candidate, plan, policy or authenticated run")
    return expected


def select_authority(observations, binding, plan, policy, *, inventory_complete, now):
    """Inspect ALL statuses/attempts. proof-required is never a success result."""
    validate_binding(binding)
    validate_plan(plan)
    policy_digest(policy)
    _now(now)
    unresolved = {"state": "unresolved", "run_id": None, "attempt": None}
    if inventory_complete is not True or not isinstance(observations, list):
        return unresolved
    if not observations:
        return {**unresolved, "state": "absent"}
    ordered, seen, latest = [], set(), {}
    try:
        for item in observations:
            if not isinstance(item, Observation):
                return unresolved
            run = item.run
            _run(run, policy, require_latest=False)
            key = (run.run_id, run.attempt)
            if key in seen or run.attempt_started_at is None:
                return unresolved
            if run.run_id in latest and latest[run.run_id] != run.latest_attempt:
                return unresolved
            latest[run.run_id] = run.latest_attempt
            seen.add(key)
            if run.attempt == run.latest_attempt:
                ordered.append((_time(run.attempt_started_at), item))
        if any((run_id, attempt) not in seen for run_id, attempt in latest.items()):
            return unresolved
        newest = max(stamp for stamp, _ in ordered)
        candidates = [item for stamp, item in ordered if stamp == newest]
        if len(candidates) != 1:
            return unresolved
        selected = candidates[0]
        value = read_artifact(selected.descriptor_archive, "descriptor", selected.descriptor_artifact, selected.run, now=now)
        validate_descriptor(value, binding, plan, policy, selected.run)
    except (ProtocolError, ValueError, TypeError):
        return unresolved
    run = selected.run
    state = "pending" if run.status != "completed" else "proof-required" if run.conclusion == "success" else "failed"
    return {"state": state, "run_id": run.run_id, "attempt": run.attempt,
            "descriptor_digest": value["descriptor_digest"], "artifact_id": selected.descriptor_artifact.artifact_id,
            "archive_digest": selected.descriptor_artifact.archive_digest}


def artifact_bytes(value, kind):
    """Create the fixed single-member wire envelope; hashes are not provenance."""
    if kind not in {"descriptor", "aggregate"}:
        raise ProtocolError("unsupported producer artifact kind")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(kind + ".json", canonical(value))
    return output.getvalue()


def read_artifact(raw, kind, facts, run, *, now):
    _now(now)
    if kind not in {"descriptor", "aggregate"} or not isinstance(facts, AuthenticatedArtifact) or not isinstance(run, AuthenticatedRun):
        raise ProtocolError("independently authenticated artifact and run facts are required")
    _positive(facts.artifact_id)
    if facts.repository_id != run.repository_id or facts.run_id != run.run_id \
            or facts.name != f"ci-{kind}-{run.run_id}-{run.attempt}" or facts.expired is not False \
            or facts.inventory_complete is not True or type(facts.matching_artifacts) is not int or facts.matching_artifacts != 1 \
            or not _time(facts.created_at) <= now < _time(facts.expires_at):
        raise ProtocolError("artifact ownership, attempt name or lifetime differs from the producer")
    _match(_DIGEST, facts.archive_digest)
    if not isinstance(raw, bytes) or len(raw) > _MAX_ARCHIVE or "sha256:" + hashlib.sha256(raw).hexdigest() != facts.archive_digest:
        raise ProtocolError("artifact bytes differ from authenticated bounded archive")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].filename != kind + ".json" or members[0].file_size > _MAX_JSON \
                    or members[0].compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED} \
                    or stat.S_ISLNK(members[0].external_attr >> 16):
                raise ProtocolError("artifact has unsupported members or uncompressed size")
            content = archive.read(members[0])
        value = json.loads(content, object_pairs_hook=inputs._unique_object)
        if content != canonical(value) or not isinstance(value, dict):
            raise ProtocolError("artifact does not contain one canonical proof object")
        return value
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, ProtocolError):
            raise
        raise ProtocolError("producer artifact cannot be decoded safely") from error


def capture_shared_context(registry, candidate, expected_commit):
    """Trusted producer adapter: unavailable actual runtime never becomes unknown."""
    inputs._validate_registry(registry)
    _match(_SHA, expected_commit)
    commit, tree_sha = execution.checkout_identity(candidate)
    if commit != expected_commit:
        raise ProtocolError("actual source context differs from the requested immutable candidate")
    tree = inputs.full_tree(candidate, commit)
    inputs._validate_tree(tree)
    return SharedContext(registry, tree, execution.capture_execution_environment(), commit, tree_sha)


def verify_aggregate(raw, artifact, binding, plan, policy, observations, *, inventory_complete,
                     final_binding, final_observations, final_inventory_complete, contexts, now):
    """Validate one original proof only. Relay and mixed-attempt proof is unsupported.

    Both snapshots and every context must be independently supplied by a trusted
    API/Git/runtime adapter. Callers must take the final snapshot immediately
    before publishing a result. No JSON field can authenticate those facts.
    """
    validate_binding(final_binding)
    if final_binding != binding:
        raise ProtocolError("live candidate changed during proof verification")
    first = select_authority(observations, binding, plan, policy, inventory_complete=inventory_complete, now=now)
    last = select_authority(final_observations, binding, plan, policy, inventory_complete=final_inventory_complete, now=now)
    if first != last or first["state"] != "proof-required":
        raise ProtocolError("latest producer is missing, pending, failed or changed")
    selected = next(item for item in final_observations if (item.run.run_id, item.run.attempt) == (last["run_id"], last["attempt"]))
    run = selected.run
    initial = next(item for item in observations if (item.run.run_id, item.run.attempt) == (first["run_id"], first["attempt"]))
    if run.final_publisher is None or initial.run.final_publisher != run.final_publisher:
        raise ProtocolError("authenticated final publisher is missing or changed during verification")
    return _verify_original_payload(raw, artifact, binding, plan, policy, selected, contexts=contexts, now=now)


def _verify_original_payload(raw, artifact, binding, plan, policy, selected, *, contexts, now):
    """Validate the same original payload after independent native authority.

    This does not select an authoritative run or assert overall run success.
    The ordinary verifier above still requires its unchanged completed-run
    selector. Only the fixed current-self native owner entrypoint may instead
    authenticate its own running outer job and completed producer jobs.
    """
    validate_binding(binding)
    validate_plan(plan)
    _now(now)
    if not isinstance(selected, Observation):
        raise ProtocolError("original selected observation is unavailable")
    run = selected.run
    _run(run, policy)
    if run.final_publisher is None:
        raise ProtocolError("authenticated original final publisher is unavailable")
    if run.attempt != 1 or run.latest_attempt != 1:
        raise ProtocolError("final publication requires the original first execution attempt")
    if len(plan["owners"]) != 1 or next(iter(plan["owners"].values()))["kind"] != "shared":
        raise ProtocolError("final publication supports exactly one shared execution owner")
    descriptor_value = read_artifact(selected.descriptor_archive, "descriptor", selected.descriptor_artifact, run, now=now)
    validate_descriptor(descriptor_value, binding, plan, policy, run)
    value = read_artifact(raw, "aggregate", artifact, run, now=now)
    _fields(value, {"schema", "producer", "descriptor_digest", "results", "qualified_at", "expires_at", "aggregate_digest"})
    unsigned = dict(value)
    claimed = unsigned.pop("aggregate_digest")
    if type(value["schema"]) is not int or value["schema"] != 1 or value["producer"] != "overte-producer-aggregate-v1" \
            or value["descriptor_digest"] != descriptor_value["descriptor_digest"] or claimed != digest(unsigned):
        raise ProtocolError("aggregate identity or canonical digest differs from its original descriptor")
    qualified, expires = _time(value["qualified_at"]), _time(value["expires_at"])
    if not _time(descriptor_value["started_at"]) <= qualified <= now < expires \
            or (expires - qualified).total_seconds() > policy.max_age_seconds \
            or qualified > _time(artifact.created_at) \
            or expires > min(_time(artifact.expires_at), _time(selected.descriptor_artifact.expires_at)):
        raise ProtocolError("original producer validity period is unavailable, expired or extended")
    if not isinstance(value["results"], dict) or set(value["results"]) != set(plan["owners"]) \
            or set(run.owners) != set(plan["owners"]):
        raise ProtocolError("aggregate or authenticated jobs omit selected owners")
    if run.publisher.status != "completed" or run.publisher.conclusion != "success" or run.publisher.completed_at is None:
        raise ProtocolError("trusted descriptor publishing job did not complete successfully")
    if not _time(run.publisher.started_at) <= _time(selected.descriptor_artifact.created_at) <= _time(run.publisher.completed_at):
        raise ProtocolError("descriptor was not published by its early bound job")
    final_job = run.final_publisher.job
    if (final_job is None or final_job.job_id in {run.publisher.job_id, *(job.job_id for job in run.owners.values())}
            or final_job.status != "completed" or final_job.conclusion != "success"
            or final_job.started_at is None or final_job.completed_at is None
            or not _time(final_job.started_at) <= qualified <= _time(artifact.created_at) <= _time(final_job.completed_at)):
        raise ProtocolError("aggregate is not bound to a distinct successful final publishing job and its actual time window")
    for name, owner in plan["owners"].items():
        result, job = value["results"][name], run.owners[name]
        _fields(result, {"status", "job_id", "attempt", "receipt"})
        _positive(result["job_id"])
        _positive(result["attempt"])
        if result["status"] != "passed" or result["job_id"] != job.job_id or result["attempt"] != run.attempt \
                or job.status != "completed" or job.conclusion != "success" or job.started_at is None or job.completed_at is None \
                or _time(job.started_at) < _time(run.publisher.completed_at) or _time(job.completed_at) > qualified \
                or _time(job.completed_at) > _time(final_job.started_at):
            raise ProtocolError("selected owner lacks complete current-attempt successful execution")
        if owner["kind"] != "shared" or not isinstance(contexts.get(name), SharedContext):
            raise ProtocolError("selected owner has no implemented complete inner-receipt validator")
        context, receipt = contexts[name], result["receipt"]
        try:
            inputs._validate_registry(context.registry)
            inputs._validate_tree(context.tree)
            inputs._environment(context.environment)
            if policy.required_execution_schema == 3 and (receipt.get("schema") != 3 or context.git_context is None):
                raise ProtocolError("isolated publication requires original materialized Git context")
            execution.validate_receipt(receipt, context.registry, context.tree,
                                       expected_git_context=context.git_context)
            if context.candidate_commit != binding["merge_sha"] or context.candidate_tree != binding["merge_tree"] \
                    or receipt["reusable"] is not True or receipt["environment"] != context.environment \
                    or receipt["candidate_commit"] != binding["merge_sha"] or receipt["candidate_tree"] != binding["merge_tree"] \
                    or set(receipt["requested_suites"]) != set(owner["suites"]) \
                    or receipt["include_platform"] != owner["include_platform"] \
                    or receipt["platform_results"] != {key: {"status": "passed", "command": command} for key, command in owner["platform"].items()} \
                    or not _time(job.started_at) <= _time(receipt["started_at"]) <= _time(receipt["completed_at"]) <= _time(job.completed_at):
                raise ProtocolError("shared source, selected suites, platform or actual runtime differs from trusted facts")
        except (inputs.InputError, execution.ExecutionError, KeyError, TypeError) as error:
            raise ProtocolError("shared execution receipt does not establish complete original proof") from error
        if hashlib.sha256(canonical(receipt)).hexdigest() != run.final_publisher.receipt_sha256:
            raise ProtocolError("shared receipt differs from the authenticated final publisher commitment")
    return {"verified": True, "run_id": run.run_id, "attempt": run.attempt,
            "final_publisher_job_id": final_job.job_id, "receipt_sha256": run.final_publisher.receipt_sha256,
            "descriptor_digest": descriptor_value["descriptor_digest"], "aggregate_digest": value["aggregate_digest"],
            "qualified_at": value["qualified_at"], "expires_at": value["expires_at"]}
