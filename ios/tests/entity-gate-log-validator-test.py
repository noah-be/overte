#!/usr/bin/env python3
"""Acceptance and rejection fixtures for the offline iOS gate validator."""

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "ios/tools/validate-entity-gate-log.py"
FIXTURES = ROOT / "ios/tests/fixtures/entity-gates"


def run(name, expected_acceptance, expected_error=None):
    with tempfile.TemporaryDirectory(prefix="overte-ios-gate-report-") as temporary:
        report_path = pathlib.Path(temporary) / "report.json"
        result = subprocess.run(
            [sys.executable, str(TOOL), str(FIXTURES / name), "--output", str(report_path)],
            check=False,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["accepted"] != expected_acceptance:
        raise SystemExit(f"{name}: unexpected acceptance: {report}")
    if (result.returncode == 0) != expected_acceptance:
        raise SystemExit(f"{name}: exit status disagrees with report")
    if expected_error and not any(expected_error in error for error in report["errors"]):
        raise SystemExit(f"{name}: missing diagnostic {expected_error!r}: {report}")
    return report


success = run("success.log", True)
if success["completed_gates"] != success["expected_gates"] or len(success["evidence"]) != 6:
    raise SystemExit("success fixture did not produce complete ordered evidence")
run("missing-marker.log", False, "missing gate 'render_handoff'")
run("wrong-order.log", False, "expected 'entity_server_active' before 'entity_query_sent'")
bootstrap = run("bootstrap-only.log", False, "missing gate 'domain_list_connected'")
if bootstrap["completed_gates"]:
    raise SystemExit("bootstrap text must not count as native gate evidence")

print("iOS entity gate log validator valid: success plus 3 fail-closed fixtures")
