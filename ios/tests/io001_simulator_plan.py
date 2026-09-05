#!/usr/bin/env python3
"""Validate or execute the bounded credential-free IO-001 simulator plan."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


CONTRACT = "overte-ios-io001-simulator-plan-v1"
EXPECTED_HARNESS = "ios/ci/interface-world-simulator-smoke.sh"
EXPECTED_CASES = {
    "iphone-serverless": ("iphone", "serverless", "none"),
    "iphone-online": ("iphone", "online", "public-domain-uuid"),
    "ipad-serverless": ("ipad", "serverless", "none"),
    "ipad-online": ("ipad", "online", "public-domain-uuid"),
}
CASE_KEYS = {
    "id",
    "family",
    "scenario",
    "expectedDomainBinding",
    "runtimeTimeoutSeconds",
    "outputSubdirectory",
    "requiresCredentials",
}
UUID = re.compile(
    r"\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\}?"
)
BUNDLE_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+"
)
MAX_PLAN_BYTES = 128 * 1024
MAX_CASE_RUNTIME_SECONDS = 600
MAX_TOTAL_RUNTIME_SECONDS = 2400
PROCESS_GRACE_SECONDS = 300


class SimulatorPlanError(ValueError):
    """The plan or a bounded harness invocation is invalid."""


def load_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SimulatorPlanError("simulator plan must be a regular file")
    if not 1 <= path.stat().st_size <= MAX_PLAN_BYTES:
        raise SimulatorPlanError("simulator plan size is out of bounds")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SimulatorPlanError("simulator plan is not valid UTF-8 JSON") from error
    if not isinstance(plan, dict):
        raise SimulatorPlanError("simulator plan root must be an object")
    return plan


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if set(plan) != {"contract", "harness", "maxTotalRuntimeSeconds", "cases"}:
        raise SimulatorPlanError("simulator plan fields do not match the contract")
    if plan["contract"] != CONTRACT:
        raise SimulatorPlanError("simulator plan contract is unsupported")
    if plan["harness"] != EXPECTED_HARNESS:
        raise SimulatorPlanError("simulator plan selects an unexpected harness")
    maximum = plan["maxTotalRuntimeSeconds"]
    if not isinstance(maximum, int) or isinstance(maximum, bool):
        raise SimulatorPlanError("maximum total runtime must be an integer")
    if not 1 <= maximum <= MAX_TOTAL_RUNTIME_SECONDS:
        raise SimulatorPlanError("maximum total runtime is out of bounds")
    cases = plan["cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        raise SimulatorPlanError("simulator plan must contain exactly four cases")

    seen: set[str] = set()
    total = 0
    for case in cases:
        if not isinstance(case, dict) or set(case) != CASE_KEYS:
            raise SimulatorPlanError("simulator case fields do not match the contract")
        case_id = case["id"]
        if case_id not in EXPECTED_CASES or case_id in seen:
            raise SimulatorPlanError("simulator case id is missing, duplicate or unexpected")
        seen.add(case_id)
        expected_family, expected_scenario, expected_binding = EXPECTED_CASES[case_id]
        observed = (case["family"], case["scenario"], case["expectedDomainBinding"])
        if observed != (expected_family, expected_scenario, expected_binding):
            raise SimulatorPlanError("simulator case does not match its declared id")
        if case["outputSubdirectory"] != case_id:
            raise SimulatorPlanError("simulator case output directory is not deterministic")
        if case["requiresCredentials"] is not False:
            raise SimulatorPlanError("IO-001 simulator cases must be credential-free")
        timeout = case["runtimeTimeoutSeconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool):
            raise SimulatorPlanError("simulator case runtime must be an integer")
        if not 1 <= timeout <= MAX_CASE_RUNTIME_SECONDS:
            raise SimulatorPlanError("simulator case runtime is out of bounds")
        total += timeout

    if seen != set(EXPECTED_CASES):
        raise SimulatorPlanError("simulator plan does not cover the exact case matrix")
    if total > maximum:
        raise SimulatorPlanError("simulator case runtimes exceed the declared total bound")
    return cases


def execute_plan(
    plan_path: Path,
    app_path: Path,
    bundle_id: str,
    output_dir: Path,
    online_domain_uuid: str,
    *,
    harness_override: Path | None = None,
    allow_non_darwin: bool = False,
) -> dict[str, Any]:
    """Execute exactly four bounded cases without exposing their raw output."""

    plan = load_plan(plan_path)
    cases = validate_plan(plan)
    if not allow_non_darwin and sys.platform != "darwin":
        raise SimulatorPlanError("real simulator execution requires macOS")
    app_path = app_path.resolve()
    if not app_path.is_dir() or app_path.suffix != ".app":
        raise SimulatorPlanError("candidate app path must be an existing .app directory")
    if BUNDLE_ID.fullmatch(bundle_id) is None:
        raise SimulatorPlanError("bundle identifier is invalid")
    if UUID.fullmatch(online_domain_uuid) is None:
        raise SimulatorPlanError("public online domain UUID is invalid")

    repository_root = Path(__file__).resolve().parents[2]
    harness = (harness_override or (repository_root / plan["harness"])).resolve()
    if not harness.is_file() or not os.access(harness, os.X_OK):
        raise SimulatorPlanError("simulator harness is not executable")
    output_dir.mkdir(parents=True, exist_ok=False)

    completed_ids: list[str] = []
    for case in cases:
        expected_domain = "-" if case["scenario"] == "serverless" else online_domain_uuid
        case_output = output_dir / case["outputSubdirectory"]
        environment = os.environ.copy()
        environment["OVERTE_IOS_WORLD_TIMEOUT_SECONDS"] = str(
            case["runtimeTimeoutSeconds"]
        )
        try:
            completed = subprocess.run(
                [
                    str(harness),
                    str(app_path),
                    bundle_id,
                    case["family"],
                    case["scenario"],
                    expected_domain,
                    str(case_output),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=environment,
                check=False,
                timeout=case["runtimeTimeoutSeconds"] + PROCESS_GRACE_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise SimulatorPlanError(
                f"simulator case {case['id']} exceeded its process bound"
            ) from error
        if completed.returncode != 0:
            raise SimulatorPlanError(f"simulator case {case['id']} failed")
        completed_ids.append(case["id"])

    return {
        "status": "PASS",
        "contract": CONTRACT,
        "completedCases": completed_ids,
        "credentialsUsed": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path(__file__).with_name("io001-simulator-cases.json"),
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--app-path", type=Path)
    parser.add_argument("--bundle-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--online-domain-uuid")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        if args.execute:
            if None in (
                args.app_path,
                args.bundle_id,
                args.output_dir,
                args.online_domain_uuid,
            ):
                raise SimulatorPlanError("execution requires app, bundle, output and online domain")
            summary = execute_plan(
                args.plan,
                args.app_path,
                args.bundle_id,
                args.output_dir,
                args.online_domain_uuid,
            )
        else:
            cases = validate_plan(load_plan(args.plan))
            summary = {
                "status": "PASS",
                "contract": CONTRACT,
                "caseIds": [case["id"] for case in cases],
                "credentialsUsed": False,
                "execution": "NOT_RUN",
            }
    except SimulatorPlanError as error:
        print(f"simulator plan failed: {error}", file=sys.stderr)
        return 1
    json.dump(summary, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
