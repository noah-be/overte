"""Candidate identity and append-only test records; no inferred test execution."""
import hashlib
import json
import re
from datetime import datetime, timezone

PIN = re.compile(r"<!-- overte-candidate:v1 (.*?) -->")
RECORD_HEADING = "Candidate-bound test records"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def criterion_id(draft):
    return fingerprint({"milestone": draft.get("milestone"), "platforms": draft["platforms"],
                        "fields": {k: draft["fields"].get(k) for k in
                                   ("scope", "outcome", "done_criteria", "required_checks")}})


def check_candidate(value, platforms):
    keys = {"revision", "artifact_sha256", "build_url", "platform", "environment"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Candidate needs revision, artifact_sha256, build_url, platform and environment")
    if not re.fullmatch(r"[0-9a-f]{40}", value.get("revision", "")):
        raise ValueError("Candidate revision must be a full immutable Git commit")
    if not re.fullmatch(r"[0-9a-f]{64}", value.get("artifact_sha256", "")):
        raise ValueError("Candidate needs the SHA256 of the exact installed/tested artifact")
    if value.get("platform") not in platforms:
        raise ValueError("Candidate platform must match the documented scope")
    for key in ("build_url", "environment"):
        if not isinstance(value[key], str) or not value[key].strip() or value[key].strip().lower() in ("unknown", "todo", "none") or "\n" in value[key]:
            raise ValueError(f"Candidate {key} must identify retained provenance and the test environment")


def pinned(milestone, platforms):
    body = milestone.get("description") or ""
    if "<!-- overte-candidate:" not in body:
        return None
    matches = PIN.findall(body)
    if len(matches) != 1 or body.count("<!-- overte-candidate:") != 1:
        raise ValueError("Milestone has malformed or multiple candidate pins")
    value = json.loads(matches[0])
    check_candidate(value, platforms)
    return value


def check_runs(draft):
    runs = draft.get("test_runs", [])
    if not isinstance(runs, list) or (runs and draft.get("kind") != "acceptance"):
        raise ValueError("test_runs is an acceptance-only list")
    previous = {}
    for run in runs:
        required = {"id", "candidate", "criterion_sha256", "tested_at", "result", "observations", "evidence", "limitations"}
        if not isinstance(run, dict) or set(run) != required:
            raise ValueError("Each test record needs an ID, candidate, criterion hash, UTC date, result, observations, evidence and limitations")
        if not isinstance(run["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", run["id"]) or run["id"] in previous:
            raise ValueError("Test record IDs must be nonempty and unique")
        check_candidate(run["candidate"], draft["platforms"])
        if not re.fullmatch(r"[0-9a-f]{64}", run["criterion_sha256"]):
            raise ValueError("Test record needs its immutable criterion hash")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", run["tested_at"]):
            raise ValueError("Test date must be YYYY-MM-DDTHH:MM:SSZ")
        if datetime.fromisoformat(run["tested_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc):
            raise ValueError("A future date cannot establish completed testing")
        if run["result"] not in ("passed", "failed", "blocked"):
            raise ValueError("Test result must be passed, failed or blocked")
        for key in ("observations", "limitations"):
            if not isinstance(run[key], str) or not run[key].strip():
                raise ValueError(f"Test record needs {key}")
        if not isinstance(run["evidence"], list) or not run["evidence"] or any(not isinstance(x, str) or not x.strip() for x in run["evidence"]):
            raise ValueError("Test record needs retained evidence references")
        if previous and run["tested_at"] < max(x["tested_at"] for x in previous.values()):
            raise ValueError("Append test records in chronological order")
        previous[run["id"]] = run


def status(draft, candidate):
    check_runs(draft)
    if candidate is None:
        return "no-candidate"
    check_candidate(candidate, draft["platforms"])
    applicable = [x for x in draft.get("test_runs", [])
                  if x["candidate"] == candidate and x["criterion_sha256"] == criterion_id(draft)]
    return applicable[-1]["result"] if applicable else "needs-test"


def label(status_value, policy):
    # Failed/blocked remain visible in the report; all need action rather than a pass.
    key = "verified" if status_value == "passed" else "no_candidate" if status_value == "no-candidate" else "needs_test"
    return policy["acceptance_labels"][key]


def apply_label(existing, draft, candidate, policy):
    result = set(existing) - set(policy.get("acceptance_labels", {}).values())
    if draft["kind"] == "acceptance" and policy.get("acceptance_labels"):
        result.add(label(status(draft, candidate), policy))
    return sorted(result)
