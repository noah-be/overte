#!/usr/bin/env python3
"""Run the common plan-to-evaluate E2E flow with owned fixtures and safe retries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from acceptance_policy import STATES, load_policy
from execution_plan import (FIXTURE_ENVIRONMENT, compile_plan, load_profiles,
                            select_suites)


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


class PipelineInterrupted(RuntimeError):
    """The pipeline received a termination signal and must clean up."""


def event(path: Path, sequence: int, phase: str, status: str) -> int:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"schemaVersion": 1, "sequence": sequence,
                                 "epochMs": int(time.time() * 1000),
                                 "phase": phase, "status": status},
                                separators=(",", ":"), sort_keys=True) + "\n")
    return sequence + 1


def load_environment(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    supplied = value.get("environment") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or set(value) != {"schemaVersion", "environment"}
            or not isinstance(supplied, dict)
            or not all(isinstance(key, str) and isinstance(item, str) and item
                       for key, item in supplied.items())):
        raise ValueError("fixture environment contract is invalid")
    return supplied


def wait_ready(path: Path, process: subprocess.Popen, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(value, dict) or value.get("schemaVersion") != 1
                    or set(value) != {
                        "schemaVersion", "environmentFile", "sceneReady", "domainReady"}):
                raise RuntimeError("fixture orchestrator returned invalid readiness metadata")
            return value
        if process.poll() is not None:
            raise RuntimeError("fixture orchestrator exited before readiness")
        time.sleep(0.05)
    raise RuntimeError("fixture orchestrator readiness timed out")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except OSError:
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)


def start_fixture(args: argparse.Namespace, mode: str,
                  temporary: Path) -> tuple[subprocess.Popen, dict[str, str]]:
    fixture_output = temporary / "fixture"
    ready_path = temporary / "ready.json"
    command = [
        sys.executable, str(ROOT / "fixture/orchestrate.py"),
        "--output-dir", str(fixture_output), "--ready-file", str(ready_path),
        "--bind", args.fixture_bind, "--fixture-port", str(args.fixture_port),
    ]
    if args.public_host:
        command += ["--public-host", args.public_host]
    if mode == "scene":
        command.append("--scene-only")
    elif mode == "domain":
        if not args.domain_server or not args.assignment_client:
            raise ValueError(
                "domain fixture requires --domain-server and --assignment-client")
        command += [
            "--domain-server", str(args.domain_server.resolve()),
            "--assignment-client", str(args.assignment_client.resolve()),
            "--domain-port", str(args.domain_port),
            "--domain-http-port", str(args.domain_http_port),
        ]
    else:
        raise ValueError("owned fixture mode must be scene or domain")
    log = (temporary / "fixture-orchestrator.log").open("w", encoding="utf-8")
    try:
        popen_options = {"stdin": subprocess.DEVNULL, "stdout": log,
                         "stderr": subprocess.STDOUT}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True
        process = subprocess.Popen(command, **popen_options)
    finally:
        log.close()
    try:
        ready = wait_ready(ready_path, process)
        expected_domain = mode == "domain"
        if ready["sceneReady"] is not True or ready["domainReady"] is not expected_domain:
            raise RuntimeError("fixture readiness does not match the execution plan")
        return process, load_environment(Path(ready["environmentFile"]))
    except Exception:
        stop_process(process)
        raise


def run_child(command: list[str], environment: dict[str, str]) -> tuple[int, str]:
    options: dict[str, object] = {
        "env": environment, "text": True, "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    try:
        output, _ = process.communicate()
        return process.returncode, output
    except BaseException:
        if process.poll() is None:
            if os.name == "nt":
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                except OSError:
                    process.terminate()
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        raise


def artifact(args: argparse.Namespace, name: str) -> Path | None:
    path = (args.upgrade_source_artifact if name == "source"
            else args.upgrade_candidate_artifact)
    if path is None:
        return None
    resolved = path.resolve()
    if not resolved.is_file() or path.is_symlink():
        raise ValueError(f"upgrade {name} artifact must be a regular non-symlink file")
    return resolved


def executable(path: Path | None, name: str) -> Path | None:
    if path is None:
        return None
    resolved = path.resolve()
    if (not resolved.is_file() or path.is_symlink()
            or (os.name != "nt" and not os.access(resolved, os.X_OK))):
        raise ValueError(f"{name} must be an executable regular non-symlink file")
    return resolved


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-manifest", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--suite", action="append")
    selection.add_argument("--minimum-state", choices=STATES)
    parser.add_argument("--fixture-provider", choices=("auto", "external", "none"),
                        default="auto")
    parser.add_argument("--fixture-environment", type=Path)
    parser.add_argument("--fixture-bind", default="127.0.0.1")
    parser.add_argument("--public-host")
    parser.add_argument("--fixture-port", type=int, default=0)
    parser.add_argument("--domain-server", type=Path)
    parser.add_argument("--assignment-client", type=Path)
    parser.add_argument("--domain-port", type=int, default=40102)
    parser.add_argument("--domain-http-port", type=int, default=40100)
    parser.add_argument("--tablet-policy", type=Path)
    parser.add_argument("--upgrade-source-artifact", type=Path)
    parser.add_argument("--upgrade-candidate-artifact", type=Path)
    parser.add_argument("--upgrade-from-version")
    parser.add_argument("--upgrade-to-version")
    parser.add_argument("--target")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--allow-virtual", action="store_true")
    parser.add_argument("--retry-infrastructure", type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.retry_infrastructure <= 3:
        parser.error("--retry-infrastructure must be from 0 through 3")
    if args.fixture_environment and args.fixture_provider == "auto":
        args.fixture_provider = "external"
    if args.fixture_provider == "external" and not args.fixture_environment:
        parser.error("external fixture provider requires --fixture-environment")
    if args.fixture_provider != "external" and args.fixture_environment:
        parser.error("--fixture-environment requires the external fixture provider")
    return args


def main() -> int:
    args = arguments()
    catalog = args.catalog.resolve()
    policy = load_policy(args.policy.resolve(), catalog)
    profiles = load_profiles(args.profiles.resolve(), catalog)
    suites = select_suites(policy, profiles, args.platform, args.suite, args.minimum_state)
    environment = os.environ.copy()
    if args.upgrade_from_version:
        environment["OVERTE_E2E_UPGRADE_FROM_VERSION"] = args.upgrade_from_version
    if args.upgrade_to_version:
        environment["OVERTE_E2E_UPGRADE_TO_VERSION"] = args.upgrade_to_version
    resolved_artifacts = {name: artifact(args, name) for name in ("source", "candidate")}
    artifacts = {name for name, path in resolved_artifacts.items() if path is not None}
    if resolved_artifacts["source"]:
        environment["OVERTE_E2E_UPGRADE_SOURCE_ARTIFACT"] = str(
            resolved_artifacts["source"])
    if resolved_artifacts["candidate"]:
        environment["OVERTE_E2E_UPGRADE_CANDIDATE_ARTIFACT"] = str(
            resolved_artifacts["candidate"])
    if args.fixture_provider == "external":
        environment.update(load_environment(args.fixture_environment.resolve()))
    resolved_resources = {
        "domain-server": executable(args.domain_server, "domain server"),
        "assignment-client": executable(args.assignment_client, "assignment client"),
    }
    resources = {name for name, path in resolved_resources.items() if path is not None}
    if resolved_resources["domain-server"]:
        args.domain_server = resolved_resources["domain-server"]
    if resolved_resources["assignment-client"]:
        args.assignment_client = resolved_resources["assignment-client"]
    plan = compile_plan(
        policy, catalog, profiles, args.platform, suites, set(environment),
        args.tablet_policy is not None, artifacts, args.fixture_provider, resources)
    if not plan["ready"]:
        raise ValueError("execution plan is not ready: " + ", ".join(plan["missingInputs"]))
    if args.tablet_policy and not args.tablet_policy.resolve().is_file():
        raise ValueError("tablet policy is unavailable")
    output = args.output_dir.resolve()
    if output == REPOSITORY or REPOSITORY in output.parents:
        raise ValueError("pipeline output must be outside the worktree")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("pipeline output must be absent or empty")
    output.mkdir(parents=True, mode=0o700)
    (output / "execution-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    timeline = output / "pipeline-timeline.jsonl"
    sequence = event(timeline, 1, "prepare", "passed")
    fixture_process = None
    interrupted = False

    def interrupt(signum, _frame) -> None:
        raise PipelineInterrupted(f"received signal {signum}")

    handled_signals = [signal.SIGTERM, signal.SIGINT]
    if hasattr(signal, "SIGBREAK"):
        handled_signals.append(signal.SIGBREAK)
    previous_handlers = {
        handled_signal: signal.signal(handled_signal, interrupt)
        for handled_signal in handled_signals
    }
    outcomes = []
    final_code = 0
    try:
        with tempfile.TemporaryDirectory(prefix="overte-e2e-fixture-") as temporary:
            if plan["fixture"] != "none" and args.fixture_provider == "auto":
                sequence = event(timeline, sequence, "fixtures", "starting")
                fixture_process, fixture_environment = start_fixture(
                    args, plan["fixture"], Path(temporary))
                environment.update(fixture_environment)
            missing_fixture = FIXTURE_ENVIRONMENT[plan["fixture"]] - set(environment)
            if missing_fixture:
                raise ValueError("fixture did not provide: " + ", ".join(sorted(missing_fixture)))
            sequence = event(timeline, sequence, "fixtures", "ready")
            for suite in suites:
                suite_outcome = None
                for attempt in range(1, args.retry_infrastructure + 2):
                    attempt_dir = output / suite / f"attempt-{attempt:02d}"
                    if fixture_process is not None and fixture_process.poll() is not None:
                        classification = "infrastructure-error"
                        attempt_dir.mkdir(parents=True, exist_ok=True)
                        (attempt_dir / "pipeline-driver.json").write_text(
                            json.dumps({"schemaVersion": 1,
                                        "failure": "fixture-exited"}, sort_keys=True) + "\n",
                            encoding="utf-8")
                    else:
                        sequence = event(timeline, sequence, "reserve-run-cleanup", "started")
                        command = [
                            sys.executable, str(ROOT / "run.py"),
                            "--adapter-manifest", str(args.adapter_manifest.resolve()),
                            "--catalog", str(catalog), "--suite", suite,
                            "--output-dir", str(attempt_dir), "--require-complete",
                        ]
                        if args.allow_virtual:
                            command.append("--allow-virtual")
                        if args.target:
                            command += ["--target", args.target]
                        if args.tablet_policy:
                            command += ["--tablet-policy", str(args.tablet_policy.resolve())]
                        returncode, _runner_output = run_child(command, environment)
                        summary_path = attempt_dir / "summary.json"
                        if summary_path.is_file():
                            summary = json.loads(summary_path.read_text(encoding="utf-8"))
                            product_failure = any(
                                item["status"] == "failed" for item in summary["results"])
                            infrastructure_error = any(
                                item["status"] == "error" for item in summary["results"])
                            audit_path = output / "audits" / f"{suite}-attempt-{attempt:02d}.json"
                            audit_code, _audit_output = run_child([
                                sys.executable, str(ROOT / "audit_artifacts.py"),
                                "--result", str(attempt_dir), "--output", str(audit_path),
                            ], environment)
                            security_error = audit_code == 1
                            if audit_code not in {0, 1}:
                                infrastructure_error = True
                        else:
                            attempt_dir.mkdir(parents=True, exist_ok=True)
                            (attempt_dir / "pipeline-driver.json").write_text(
                                json.dumps({"schemaVersion": 1, "runnerExitCode": returncode},
                                           indent=2, sort_keys=True) + "\n", encoding="utf-8")
                            product_failure = security_error = False
                            infrastructure_error = True
                        if (fixture_process is not None and fixture_process.poll() is not None
                                and not product_failure and not security_error):
                            infrastructure_error = True
                        classification = ("security-error" if security_error else
                                          "product-failure" if product_failure else
                                          "infrastructure-error" if infrastructure_error else
                                          "passed")
                    sequence = event(timeline, sequence, "collect-evaluate", classification)
                    suite_outcome = {"suite": suite, "attempt": attempt,
                                     "classification": classification,
                                     "result": str(attempt_dir.relative_to(output))}
                    if classification != "infrastructure-error":
                        break
                outcomes.append(suite_outcome)
                if suite_outcome["classification"] in {
                        "infrastructure-error", "security-error"}:
                    final_code = 2
                elif (suite_outcome["classification"] == "product-failure"
                      and final_code == 0):
                    final_code = 1
    except PipelineInterrupted:
        interrupted = True
        final_code = 2
        (output / "pipeline-driver.json").write_text(
            json.dumps({"schemaVersion": 1, "failure": "interrupted"},
                       sort_keys=True) + "\n", encoding="utf-8")
        outcomes.append({"suite": "pipeline", "attempt": 0,
                         "classification": "infrastructure-error",
                         "result": "pipeline-driver.json"})
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError):
        final_code = 2
        (output / "pipeline-driver.json").write_text(
            json.dumps({"schemaVersion": 1, "failure": "pipeline-runtime"},
                       sort_keys=True) + "\n", encoding="utf-8")
        outcomes.append({"suite": "pipeline", "attempt": 0,
                         "classification": "infrastructure-error",
                         "result": "pipeline-driver.json"})
    finally:
        sequence = event(timeline, sequence, "fixtures", "stopping")
        stop_process(fixture_process)
        event(timeline, sequence, "pipeline", "interrupted" if interrupted else
              "passed" if final_code == 0 else "failed")
        for handled_signal, previous in previous_handlers.items():
            signal.signal(handled_signal, previous)
    (output / "pipeline-summary.json").write_text(
        json.dumps({"schemaVersion": 1, "platform": args.platform,
                    "status": "passed" if final_code == 0 else "failed",
                    "outcomes": outcomes}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"Pipeline: {'passed' if final_code == 0 else 'failed'}; {len(suites)} suite(s)")
    return final_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
