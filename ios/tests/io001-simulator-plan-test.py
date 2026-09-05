#!/usr/bin/env python3
"""Focused host tests for the bounded four-case IO-001 simulator plan."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


TESTS = Path(__file__).resolve().parent
PLAN = TESTS / "io001-simulator-cases.json"
sys.path.insert(0, str(TESTS))

import io001_simulator_plan as simulator  # noqa: E402


plan = simulator.load_plan(PLAN)
cases = simulator.validate_plan(plan)
assert [case["id"] for case in cases] == [
    "iphone-serverless",
    "iphone-online",
    "ipad-serverless",
    "ipad-online",
]
assert {(case["family"], case["scenario"]) for case in cases} == {
    ("iphone", "serverless"),
    ("iphone", "online"),
    ("ipad", "serverless"),
    ("ipad", "online"),
}
assert all(case["requiresCredentials"] is False for case in cases)
assert sum(case["runtimeTimeoutSeconds"] for case in cases) <= plan[
    "maxTotalRuntimeSeconds"
]


def expect_rejection(mutated: dict, expected: str) -> None:
    try:
        simulator.validate_plan(mutated)
    except simulator.SimulatorPlanError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError(f"unsafe simulator plan accepted: {expected}")


missing = copy.deepcopy(plan)
missing["cases"].pop()
expect_rejection(missing, "exactly four cases")

duplicate = copy.deepcopy(plan)
duplicate["cases"][3] = copy.deepcopy(duplicate["cases"][0])
expect_rejection(duplicate, "missing, duplicate or unexpected")

credentialed = copy.deepcopy(plan)
credentialed["cases"][0]["requiresCredentials"] = True
expect_rejection(credentialed, "must be credential-free")

unbounded = copy.deepcopy(plan)
unbounded["cases"][0]["runtimeTimeoutSeconds"] = 601
expect_rejection(unbounded, "runtime is out of bounds")

wrong_harness = copy.deepcopy(plan)
wrong_harness["harness"] = "ios/tests/unreviewed-runner.sh"
expect_rejection(wrong_harness, "unexpected harness")

with tempfile.TemporaryDirectory(prefix="io001-simulator-execute-") as temporary:
    root = Path(temporary)
    app = root / "Overte.app"
    app.mkdir()
    log = root / "calls.jsonl"
    harness = root / "fake-harness.py"
    harness.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"log = pathlib.Path({json.dumps(str(log))})\n"
        "with log.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    harness.chmod(0o700)
    output = root / "evidence"
    public_domain = "11111111-1111-4111-8111-111111111111"
    summary = simulator.execute_plan(
        PLAN,
        app,
        "org.overte.interface.e2e",
        output,
        public_domain,
        harness_override=harness,
        allow_non_darwin=True,
    )
    assert summary["completedCases"] == [case["id"] for case in cases]
    assert summary["credentialsUsed"] is False
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 4
    assert [(call[2], call[3]) for call in calls] == [
        ("iphone", "serverless"),
        ("iphone", "online"),
        ("ipad", "serverless"),
        ("ipad", "online"),
    ]
    assert calls[0][4] == "-" and calls[2][4] == "-"
    assert calls[1][4] == public_domain and calls[3][4] == public_domain
    assert all(call[1] == "org.overte.interface.e2e" for call in calls)

completed = subprocess.run(
    [sys.executable, str(TESTS / "io001_simulator_plan.py"), "--plan", str(PLAN)],
    check=False,
    capture_output=True,
    text=True,
    timeout=30,
)
assert completed.returncode == 0, completed.stderr
summary = json.loads(completed.stdout)
assert summary["caseIds"] == [case["id"] for case in cases]
assert summary["execution"] == "NOT_RUN"

print("PASS bounded credential-free IO-001 simulator plan")
