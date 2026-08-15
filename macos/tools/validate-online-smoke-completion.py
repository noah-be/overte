#!/usr/bin/env python3
"""Validate durable online-smoke completion and supervisor evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


class ValidationError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"unable to read valid JSON from {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{path.name} must contain a JSON object")
    return value


def validate(completion: dict[str, object], process: dict[str, object]) -> dict[str, object]:
    expected_completion = {
        "schema_version",
        "ready_for_external_validation",
        "script_success",
    }
    if set(completion) != expected_completion:
        raise ValidationError("completion sentinel has an unexpected field set")
    if completion["schema_version"] != 1:
        raise ValidationError("completion sentinel schema_version must be 1")
    if completion["ready_for_external_validation"] is not True:
        raise ValidationError("online script did not reach external validation")
    if completion["script_success"] is not True:
        raise ValidationError("online script reported failure")

    required_process = {
        "exit_code",
        "timed_out",
        "completion_file_observed",
        "terminated_after_completion",
        "sent_sigterm",
    }
    missing = required_process - set(process)
    if missing:
        raise ValidationError(
            "process evidence is missing: " + ", ".join(sorted(missing))
        )
    if process["timed_out"] is not False:
        raise ValidationError("online process reached its outer timeout")
    if process["completion_file_observed"] is not True:
        raise ValidationError("supervisor did not observe completion evidence")

    controlled = process["terminated_after_completion"] is True
    natural = process["terminated_after_completion"] is False and process["exit_code"] == 0
    if not (controlled or natural):
        raise ValidationError("online process neither exited cleanly nor was stopped after completion")
    if controlled and process["sent_sigterm"] is not True:
        raise ValidationError("controlled completion did not record SIGTERM forwarding")

    return {
        "schema_version": 1,
        "passed": True,
        "process_mode": "controlled-completion" if controlled else "natural-exit",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("completion", type=Path)
    parser.add_argument("process", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(_load(args.completion), _load(args.process))
    except ValidationError as exc:
        print(f"online completion validation failed: {exc}", file=sys.stderr)
        return 1
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"macOS online completion valid ({result['process_mode']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
