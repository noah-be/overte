#!/usr/bin/env python3
"""Run one real platform/suite cell repeatedly without retrying product failures."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


def checked_pipeline_arguments(values: list[str]) -> list[str]:
    arguments = list(values)
    if arguments and arguments[0] == "--":
        arguments.pop(0)
    if not arguments:
        raise ValueError("pipeline arguments are required after --")
    forbidden = {"--output-dir", "--retry-infrastructure"}
    for value in arguments:
        option = value.split("=", 1)[0]
        if option in forbidden:
            raise ValueError(f"campaign owns {option}")
    if sum(value == "--suite" or value.startswith("--suite=") for value in arguments) != 1:
        raise ValueError("stability campaign requires exactly one explicit suite")
    if any(value == "--minimum-state" or value.startswith("--minimum-state=")
           for value in arguments):
        raise ValueError("stability campaign does not accept lifecycle suite expansion")
    return arguments


def private_output(path: Path) -> Path:
    output = path.expanduser().resolve()
    if output == REPOSITORY or REPOSITORY in output.parents:
        raise ValueError("campaign output must be outside the worktree")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("campaign output must be absent or empty")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(output, 0o700)
    return output


def pipeline_outcome(path: Path) -> tuple[str, list[Path], int]:
    value = json.loads((path / "pipeline-summary.json").read_text(encoding="utf-8"))
    outcomes = value.get("outcomes") if isinstance(value, dict) else None
    if (value.get("schemaVersion") != 1 or not isinstance(outcomes, list)
            or len(outcomes) != 1):
        raise ValueError("stability iteration returned an invalid pipeline summary")
    outcome = outcomes[0]
    classification = outcome.get("classification") if isinstance(outcome, dict) else None
    attempt = outcome.get("attempt") if isinstance(outcome, dict) else None
    result = outcome.get("result") if isinstance(outcome, dict) else None
    if (classification not in {"passed", "product-failure", "infrastructure-error",
                               "security-error"}
            or not isinstance(attempt, int) or attempt < 1
            or not isinstance(result, str)):
        raise ValueError("stability iteration outcome is invalid")
    run = (path / result).resolve()
    if path.resolve() not in run.parents or not run.is_dir():
        raise ValueError("stability iteration result escaped its directory")
    history = []
    suite_root = run.parent
    for index in range(1, attempt + 1):
        candidate = suite_root / f"attempt-{index:02d}"
        if (candidate / "run-manifest.json").is_file() \
                and (candidate / "summary.json").is_file():
            history.append(candidate)
    return classification, history, attempt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--retry-infrastructure", type=int, default=1)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("pipeline_arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not 10 <= args.repetitions <= 20:
        parser.error("--repetitions must be from 10 through 20")
    if not 0 <= args.retry_infrastructure <= 3:
        parser.error("--retry-infrastructure must be from 0 through 3")
    pipeline_arguments = checked_pipeline_arguments(args.pipeline_arguments)
    output = private_output(args.output_dir)
    iterations = []
    history_inputs: list[Path] = []
    status = "passed"
    exit_code = 0
    for sequence in range(1, args.repetitions + 1):
        iteration = output / f"run-{sequence:02d}"
        command = [
            sys.executable, str(ROOT / "pipeline.py"), *pipeline_arguments,
            "--retry-infrastructure", str(args.retry_infrastructure),
            "--output-dir", str(iteration),
        ]
        completed = subprocess.run(command, check=False)
        try:
            classification, history, attempts = pipeline_outcome(iteration)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            classification, history, attempts = "infrastructure-error", [], 0
        history_inputs.extend(history)
        iterations.append({
            "sequence": sequence,
            "classification": classification,
            "infrastructureAttempts": attempts,
            "result": iteration.name,
        })
        print(f"Stability {sequence}/{args.repetitions}: {classification}", flush=True)
        if classification != "passed":
            status = classification
            exit_code = 1 if classification == "product-failure" else 2
            break
        if completed.returncode != 0:
            status = "infrastructure-error"
            exit_code = 2
            break
    history_path = output / "history.json"
    if history_inputs:
        history_command = [sys.executable, str(ROOT / "analyze_history.py")]
        for path in history_inputs:
            history_command += ["--result", str(path)]
        history_command += ["--output", str(history_path)]
        if subprocess.run(history_command, check=False).returncode != 0:
            status = "infrastructure-error"
            exit_code = 2
    summary = {
        "schemaVersion": 1,
        "requestedRepetitions": args.repetitions,
        "completedRepetitions": len(iterations),
        "status": status,
        "productFailureRetries": 0,
        "iterations": iterations,
        "history": history_path.name if history_path.is_file() else None,
    }
    (output / "campaign-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
