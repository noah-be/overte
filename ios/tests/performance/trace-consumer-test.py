#!/usr/bin/env python3
"""Execute iOS trace consumer with original Shared synthetic fixtures, no device."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--shared-contract-root", type=Path, required=True)
parser.add_argument("--fixture-contract-root", type=Path, required=True)
args = parser.parse_args()
ios = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ios / "performance"))
import verify_trace as consumer
consumer.load_analyzer(args.shared_contract_root, ios.parent, args.fixture_contract_root)
sys.path.insert(0, str(ios.parent / "tests/performance/schema"))
import test_metrics as fixture

case = fixture.MetricsTests()
case.setUp()
try:
    command = [sys.executable, str(ios / "performance/verify_trace.py"),
        "--shared-contract-root", str(args.shared_contract_root), "--trace", str(case.path),
        "--fixture-contract-root", str(args.fixture_contract_root),
        "--expected-source-sha", "a" * 40, "--expected-artifact-sha256", "b" * 64,
        "--form-factor", "ipad", "--expected-fixture-sha256", case.fixture]
    def run(extra=()):
        return subprocess.run([*command, *extra], capture_output=True, text=True, timeout=10)
    result = run()
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "METRICS_BOUND_BUDGETS_PENDING"
    assert run(["--fixture-contract-root", str(args.shared_contract_root)]).returncode == 1
    # Old traces/expectations and budgets are not silently upgraded to the new tone.
    old_fixture = "5b529ac6221218630120596eafcb44ba3966d2beab09ee19a8abbeab7fd72154"
    assert case.fixture == "88d94ad1936dd68deeedd9e91f0bb0170621ff69e6ce70c39580c901e679062b"
    assert run(["--expected-fixture-sha256", old_fixture]).returncode == 1
    assert run(["--require-budget"]).returncode == 1
    original = copy.deepcopy(case.trace)
    for change in ({"platform": "ios-iphone"}, {"samples": case.samples[:-1]},
                   {"fixtureSha256": "c" * 64}, {"fixtureSha256": old_fixture},
                   {"artifactSha256": "c" * 64}):
        case.trace = copy.deepcopy(original)
        case.trace.update(change)
        case.write()
        rejected = run()
        assert rejected.returncode == 1 and rejected.stderr.strip() == "IOS_PERFORMANCE_TRACE_REJECTED"
    for field, value in (("blackFrames", None), ("blackFrames", 1), ("thermal", "critical"),
                         ("frameP95Ms", None), ("processEnergyJoules", 0)):
        case.trace = copy.deepcopy(original)
        case.trace["samples"][1][field] = value
        case.write()
        assert run().returncode == 1
    case.trace = original
    case.write()
    # Explicitly synthetic values, NOT approved iOS production budgets.
    budget = dict(contract="overte-sh008-budget-v1", platform="ios-ipad", fixtureSha256=case.fixture,
        memoryKind="ios-physical-footprint", maxFrameP95Ms=15, maxMemoryGrowthBytes=0,
        maxQueueDepth=1, minBatteryEndPercent=80)
    budget_path = case.root / "synthetic-budget.json"
    budget_path.write_text(json.dumps(budget))
    digest = hashlib.sha256(budget_path.read_bytes()).hexdigest()
    result = run(["--require-budget", "--budget", str(budget_path), "--expected-budget-sha256", digest])
    assert result.returncode == 0 and json.loads(result.stdout)["status"] == "BUDGETS_CHECKED_NOT_NODE_ACCEPTED"
    assert run(["--budget", str(budget_path), "--expected-budget-sha256", "c" * 64]).returncode == 1
    budget["fixtureSha256"] = old_fixture
    budget_path.write_text(json.dumps(budget))
    old_budget_digest = hashlib.sha256(budget_path.read_bytes()).hexdigest()
    assert run(["--budget", str(budget_path), "--expected-budget-sha256", old_budget_digest]).returncode == 1
finally:
    case.doCleanups()
print("PASS real iOS Shared v001 analyzer/v002 fixture consumer, old trace/budget rejection; synthetic only")
