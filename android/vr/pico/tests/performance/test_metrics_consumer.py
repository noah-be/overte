#!/usr/bin/env python3
"""Synthetic-only conformance of actual Pico CLI and existing power-report caller."""
# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
PICO = ROOT / 'android/vr/pico'
# Independently pinned exact reference-fixture.json bytes from SH-008 release.
FIXTURE_SHA = '88d94ad1936dd68deeedd9e91f0bb0170621ff69e6ce70c39580c901e679062b'


class MetricsConsumerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pico-sh008-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'trace.json'
        self.trace = dict(contract='overte-sh008-trace-v1', sourceRevision='a' * 40,
            artifactSha256='b' * 64, platform='pico4', fixtureSha256=FIXTURE_SHA,
            samples=[dict(elapsedMs=i * 30000, frameP95Ms=10 + i % 5,
                memory=dict(kind='android-total-pss', bytes=100000000 + i * 1024),
                thermal='nominal', batteryPercent=80 - i * 0.25, processEnergyJoules=None,
                queueDepth=2, blackFrames=0, degradation='normal', checkpoint=i == 60)
                for i in range(121)])

    def run_cli(self, extra=(), existing=False):
        self.path.write_text(self.trace if isinstance(self.trace, str) else json.dumps(self.trace))
        command = [sys.executable, str(PICO / ('tools/analyze-pico4-power.py' if existing else 'performance/analyze.py'))]
        if existing: command.append('--parity')
        return subprocess.run(command + ['--trace', str(self.path), '--expected-source-sha', 'a' * 40,
            '--expected-artifact-sha256', 'b' * 64, '--expected-fixture-sha256', FIXTURE_SHA,
            *extra], capture_output=True, text=True, timeout=5)

    def assert_rejected(self, result, code='PICO_METRICS_REJECTED'):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), code)
        self.assertEqual(result.stdout, '')

    def test_real_cli_and_existing_report_entry(self):
        for existing in (False, True):
            result = self.run_cli(existing=existing)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output['status'], 'METRICS_BOUND_BUDGETS_PENDING')
            self.assertEqual(output['durationMs'], 3600000)
            self.assertEqual(output['memoryKind'], 'android-total-pss')
            self.assertEqual(output['traceSha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
            self.assertNotIn(str(self.path), result.stdout)

    def test_foreign_identity_missing_time_and_measurements(self):
        original = copy.deepcopy(self.trace)
        for key, value in [('platform', 'android-phone'), ('sourceRevision', 'c' * 40),
                           ('artifactSha256', 'c' * 64), ('fixtureSha256', 'c' * 64),
                           ('private-context', 'CANARY_USER_URL'), ('samples', self.trace['samples'][:-1])]:
            with self.subTest(key=key):
                self.trace = copy.deepcopy(original); self.trace[key] = value
                self.assert_rejected(self.run_cli())
        for key, value in [('frameP95Ms', None), ('frameP95Ms', True), ('frameP95Ms', float('nan')),
                           ('memory', dict(kind='ios-physical-footprint', bytes=1000)),
                           ('blackFrames', None), ('processEnergyJoules', 1), ('thermal', 'unavailable'),
                           ('elapsedMs', 100000), ('queueDepth', -1), ('thermal', 'serious')]:
            with self.subTest(key=key):
                self.trace = copy.deepcopy(original); self.trace['samples'][1][key] = value
                self.assert_rejected(self.run_cli())
        self.trace = copy.deepcopy(original)
        self.trace['samples'][60]['checkpoint'] = False
        self.assert_rejected(self.run_cli())

    def test_closed_stop_outcomes(self):
        for key, value, code in [('thermal', 'critical', 'STOP_THERMAL_CRITICAL'),
                                 ('blackFrames', 1, 'STOP_BLACK_FRAME'),
                                 ('degradation', 'stopped', 'STOP_RUN_INCOMPLETE')]:
            original = self.trace['samples'][2][key]
            self.trace['samples'][2][key] = value
            self.assert_rejected(self.run_cli(), 'PICO_METRICS_' + code)
            self.trace['samples'][2][key] = original

    def test_v001_fixture_trace_is_not_silently_relabelled(self):
        self.trace['fixtureSha256'] = '5b529ac6221218630120596eafcb44ba3966d2beab09ee19a8abbeab7fd72154'
        self.assert_rejected(self.run_cli())

    def test_frozen_synthetic_budget_and_inclusive_bounds(self):
        # Numeric values are TEST FIXTURES, never production acceptance budgets.
        budget = dict(contract='overte-sh008-budget-v1', platform='pico4', fixtureSha256=FIXTURE_SHA,
            memoryKind='android-total-pss', maxFrameP95Ms=14, maxMemoryGrowthBytes=120 * 1024,
            maxQueueDepth=2, minBatteryEndPercent=50)
        path = self.path.with_name('synthetic-budget.json')
        raw = json.dumps(budget).encode()
        path.write_bytes(raw)
        frozen = hashlib.sha256(raw).hexdigest()
        args = ['--budget', str(path), '--expected-budget-sha256', frozen]
        result = self.run_cli(args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'BUDGETS_CHECKED_NOT_NODE_ACCEPTED')
        budget['maxFrameP95Ms'] = 13
        path.write_text(json.dumps(budget))
        self.assert_rejected(self.run_cli(args)) # changed bytes do not approve themselves
        path.write_bytes(raw)
        self.trace['samples'][30]['queueDepth'] = None
        self.assert_rejected(self.run_cli(args))
        self.assertEqual(self.run_cli().returncode, 0) # optional only while budget-pending
        self.assert_rejected(self.run_cli(['--budget', str(path)]))
        self.assert_rejected(self.run_cli(['--expected-budget-sha256', frozen]))

    def test_raw_csv_and_private_arguments_are_not_retained_output(self):
        result = self.run_cli(['--device-selector', 'CANARY_PRIVATE'], existing=True)
        self.assert_rejected(result)
        self.trace = 'epoch_s,label,level_pct\n0,CANARY_PRIVATE,80\n'
        self.assert_rejected(self.run_cli(existing=True))
        self.trace = {'sourceRevision': 'CANARY_PRIVATE'}
        self.assert_rejected(self.run_cli())


if __name__ == '__main__':
    unittest.main(verbosity=2)
