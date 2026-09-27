#!/usr/bin/env python3
"""Inspect iOS failures and distinguish workflow, artifact and installation evidence.

Reads use gh's authenticated API. Dispatch is an explicit subcommand, binds the
fork and exact current apple-ios tip, and requires a recorded diagnosis of the
latest failed build. No log content, devices or signing material is published.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote


REPOSITORY = "noah-be/overte"
REPOSITORY_ID = 1319052603
WORKFLOW = "ios-bootstrap.yml"
HISTORY_WORKFLOWS = (WORKFLOW, "ios-build-qualification.yml")
FAILURES = {"failure", "timed_out", "startup_failure"}
BUILD_JOB = "Toolchain, dependencies, build and package"


def require(value, message):
    if not value:
        raise ValueError(message)


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True, stderr=subprocess.PIPE, timeout=90)


def api(path):
    require(path == f"repos/{REPOSITORY}" or path.startswith(f"repos/{REPOSITORY}/"),
            "foreign API target")
    return json.loads(gh("api", path))


def run_record(run):
    return {"runId": run["id"], "runAttempt": run["run_attempt"],
            "workflow": {"id": run.get("workflow_id"), "path": run.get("path"),
                         "name": run.get("name")},
            "buildNumber": run["run_number"], "sourceRevision": run["head_sha"],
            "branch": run["head_branch"], "status": run["status"],
            "conclusion": run["conclusion"], "url": run["html_url"]}


def analyze(runs, jobs, artifacts, current_source):
    """Workflow success alone is never a produced or installed application."""
    result = {"sourceRevision": current_source, "latestWorkflow": None,
              "latestDeviceBuild": None, "latestFailure": None,
              "installation": {"status": "unknown", "reason": "no installation receipt supplied"}}
    ordered = sorted(runs, key=lambda run: (run["created_at"], run["id"]), reverse=True)
    if ordered:
        result["latestWorkflow"] = run_record(ordered[0])
    for run in ordered:
        record = run_record(run)
        job_list = jobs(run["id"])
        device_jobs = [job for job in job_list if job["name"].endswith(BUILD_JOB)]
        if result["latestFailure"] is None and run["conclusion"] in FAILURES:
            failed = [job for job in job_list if job["conclusion"] in FAILURES]
            result["latestFailure"] = {**record, "failedJobs": [job["name"] for job in failed]}
        if (result["latestDeviceBuild"] is None and run["conclusion"] == "success"
                and device_jobs and all(job["conclusion"] == "success" for job in device_jobs)):
            packaged = any(any(step.get("name") == "Package numbered unsigned client IPA"
                               and step.get("conclusion") == "success" for step in job.get("steps", []))
                           for job in device_jobs)
            if not packaged:
                continue
            expected = f"{run['run_number']}-overte-ios-integrated-e2e-unsigned-{run['id']}"
            matches = [a for a in artifacts(run["id"]) if a["name"] == expected]
            # Preserve the newest known production even after artifact retention
            # expires. Never silently substitute an older downloadable build.
            availability = "missing" if not matches else "ambiguous"
            if len(matches) == 1:
                availability = "expired" if matches[0]["expired"] else "available"
            result["latestDeviceBuild"] = {
                **record, "artifactId": matches[0]["id"] if len(matches) == 1 else None,
                "artifact": expected, "availability": availability,
                "integrity": "not-downloaded-or-verified",
                "matchesCurrentBranch": (run["event"] != "pull_request"
                                         and run["head_sha"] == current_source),
                "sourceIdentity": "manifest-required" if run["event"] == "pull_request" else "run-source"}
        if result["latestFailure"] is not None and result["latestDeviceBuild"] is not None:
            break
    return result


def installation_evidence(receipt, current_source):
    require(isinstance(receipt, dict), "invalid installation receipt")
    require(receipt.get("status") == "installed-and-vm-stopped", "installation was not completed")
    require(re.fullmatch(r"[0-9a-f]{40}", receipt.get("source", "")), "missing installed source")
    require(re.fullmatch(r"[0-9a-f]{64}", receipt.get("sha256", "")), "missing installed IPA digest")
    require(type(receipt.get("build")) is int and receipt["build"] > 0, "missing installed build number")
    require(receipt.get("utc") and receipt.get("ipadReturnedToFedora") is True,
            "incomplete installation receipt")
    # This reports a supplied local historical receipt, not a fresh device query.
    return {"status": "historical-installation-receipt", "sourceRevision": receipt["source"],
            "buildNumber": receipt["build"], "ipaSha256": receipt["sha256"],
            "recordedAt": receipt["utc"], "matchesCurrentBranch": receipt["source"] == current_source,
            "currentDeviceState": "not-rechecked", "deviceAcceptance": "not-proven"}


def review_failure(report, reviewed_run, diagnosis, retry_reason):
    failure = report["latestFailure"]
    if not failure:
        return {"priorFailure": None}
    require(reviewed_run == failure["runId"], "inspect and identify the latest failed run before dispatch")
    require(isinstance(diagnosis, str) and len(diagnosis.strip()) >= 30,
            "record a concrete failure diagnosis and the repair before dispatch")
    same_source = failure["sourceRevision"] == report["sourceRevision"]
    require(not same_source or (retry_reason and len(retry_reason.strip()) >= 30),
            "same-source failed build: record a concrete external-state repair before retrying")
    return {"priorFailure": failure["runId"], "diagnosis": diagnosis.strip(),
            "sameSource": same_source, "retryReason": retry_reason or None}


def failure_diagnostics(run_id):
    try:
        log = gh("run", "view", str(run_id), "--repo", REPOSITORY, "--log-failed")
    except subprocess.SubprocessError:
        # Retention may remove historical logs. Keep the known failure visible
        # without treating a missing log as a new compiler failure or success.
        return {"missingHeaders": [], "failedLogInspected": False,
                "logAvailability": "unavailable", "diagnosis": "unknown"}
    missing = sorted(set(re.findall(r"fatal error: ['\"]([A-Za-z0-9_./-]+)['\"] file not found", log)))
    return {"missingHeaders": missing[:20], "failedLogInspected": True,
            "logAvailability": "available"}


def read_history():
    inventory = api(f"repos/{REPOSITORY}/actions/workflows?per_page=100")
    require(inventory["total_count"] <= len(inventory["workflows"]),
            "incomplete workflow inventory")
    runs, coverage = [], {}
    for name in HISTORY_WORKFLOWS:
        path = f".github/workflows/{name}"
        matches = [item for item in inventory["workflows"] if item["path"] == path]
        require(len(matches) <= 1, "ambiguous workflow identity")
        if not matches:
            require(name != WORKFLOW, "bootstrap workflow is not registered")
            coverage[name] = {"status": "not-registered", "runLimit": 50}
            continue
        workflow = matches[0]
        require(type(workflow["id"]) is int and workflow["id"] > 0, "invalid workflow identity")
        selected = api(f"repos/{REPOSITORY}/actions/workflows/{workflow['id']}/runs?per_page=50")["workflow_runs"]
        for run in selected:
            require(run["workflow_id"] == workflow["id"]
                    and run["repository"]["full_name"] == REPOSITORY
                    and run["repository"]["id"] == REPOSITORY_ID, "foreign workflow history")
        runs.extend(selected)
        coverage[name] = {"status": "inspected", "workflowId": workflow["id"],
                          "runLimit": 50, "runsRead": len(selected)}
    require(len({run["id"] for run in runs}) == len(runs), "duplicate run identity")
    return runs, coverage


def snapshot(ref="apple-ios"):
    require(ref == "apple-ios", "this device-build handoff only targets apple-ios")
    repo = api(f"repos/{REPOSITORY}")
    require(repo["full_name"] == REPOSITORY and repo["id"] == REPOSITORY_ID, "repository identity mismatch")
    source = api(f"repos/{REPOSITORY}/git/ref/heads/{quote(ref, safe='')}")["object"]["sha"]
    # Include sibling topics and qualification PRs; their failures must not be
    # hidden by a later host-only bootstrap success.
    runs, coverage = read_history()
    def jobs(run_id):
        response = api(f"repos/{REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100")
        require(response["total_count"] <= len(response["jobs"]), "incomplete job inventory")
        return response["jobs"]
    def artifacts(run_id):
        response = api(f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100")
        require(response["total_count"] <= len(response["artifacts"]), "incomplete artifact inventory")
        return response["artifacts"]
    report = analyze(runs, jobs, artifacts, source)
    report.update(schema=1, repository=REPOSITORY, repositoryId=REPOSITORY_ID,
                  ref=ref, historyLimitPerWorkflow=50, workflows=coverage,
                  capturedAt=datetime.now(timezone.utc).isoformat())
    if report["latestFailure"]:
        run_id = report["latestFailure"]["runId"]
        # Emit only bounded compiler diagnostic categories, never raw hosted logs.
        report["latestFailure"]["diagnostics"] = failure_diagnostics(run_id)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "dispatch"))
    parser.add_argument("--ref", default="apple-ios")
    parser.add_argument("--installation-receipt", type=Path)
    parser.add_argument("--reviewed-failure-run", type=int)
    parser.add_argument("--diagnosis")
    parser.add_argument("--retry-reason")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = snapshot(args.ref)
        if args.installation_receipt:
            report["installation"] = installation_evidence(json.loads(args.installation_receipt.read_text()),
                                                           report["sourceRevision"])
        if args.command == "dispatch":
            report["review"] = review_failure(report, args.reviewed_failure_run, args.diagnosis, args.retry_reason)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        args.output.chmod(0o600)
        if args.command == "dispatch":
            repo = api(f"repos/{REPOSITORY}")
            require(repo["full_name"] == REPOSITORY and repo["id"] == REPOSITORY_ID, "write target mismatch")
            require(api(f"repos/{REPOSITORY}/git/ref/heads/apple-ios")["object"]["sha"] == report["sourceRevision"],
                    "apple-ios moved after the reviewed preflight; inspect the new revision")
            dispatched = gh("workflow", "run", WORKFLOW, "--repo", REPOSITORY,
                            "--ref", "apple-ios", "-f", "integrated=true").strip()
            match = re.fullmatch(r"https://github.com/noah-be/overte/actions/runs/([0-9]+)", dispatched)
            require(match, "dispatch returned no exact run URL; inspect Actions before any retry")
            run = api(f"repos/{REPOSITORY}/actions/runs/{match[1]}")
            require(run["repository"]["full_name"] == REPOSITORY
                    and run["repository"]["id"] == REPOSITORY_ID
                    and run["head_branch"] == "apple-ios" and run["head_sha"] == report["sourceRevision"],
                    "dispatched revision changed; do not report it as the reviewed build")
            report["dispatched"] = run_record(run)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 0
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"iOS build handoff failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
