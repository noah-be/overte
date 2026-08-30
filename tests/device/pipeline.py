#!/usr/bin/env python3
"""Run the common prepare-to-evaluate E2E flow with infrastructure-only retries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from acceptance_policy import load_policy, state_for


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


def event(path: Path, sequence: int, phase: str, status: str) -> int:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"schemaVersion": 1, "sequence": sequence,
                                 "epochMs": int(time.time() * 1000),
                                 "phase": phase, "status": status},
                                separators=(",", ":"), sort_keys=True) + "\n")
    return sequence + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-manifest", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--suite", action="append", required=True)
    parser.add_argument("--fixture-environment", type=Path)
    parser.add_argument("--tablet-policy", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--allow-virtual", action="store_true")
    parser.add_argument("--retry-infrastructure", type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.retry_infrastructure <= 3:
        raise ValueError("--retry-infrastructure must be from 0 through 3")
    policy = load_policy(args.policy.resolve(), args.catalog.resolve())
    suites = list(dict.fromkeys(args.suite))
    for suite in suites:
        state_for(policy, args.platform, suite)
    output = args.output_dir.resolve()
    if output == REPOSITORY or REPOSITORY in output.parents:
        raise ValueError("pipeline output must be outside the worktree")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("pipeline output must be absent or empty")
    output.mkdir(parents=True, mode=0o700)
    timeline = output / "pipeline-timeline.jsonl"
    sequence = event(timeline, 1, "prepare", "started")
    environment = os.environ.copy()
    if args.fixture_environment:
        fixture = json.loads(args.fixture_environment.read_text(encoding="utf-8"))
        values = fixture.get("environment") if isinstance(fixture, dict) else None
        if (fixture.get("schemaVersion") != 1 or not isinstance(values, dict)
                or not all(isinstance(key, str) and isinstance(value, str) and value
                           for key, value in values.items())):
            raise ValueError("fixture environment contract is invalid")
        environment.update(values)
    sequence = event(timeline, sequence, "fixtures", "ready")
    outcomes = []
    final_code = 0
    for suite in suites:
        suite_outcome = None
        for attempt in range(1, args.retry_infrastructure + 2):
            attempt_dir = output / suite / f"attempt-{attempt:02d}"
            sequence = event(timeline, sequence, "reserve-run-cleanup", "started")
            command = [
                sys.executable, str(ROOT / "run.py"),
                "--adapter-manifest", str(args.adapter_manifest.resolve()),
                "--catalog", str(args.catalog.resolve()), "--suite", suite,
                "--output-dir", str(attempt_dir), "--require-complete",
            ]
            if args.allow_virtual:
                command.append("--allow-virtual")
            if args.target:
                command += ["--target", args.target]
            if args.tablet_policy:
                command += ["--tablet-policy", str(args.tablet_policy.resolve())]
            result = subprocess.run(command, env=environment, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    check=False)
            summary_path = attempt_dir / "summary.json"
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                product_failure = any(
                    item["status"] == "failed" for item in summary["results"])
                infrastructure_error = any(
                    item["status"] == "error" for item in summary["results"])
                audit_path = output / "audits" / f"{suite}-attempt-{attempt:02d}.json"
                audit = subprocess.run([
                    sys.executable, str(ROOT / "audit_artifacts.py"),
                    "--result", str(attempt_dir), "--output", str(audit_path),
                ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                security_error = audit.returncode != 0
            else:
                attempt_dir.mkdir(parents=True, exist_ok=True)
                (attempt_dir / "pipeline-driver.json").write_text(
                    json.dumps({"schemaVersion": 1, "runnerExitCode": result.returncode},
                               indent=2, sort_keys=True) + "\n", encoding="utf-8")
                product_failure = security_error = False
                infrastructure_error = True
            classification = ("security-error" if security_error else
                              "product-failure" if product_failure else
                              "infrastructure-error" if infrastructure_error else "passed")
            sequence = event(timeline, sequence, "collect-evaluate", classification)
            suite_outcome = {"suite": suite, "attempt": attempt,
                             "classification": classification,
                             "result": str(attempt_dir.relative_to(output))}
            if security_error or not infrastructure_error or product_failure:
                break
        outcomes.append(suite_outcome)
        if suite_outcome["classification"] in {"infrastructure-error", "security-error"}:
            final_code = 2
        elif suite_outcome["classification"] == "product-failure" and final_code == 0:
            final_code = 1
    event(timeline, sequence, "pipeline", "passed" if final_code == 0 else "failed")
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
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
