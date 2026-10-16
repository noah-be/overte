#!/usr/bin/env python3
"""Dormant sole-owner Android transfer; no generic skip or artifact authority."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/android-owner-transfer.json"
PICO = "pico4-device-free"
OWNED = "tools/repository-checks/workflows/android-owned"


def gate():
    spec = importlib.util.spec_from_file_location("android_transfer_gate", ROOT / "tools/repository-checks/android_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def policy(policy_root=ROOT):
    owner = gate().android()
    value = owner._json(owner._file(Path(policy_root), POLICY))
    if not isinstance(value, dict) or set(value) != {"schema", "repository", "repository_id", "legacy_workflows", "source_contracts", "profiles"} \
            or type(value["schema"]) is not int or value["schema"] != 1 \
            or value["repository"] != "noah-l-frank/overte" or type(value["repository_id"]) is not int \
            or value["repository_id"] != 1319052603 \
            or set(value["legacy_workflows"]) != {".github/workflows/android-tests.yml", ".github/workflows/android-vr-tests.yml"} \
            or set(value["source_contracts"]) != {"android/common/tests/android-workflow-contract-test.py",
                "android/common/tests/ci/validate_ci_contract.py", "android/common/tests/ci/test_ci_contract.py",
                "android/phone/tests/phone-release-metadata-test.py"} \
            or set(value["profiles"]) != {"android-main", "android-phone", "android-vr", "android-vr-pico"}:
        raise ValueError("invalid trusted Android ownership-transfer policy")
    for group in ("legacy_workflows", "source_contracts"):
        for target, item in value[group].items():
            if not isinstance(item, dict) or set(item) != {"source", "reviewed_blob", "mode"} \
                    or item["source"] != OWNED + "/handoff/" + target \
                    or item["mode"] not in {"100644", "100755"} \
                    or not isinstance(item["reviewed_blob"], str) or not re.fullmatch(r"[0-9a-f]{40}", item["reviewed_blob"]):
                raise ValueError("invalid fixed Android handoff source")
    for branch, profile in value["profiles"].items():
        if not isinstance(profile, dict) or set(profile) != {"reviewed_commit", "required_suites"} \
                or not isinstance(profile["reviewed_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", profile["reviewed_commit"]) \
                or not isinstance(profile["required_suites"], list) or len(profile["required_suites"]) != (19 if branch == "android-phone" else 13):
            raise ValueError("incomplete Android profile ownership review")
        _profile({"schema": 1, "platform": "android", "suites": profile["required_suites"]})
    return value


def _profile(value):
    if not isinstance(value, dict) or set(value) != {"schema", "platform", "suites"} \
            or type(value["schema"]) is not int or value["schema"] != 1 or value["platform"] != "android" \
            or not isinstance(value["suites"], list):
        raise ValueError("Android profile must remain a complete ordinary declaration")
    names, commands = {}, set()
    for item in value["suites"]:
        if not isinstance(item, dict) or set(item) != {"name", "entrypoint", "interpreter"} \
                or any(not isinstance(item[key], str) for key in item) \
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", item["name"]) \
                or item["interpreter"] not in {"python", "bash"} or item["name"] in names \
                or item["entrypoint"].startswith("/") or ".." in Path(item["entrypoint"]).parts:
            raise ValueError("invalid or duplicate Android profile suite")
        command = (item["interpreter"], item["entrypoint"])
        if command in commands:
            raise ValueError("Android profile aliases an already owned execution")
        names[item["name"]] = item
        commands.add(command)
    return names


def validate_sources(sources, branch, *, policy_root=ROOT, previous=None):
    """Complete immutable maps prove retirement and preserve every profile extra."""
    document = policy(policy_root)
    for group in ("legacy_workflows", "source_contracts"):
        for target, item in document[group].items():
            data = gate().android()._file(Path(policy_root), item["source"]).read_bytes()
            expected = {**gate()._blob(data), "mode": item["mode"]}
            reviewed = {"mode": item["mode"], "type": "blob", "sha": item["reviewed_blob"]}
            if previous is not None and previous.entries.get(target) not in (reviewed, expected):
                raise ValueError("Android handoff would overwrite an unreviewed predecessor: " + target)
            if sources.entries.get(target) != expected:
                raise ValueError("Android handoff source is missing, altered or nonregular: " + target)
    sources.require(["tests/platform-profile.json"])
    if sources.entries["tests/platform-profile.json"]["mode"] != "100644":
        raise ValueError("Android profile has an unreviewed executable mode")
    observed = _profile(sources.json("tests/platform-profile.json"))
    expected = _profile({"schema": 1, "platform": "android", "suites": document["profiles"][branch]["required_suites"]})
    if any(observed.get(name) != item for name, item in expected.items()):
        raise ValueError("Android transfer drops or changes an existing product profile suite")
    if observed.get(PICO) != {"name": PICO, "entrypoint": "android/vr/pico/tests/pico-device-free-test.sh", "interpreter": "bash"}:
        raise ValueError("the original Pico profile owner must remain available to legacy contexts")
    if previous is not None:
        previous.require(["tests/platform-profile.json"])
        prior = _profile(previous.json("tests/platform-profile.json"))
        if any(observed.get(name) != item for name, item in prior.items()):
            raise ValueError("Android transfer removes or changes a predecessor profile extra")
    sources.require([item["entrypoint"] for item in observed.values()])
    return observed


def runner_context(event, sha, event_name):
    """Before candidate code, bind the actual GitHub caller rather than an input."""
    if event_name not in {"pull_request", "workflow_dispatch"}:
        return False
    if event_name == "pull_request":
        number = event.get("number")
        if type(number) is not int or number <= 0:
            raise ValueError("Android ownership requires the exact PR number")
        ref = f"refs/pull/{number}/merge"
    else:
        ref = "refs/heads/" + event.get("ref", "").removeprefix("refs/heads/")
    expected = {"GITHUB_REPOSITORY": "noah-l-frank/overte", "GITHUB_SHA": sha, "GITHUB_REF": ref,
                "GITHUB_WORKFLOW_REF": "noah-l-frank/overte/.github/workflows/repository-checks.yml@" + ref}
    # Direct project dispatch/push/sync and older callers retain the full profile.
    if not os.environ.get("GITHUB_WORKFLOW_REF", "").startswith(
            "noah-l-frank/overte/.github/workflows/repository-checks.yml@"):
        return False
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise ValueError("Android platform transfer caller or candidate context mismatch")
    if os.environ.get("GITHUB_WORKFLOW_SHA") != sha:
        raise ValueError("Android platform transfer workflow source differs from candidate")
    return True


def platform_owner(candidate, event, sha, event_name, *, policy_root=ROOT):
    """Return a pending ownership plan, never a claim that Pico passed."""
    if not runner_context(event, sha, event_name):
        return {}
    controller = gate()
    current = controller.candidate_plan(candidate, event, sha, event_name=event_name, policy_root=policy_root)
    if not current["required"] or current["target"] not in policy(policy_root)["profiles"]:
        return {}
    controller.validate_execution_generation(candidate, event, policy_root=policy_root)
    return {PICO: {"owner": "required-android", **{key: current[key] for key in ("candidate", "plan", "inventory")}}}



def host_selection():
    spec = importlib.util.spec_from_file_location("android_owned_host_selection", ROOT / "tools/repository-checks/host_selection.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected_host(candidate, event, sha, event_name, *, host=None, expected_plan=None):
    if not runner_context(event, sha, event_name):
        shared, _ = gate().android()._shared()
        if shared.checkout_identity(Path(candidate).resolve(strict=True))[0] != sha:
            raise ValueError("legacy host checkout differs from the runner candidate")
        registry = shared.inputs.load_registry(ROOT / ".github/test-suites.json")
        return {"suites": list(registry["suites"]), "include_platform": True,
                "full_host": True, "reason": "complete-legacy-context"}
    return (host or host_selection()).candidate_selection(candidate, event, sha, expected_plan)


def project(candidate, event, sha, event_name, *, junit, receipt_path, timeout=240, host_timeout=900,
            policy_root=ROOT, expected_plan=None):
    controller = gate()
    shared, _ = controller.android()._shared()
    candidate = Path(candidate).resolve(strict=True)
    if any(Path(path).resolve().is_relative_to(candidate) for path in (junit, receipt_path)):
        raise ValueError("owned project diagnostics must remain outside the immutable candidate")
    if not 1 <= timeout <= 1800 or not 1 <= host_timeout <= 1800:
        raise ValueError("owned project timeouts must remain bounded")
    host = host_selection()
    selected = selected_host(candidate, event, sha, event_name, host=host, expected_plan=expected_plan)
    before = platform_owner(candidate, event, sha, event_name, policy_root=policy_root) if selected["include_platform"] else {}
    # Internal trusted callback only. No execution CLI flag or candidate profile
    # can request an exclusion; the final gate still requires the actual owner.
    status, proof = shared.execute(candidate, suite_names=selected["suites"], include_platform=selected["include_platform"],
                                  junit=junit, receipt_path=receipt_path,
                                  timeout=timeout, host_timeout=host_timeout, _platform_owner=lambda: before,
                                  _impact_selection=not selected["include_platform"])
    try:
        if selected_host(candidate, event, sha, event_name, host=host, expected_plan=expected_plan) != selected:
            raise ValueError("shared host selection changed during project execution")
        after = platform_owner(candidate, event, sha, event_name, policy_root=policy_root) if selected["include_platform"] else {}
        if after != before:
            raise ValueError("Android ownership plan changed during project execution")
    except (ValueError, KeyError, TypeError, OSError):
        proof["conclusion"] = "failure"
        proof["receipt_digest"] = shared.digest({key: value for key, value in proof.items() if key != "receipt_digest"})
        shared._write_receipt(receipt_path, proof)
        raise
    if not selected["include_platform"] or set(selected["suites"]) != set(shared.inputs.load_registry(ROOT / ".github/test-suites.json")["suites"]):
        proof["reusable"], proof["environment"] = False, None
        for result in proof["results"].values():
            result["fingerprint"] = None
        proof["receipt_digest"] = shared.digest({key: value for key, value in proof.items() if key != "receipt_digest"})
        shared._write_receipt(receipt_path, proof)
    return status, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--select-only", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--host-timeout", type=int, default=900)
    args = parser.parse_args()
    try:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise ValueError("Android owned project requires the runner event")
        event = json.loads(Path(event_path).read_text())
        if args.select_only:
            if args.output is None:
                raise ValueError("owned prerequisite selection requires a step output")
            selected = selected_host(args.candidate, event, os.environ.get("GITHUB_SHA"),
                                     os.environ.get("GITHUB_EVENT_NAME"), expected_plan=os.environ.get("EXPECTED_PLAN"))
            with args.output.open("a") as output:
                output.write("full_host=" + str(selected["full_host"]).lower() + "\n")
            return 0
        if args.junit is None or args.receipt is None:
            raise ValueError("owned execution requires fresh reports and receipt paths")
        status, _ = project(args.candidate, event, os.environ.get("GITHUB_SHA"), os.environ.get("GITHUB_EVENT_NAME"),
                            junit=args.junit, receipt_path=args.receipt, timeout=args.timeout, host_timeout=args.host_timeout,
                            expected_plan=os.environ.get("EXPECTED_PLAN"))
        return status
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Android owned project failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
