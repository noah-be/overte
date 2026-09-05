#!/usr/bin/env python3
"""Exercise actual iOS checkpoint consumer with General's synthetic result fixture."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--shared-contract-root", type=Path, required=True)
args = parser.parse_args()
ios = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ios / "acceptance"))
import verify_checkpoint as consumer
consumer.verify_release(args.shared_contract_root, consumer.MANIFEST_SHA256, consumer.ENTRYPOINT, executable=False)
sys.path.insert(0, str(args.shared_contract_root / "tests/device/schema"))
import test_result_binding as fixtures

case = fixtures.ResultBindingTests()
case.setUp()
try:
    catalog = json.loads((args.shared_contract_root / "tests/device/catalog.json").read_text())
    selected = [item for item in catalog["modules"] if "e2e-core" in item["suites"]]
    case.run.update(adapter="appium-ios", platform="ios", physical=True, suite="e2e-core",
                    modules=[item["id"] for item in selected],
                    capabilities=sorted(set(op for item in selected for op in item["requires"])))
    template = case.summary["results"][0]
    case.summary.update(adapter="appium-ios", suite="e2e-core", results=[
        dict(template, id=item["id"], description=item["description"]) for item in selected])
    tree = ET.fromstring(case.xml)
    original = tree.find("testcase")
    tree.remove(original)
    tree.set("tests", str(len(selected)))
    tree.set("name", "device-e2e-core")
    for item in selected:
        element = copy.deepcopy(original)
        element.set("name", item["id"])
        tree.append(element)
    case.xml = ET.tostring(tree, encoding="unicode")
    case.write()
    command = [sys.executable, str(ios / "acceptance/verify_checkpoint.py"),
               "--shared-contract-root", str(args.shared_contract_root), "--result-dir", str(case.root),
               "--expected-source-sha", "a" * 40, "--expected-artifact-sha256", "b" * 64,
               "--checkpoint", "e2e-core"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "RESULT_BOUND_NOT_NODE_ACCEPTED"
    assert json.loads(result.stdout)["moduleCount"] == len(selected)
    for mutation in ({"modules": ["launch-smoke"]}, {"physical": False}, {"requireComplete": False},
                     {"adapter": "ios"}, {"platform": "android"}):
        original_run = copy.deepcopy(case.run)
        case.run.update(mutation)
        case.write()
        rejected = subprocess.run(command, capture_output=True, text=True, timeout=40)
        assert rejected.returncode == 1 and rejected.stderr.strip() == "IOS_CHECKPOINT_REJECTED"
        case.run = original_run
finally:
    case.doCleanups()
print("PASS iOS checkpoint consumer: whole-scope fixture, subset/virtual/adapter/platform rejection")
