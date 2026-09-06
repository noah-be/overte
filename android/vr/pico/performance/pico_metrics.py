"""Pico offline SH-008 consumer. No device access, synthetic trace or budget creation."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
SHARED = ROOT / 'tests/performance/schema/metrics.py'


class ClosedParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid arguments')


def shared_validator():
    spec = importlib.util.spec_from_file_location('_overte_pico_shared_metrics_v1', SHARED)
    if not spec or not spec.loader:
        raise ImportError('missing shared metrics')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    try:
        parser = ClosedParser(description=__doc__)
        parser.add_argument('--trace', type=Path, required=True)
        parser.add_argument('--expected-source-sha', required=True)
        parser.add_argument('--expected-artifact-sha256', required=True)
        parser.add_argument('--expected-fixture-sha256', required=True)
        parser.add_argument('--budget', type=Path)
        parser.add_argument('--expected-budget-sha256')
        args = parser.parse_args(argv)
        shared = shared_validator()
        try:
            result = shared.validate(args.trace, args.expected_source_sha,
                args.expected_artifact_sha256, 'pico4', args.expected_fixture_sha256,
                args.budget, args.expected_budget_sha256)
        except shared.MetricsError as error:
            # Preserve actionable closed STOP outcomes; never echo arbitrary
            # paths, JSON values, exceptions or command arguments.
            if str(error) in ('STOP_THERMAL_CRITICAL', 'STOP_BLACK_FRAME', 'STOP_RUN_INCOMPLETE'):
                print('PICO_METRICS_' + str(error), file=sys.stderr)
                return 1
            raise
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        print('PICO_METRICS_REJECTED', file=sys.stderr)
        return 1
    # Original Shared status remains budget-pending or checked-not-node-accepted.
    print(json.dumps(result, sort_keys=True))
    return 0
