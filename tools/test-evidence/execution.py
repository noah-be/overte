#!/usr/bin/env python3
"""Execute trusted suite definitions against a clean immutable candidate checkout."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from types import SimpleNamespace

import inputs
import runtime

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = "overte-trusted-test-execution-v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_CANDIDATE_PRIVATE_ENVIRONMENT = (
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STATE",
    "GITHUB_STEP_SUMMARY", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_RUNTIME_URL", "ACTIONS_RESULTS_URL",
)


class ExecutionError(ValueError):
    """A candidate execution or receipt is not an authoritative observation."""


def canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def _git(candidate, *arguments):
    try:
        return subprocess.check_output(["git", "--no-optional-locks", *arguments], cwd=candidate, text=True, stderr=subprocess.PIPE).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExecutionError("candidate checkout identity cannot be verified") from error


def checkout_identity(candidate):
    candidate = Path(candidate).resolve(strict=True)
    if Path(_git(candidate, "rev-parse", "--show-toplevel")).resolve() != candidate:
        raise ExecutionError("candidate must identify the checkout root")
    if _git(candidate, "status", "--porcelain", "--untracked-files=all"):
        raise ExecutionError("candidate checkout must contain only its immutable tracked inputs")
    commit = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}")
    tree = _git(candidate, "rev-parse", "--verify", "HEAD^{tree}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ExecutionError("candidate requires a full immutable Git identity")
    return commit, tree


@contextmanager
def candidate_process_environment():
    """Scope fixed fixture cleanup and credential isolation to candidate children."""
    stripped = set(_CANDIDATE_PRIVATE_ENVIRONMENT) | {"GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}
    stripped.update(name for name in os.environ if re.fullmatch(r"GIT_CONFIG_(?:KEY|VALUE)_[0-9]+", name))
    fixed = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
             "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0"}
    # Preserve the invocation path: resolving this symlink would select the base
    # interpreter's bin directory and discard the prepared virtualenv semantics.
    python_bin = Path(sys.executable).parent
    fixed["PATH"] = str(python_bin) + os.pathsep + os.environ.get("PATH", os.defpath)
    virtual = sys.prefix != sys.base_prefix
    if virtual:
        fixed["VIRTUAL_ENV"] = sys.prefix
    stripped.add("VIRTUAL_ENV")
    affected = stripped | set(fixed)
    previous = {name: os.environ.get(name) for name in affected}
    try:
        for name in stripped:
            os.environ.pop(name, None)
        os.environ.update(fixed)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def capture_execution_environment():
    """Observe the same normalized process environment used by suite children."""
    with candidate_process_environment():
        return runtime.capture_host_environment()


def _runner():
    spec = importlib.util.spec_from_file_location("trusted_execution_project_runner", ROOT / "tests/run-project-tests.py")
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise ExecutionError("trusted test process controller is unavailable")
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def select_common(registry, requested=None):
    if requested is None:
        return list(registry["suites"])
    if not isinstance(requested, list) or len(set(requested)) != len(requested) \
            or any(name not in registry["suites"] for name in requested):
        raise ExecutionError("requested shared suites must be unique trusted registry names")
    return [name for name in registry["suites"] if name in requested]


def platform_suites(candidate, known):
    """Read branch declarations as bounded data, never import a candidate runner."""
    try:
        path = candidate / "tests/platform-profile.json"
        if path.is_symlink() or path.stat().st_size > 100_000:
            raise ExecutionError("candidate platform profile is unsafe")
        profile = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=inputs._unique_object)
        if not isinstance(profile, dict) or set(profile) != {"schema", "platform", "suites"} \
                or type(profile["schema"]) is not int or profile["schema"] != 1 \
                or profile["platform"] not in ("shared", "android") or not isinstance(profile["suites"], list):
            raise ExecutionError("candidate platform profile is invalid")
        if (profile["platform"] == "shared") != (not profile["suites"]):
            raise ExecutionError("candidate platform profile omits required product suites")
        names, result = set(known), []
        for entry in profile["suites"]:
            if not isinstance(entry, dict) or set(entry) != {"name", "entrypoint", "interpreter"}:
                raise ExecutionError("candidate platform suite declaration is invalid")
            name, relative, interpreter = entry["name"], entry["entrypoint"], entry["interpreter"]
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in names:
                raise ExecutionError("candidate platform suite name is invalid or duplicated")
            relative = inputs._path(relative, "platform entrypoint")
            if relative.startswith("-"):
                raise ExecutionError("candidate platform suite entrypoint cannot be an interpreter option")
            path = candidate / relative
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(candidate) \
                    or interpreter not in ("python", "bash"):
                raise ExecutionError("candidate platform suite entrypoint is unavailable or unsafe")
            names.add(name)
            result.append((name, [interpreter, relative]))
        return result
    except (OSError, UnicodeError, json.JSONDecodeError, inputs.InputError, KeyError, TypeError) as error:
        raise ExecutionError("candidate platform profile cannot be validated") from error


def validate_git_context(value, commit, tree):
    """Validate the declared depth-2 source shape; this is not authentication.

    A protected consumer must independently reconstruct and compare this object.
    Content-scoped suite fingerprints deliberately do not include commit IDs.
    """
    if not isinstance(value, dict) or set(value) != {"profile", "commits", "shallow"} \
            or value["profile"] != "streamed-candidate-source-v1" \
            or not isinstance(value["commits"], dict) or not 1 <= len(value["commits"]) <= 8:
        raise ExecutionError("execution receipt Git context is invalid")
    commits = value["commits"]
    for oid, identity in commits.items():
        if not isinstance(oid, str) or re.fullmatch(r"[0-9a-f]{40}", oid) is None or set(oid) == {"0"} \
                or not isinstance(identity, dict) or set(identity) != {"commit", "tree", "parents"} \
                or identity["commit"] != oid or not isinstance(identity["tree"], str) \
                or re.fullmatch(r"[0-9a-f]{40}", identity["tree"]) is None or set(identity["tree"]) == {"0"} \
                or not isinstance(identity["parents"], list) or len(identity["parents"]) > 64 \
                or any(not isinstance(parent, str) or re.fullmatch(r"[0-9a-f]{40}", parent) is None
                       or set(parent) == {"0"} for parent in identity["parents"]) \
                or len(set(identity["parents"])) != len(identity["parents"]):
            raise ExecutionError("execution receipt commit identity is invalid")
    if commit not in commits or commits[commit]["tree"] != tree \
            or set(commits) != {commit, *commits[commit]["parents"]}:
        raise ExecutionError("execution receipt does not describe the exact target and immediate parents")
    shallow = sorted(oid for oid, identity in commits.items() if set(identity["parents"]) - commits.keys())
    if value["shallow"] != shallow:
        raise ExecutionError("execution receipt history boundary is untruthful")
    return value


def validate_receipt(receipt, registry, tree, *, require_all=False, expected_git_context=None,
                     expected_protected_source=None):
    """Verify observed names, statuses and independently recomputed fingerprints."""
    fields = {"schema", "producer", "candidate_commit", "candidate_tree", "environment", "reusable",
              "requested_suites", "include_platform", "results", "platform_results", "conclusion",
              "started_at", "completed_at", "receipt_digest"}
    if not isinstance(receipt, dict) or type(receipt.get("schema")) is not int \
            or (receipt["schema"] == 1 and set(receipt) != fields) \
            or (receipt["schema"] == 2 and set(receipt) != fields | {"platform_selection"}) \
            or (receipt["schema"] == 3 and set(receipt) != fields | {"git_context"}) \
            or (receipt["schema"] == 4 and set(receipt) != fields | {"git_context", "protected_source"}) \
            or receipt["schema"] not in {1, 2, 3, 4} or receipt["producer"] != PRODUCER:
        raise ExecutionError("execution receipt format is invalid")
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_digest")
    if not isinstance(claimed, str) or not _DIGEST.fullmatch(claimed) or digest(unsigned) != claimed:
        raise ExecutionError("execution receipt digest does not match")
    for field in ("candidate_commit", "candidate_tree"):
        if not isinstance(receipt[field], str) or not re.fullmatch(r"[0-9a-f]{40}", receipt[field]):
            raise ExecutionError("execution receipt source identity is invalid")
    if receipt["schema"] in {3, 4}:
        validate_git_context(receipt["git_context"], receipt["candidate_commit"], receipt["candidate_tree"])
        if expected_git_context is not None and receipt["git_context"] != expected_git_context:
            raise ExecutionError("execution receipt Git context differs from independently authenticated source")
    elif expected_git_context is not None:
        raise ExecutionError("legacy execution receipt does not bind its materialized Git context")
    if receipt['schema'] == 4:
        # Versioned source provenance is separate from E. Only this new format
        # loads its fixed validator; tiny/legacy execution remains unchanged.
        import ci_profile
        try:
            source=ci_profile.retained_source_shape(receipt['protected_source'])
            if source['binding']['source'] != receipt['candidate_commit'] \
                    or source['binding']['git_context'] != receipt['git_context']:
                raise ExecutionError('retained source does not bind original materialized candidate')
        except ci_profile.CIProfileError as error:
            raise ExecutionError('retained original source envelope is invalid') from error
    if expected_protected_source is not None and (receipt['schema'] != 4
            or receipt['protected_source'] != expected_protected_source):
        raise ExecutionError('receipt differs from independently authenticated original protected source')
    for field in ("started_at", "completed_at"):
        if receipt["schema"] in {3, 4} and (not isinstance(receipt[field], str)
                or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", receipt[field]) is None):
            raise ExecutionError("isolated execution receipt requires whole UTC seconds")
        try:
            stamp = datetime.fromisoformat(receipt[field].replace("Z", "+00:00"))
        except (TypeError, AttributeError, ValueError) as error:
            raise ExecutionError("execution receipt time is invalid") from error
        if stamp.tzinfo is None:
            raise ExecutionError("execution receipt time must identify UTC")
    if receipt["started_at"] > receipt["completed_at"]:
        raise ExecutionError("execution receipt time order is invalid")
    names = receipt["requested_suites"]
    if not isinstance(names, list) or len(names) != len(set(names)) \
            or any(not isinstance(name, str) or name not in registry["suites"] for name in names):
        raise ExecutionError("execution receipt selected names are invalid")
    if require_all and set(names) != set(registry["suites"]):
        raise ExecutionError("qualification requires actual execution of every shared suite")
    results = receipt["results"]
    if not isinstance(results, dict) or set(results) != set(names) or receipt["conclusion"] != "success":
        raise ExecutionError("execution receipt does not establish complete successful execution")
    if type(receipt["reusable"]) is not bool or type(receipt["include_platform"]) is not bool:
        raise ExecutionError("execution receipt flags are invalid")
    environment = receipt["environment"]
    if (not receipt["reusable"] and environment is not None) or (receipt["reusable"] and not isinstance(environment, dict)):
        raise ExecutionError("execution receipt environment is invalid")
    for name, result in results.items():
        if not isinstance(result, dict) or set(result) != {"status", "fingerprint"} or result["status"] != "passed":
            raise ExecutionError("execution receipt contains an unsuccessful or malformed suite")
        if receipt["reusable"]:
            expected = inputs.suite_fingerprint(registry, name, tree, environment)
            if result["fingerprint"] != expected:
                raise ExecutionError("execution receipt suite fingerprint differs from actual inputs")
        elif result["fingerprint"] is not None:
            raise ExecutionError("nonreusable execution cannot claim source fingerprints")
    platform = receipt["platform_results"]
    if not isinstance(platform, dict) or (not receipt["include_platform"] and platform):
        raise ExecutionError("execution receipt platform observations are invalid")
    for name, result in platform.items():
        if name in registry["suites"] or not isinstance(result, dict) or set(result) != {"status", "command"} \
                or result["status"] != "passed" or not isinstance(result["command"], list) or not result["command"]:
            raise ExecutionError("execution receipt platform suite did not pass")
    if receipt["schema"] == 2:
        selection = receipt["platform_selection"]
        if require_all:
            raise ExecutionError("qualification cannot certify pending independent platform ownership")
        if not isinstance(selection, dict) or set(selection) != {"original", "executed", "delegated", "observed_environment"} \
                or not receipt["include_platform"] or not isinstance(selection["original"], list) \
                or any(not isinstance(name, str) for name in selection["original"]) \
                or len(selection["original"]) != len(set(selection["original"])) \
                or selection["executed"] != [name for name in selection["original"] if name != "pico4-device-free"] \
                or set(selection["executed"]) != set(platform) \
                or not isinstance(selection["delegated"], dict) or set(selection["delegated"]) != {"pico4-device-free"} \
                or "pico4-device-free" not in selection["original"]:
            raise ExecutionError("owned platform execution selection is incomplete")
        if receipt["reusable"] or receipt["environment"] is not None:
            raise ExecutionError("pending platform transfer cannot authorize reusable evidence")
        if selection["observed_environment"] is not None:
            inputs._environment(selection["observed_environment"])
        _validate_platform_owner(selection["delegated"], receipt["candidate_commit"])
    return results


def _validate_platform_owner(value, candidate):
    """Structural diagnostic data only; the required outer gate owns authority."""
    if not isinstance(value, dict) or set(value) != {"pico4-device-free"}:
        raise ExecutionError("only the exact reviewed Pico owner can transfer platform execution")
    proof = value["pico4-device-free"]
    if not isinstance(proof, dict) or set(proof) != {"owner", "candidate", "plan", "inventory"} \
            or proof["owner"] != "required-android" or proof["candidate"] != candidate \
            or any(not isinstance(proof[key], str) or not _DIGEST.fullmatch(proof[key]) for key in ("plan", "inventory")):
        raise ExecutionError("invalid independent Android ownership plan")


def _write_receipt(path, receipt):
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ExecutionError("execution receipt cannot replace a symbolic link")
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("xb") as output:
        output.write(canonical_json(receipt))
    temporary.replace(path)


def execute(candidate, suite_names=None, *, include_platform=False, junit=None, receipt_path=None,
            timeout=240, host_timeout=900, _platform_owner=None, _impact_selection=False):
    candidate = Path(candidate).resolve(strict=True)
    initial = checkout_identity(candidate)
    registry = inputs.load_registry(ROOT / ".github/test-suites.json")
    names = select_common(registry, suite_names)
    product = platform_suites(candidate, registry["suites"]) if include_platform else []
    original_product = [name for name, _ in product]
    delegated = _platform_owner() if _platform_owner is not None else {}
    if type(_impact_selection) is not bool or _impact_selection and (include_platform or delegated):
        raise ExecutionError("partial impact execution cannot delegate or claim a platform inventory")
    if delegated:
        if not include_platform or "pico4-device-free" not in original_product:
            raise ExecutionError("Android transfer requires the complete actual product profile")
        _validate_platform_owner(delegated, initial[0])
        product = [(name, command) for name, command in product if name not in delegated]
    controller = _runner()
    environment = None
    if not _impact_selection:
        try:
            environment = capture_execution_environment()
        except runtime.RuntimeIdentityError as error:
            # Unknown runtime means no omission may be justified by a cached proof.
            names = list(registry["suites"])
            print(f"Host identity unavailable ({error}): executing all shared suites without reusable evidence")
    tree = inputs.full_tree(candidate, initial[0])
    fingerprints = {}
    if environment is not None:
        try:
            fingerprints = {name: inputs.suite_fingerprint(registry, name, tree, environment) for name in names}
        except inputs.InputError:
            environment = None
            names = list(registry["suites"])
            print("Input closure unavailable: executing all shared suites without reusable evidence")
    suites = [controller.Suite(name, registry["suites"][name]["layer"], tuple(
        sys.executable if value == "python" and index == 0 else value
        for index, value in enumerate(registry["suites"][name]["command"]))) for name in names]
    suites += [controller.Suite(name, "quick", tuple(
        sys.executable if value == "python" and index == 0 else value
        for index, value in enumerate(command))) for name, command in product]
    observations = []
    cancelled = []
    previous = {}
    def interrupted(signum, _frame):
        if not cancelled:
            cancelled.append(signum)
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    old_root = controller.ROOT
    original_run_command = controller.run_command
    def run_candidate_command(command, timeout, cancelled):
        with candidate_process_environment():
            return original_run_command(command, timeout, cancelled)
    controller.ROOT = candidate
    controller.run_command = run_candidate_command
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        arguments = SimpleNamespace(timeout=timeout, host_timeout=host_timeout, native_build_dir=None,
                                    junit=junit, fail_fast=False)
        exit_code = controller.run_suites(arguments, suites, cancelled, result_callback=observations.append)
    finally:
        controller.ROOT = old_root
        controller.run_command = original_run_command
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    if checkout_identity(candidate) != initial:
        raise ExecutionError("candidate changed during trusted suite execution")
    if environment is not None:
        try:
            if capture_execution_environment() != environment:
                raise ExecutionError("host environment changed during trusted suite execution")
        except runtime.RuntimeIdentityError as error:
            raise ExecutionError("host environment became unverifiable during execution") from error
    if len(observations) != len(suites) or any(item["status"] != "passed" for item in observations):
        exit_code = exit_code or 1
    common_names = set(names)
    results = {item["name"]: {"status": item["status"], "fingerprint": fingerprints.get(item["name"])
                             if environment is not None else None}
               for item in observations if item["name"] in common_names}
    commands = dict(product)
    platform = {item["name"]: {"status": item["status"], "command": commands[item["name"]]}
                for item in observations if item["name"] not in common_names}
    receipt = {
        "schema": 1, "producer": PRODUCER, "candidate_commit": initial[0], "candidate_tree": initial[1],
        "environment": environment, "reusable": environment is not None, "requested_suites": names,
        "include_platform": include_platform, "results": results, "platform_results": platform,
        "conclusion": "success" if exit_code == 0 and len(observations) == len(suites) else "failure",
        "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if delegated:
        receipt["schema"] = 2
        receipt["platform_selection"] = {"original": original_product, "executed": list(commands),
                                         "delegated": delegated, "observed_environment": environment}
        receipt["environment"], receipt["reusable"] = None, False
        for result in results.values():
            result["fingerprint"] = None
    receipt["receipt_digest"] = digest(receipt)
    _write_receipt(receipt_path, receipt)
    return exit_code, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--suite", action="append")
    parser.add_argument("--include-platform", action="store_true")
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--host-timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 1800 or not 1 <= args.host_timeout <= 1800:
        parser.error("suite timeouts must be from 1 through 1800 seconds")
    try:
        status, _ = execute(args.candidate, args.suite, include_platform=args.include_platform,
                            junit=args.junit, receipt_path=args.receipt,
                            timeout=args.timeout, host_timeout=args.host_timeout)
        return status
    except (ExecutionError, inputs.InputError, OSError, ValueError) as error:
        print(f"trusted execution error: {error}", file=sys.stderr)
        return 2
