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
        return subprocess.check_output(["git", *arguments], cwd=candidate, text=True, stderr=subprocess.PIPE).strip()
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


def validate_receipt(receipt, registry, tree, *, require_all=False):
    """Verify observed names, statuses and independently recomputed fingerprints."""
    fields = {"schema", "producer", "candidate_commit", "candidate_tree", "environment", "reusable",
              "requested_suites", "include_platform", "results", "platform_results", "conclusion",
              "started_at", "completed_at", "receipt_digest"}
    if not isinstance(receipt, dict) or set(receipt) != fields or type(receipt["schema"]) is not int \
            or receipt["schema"] != 1 or receipt["producer"] != PRODUCER:
        raise ExecutionError("execution receipt format is invalid")
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_digest")
    if not isinstance(claimed, str) or not _DIGEST.fullmatch(claimed) or digest(unsigned) != claimed:
        raise ExecutionError("execution receipt digest does not match")
    for field in ("candidate_commit", "candidate_tree"):
        if not isinstance(receipt[field], str) or not re.fullmatch(r"[0-9a-f]{40}", receipt[field]):
            raise ExecutionError("execution receipt source identity is invalid")
    for field in ("started_at", "completed_at"):
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
    return results


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
            timeout=240, host_timeout=900):
    candidate = Path(candidate).resolve(strict=True)
    initial = checkout_identity(candidate)
    registry = inputs.load_registry(ROOT / ".github/test-suites.json")
    names = select_common(registry, suite_names)
    product = platform_suites(candidate, registry["suites"]) if include_platform else []
    controller = _runner()
    environment = None
    try:
        environment = runtime.capture_host_environment()
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
            if runtime.capture_host_environment() != environment:
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
