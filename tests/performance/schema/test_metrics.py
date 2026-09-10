# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import metrics

class MetricsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'trace.json'
        self.fixture = metrics.fixture_digest()
        self.samples = [dict(elapsedMs=t, frameP95Ms=15, memory={'kind':'ios-physical-footprint','bytes':100000000},
                             thermal='nominal', batteryPercent=80, processEnergyJoules=None,
                             queueDepth=1, blackFrames=0, degradation='normal', checkpoint=t==1800000)
                        for t in range(0, 1800001, 30000)]
        self.trace = dict(contract='overte-sh008-trace-v1', sourceRevision='a'*40, artifactSha256='b'*64,
                          platform='ios-ipad', fixtureSha256=self.fixture, samples=self.samples)
        self.write()
    def write(self): self.path.write_text(json.dumps(self.trace))
    def check(self, budget=None, sha=None):
        return metrics.validate(self.path, 'a'*40, 'b'*64, 'ios-ipad', self.fixture, budget, sha)
    def test_real_cli_positive_without_budget_is_pending(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'analyze.py'),
            '--trace', str(self.path), '--expected-source-sha', 'a'*40,
            '--expected-artifact-sha256', 'b'*64, '--platform', 'ios-ipad',
            '--expected-fixture-sha256', self.fixture], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'METRICS_BOUND_BUDGETS_PENDING')
    def test_missing_stale_foreign_or_short_run(self):
        original = copy.deepcopy(self.trace)
        for key, value in [('sourceRevision','c'*40), ('artifactSha256','c'*64), ('platform','ios-iphone'),
                           ('fixtureSha256','c'*64), ('samples',self.samples[:-1])]:
            with self.subTest(key=key):
                self.trace = copy.deepcopy(original); self.trace[key] = value; self.write()
                with self.assertRaises(metrics.MetricsError): self.check()
    def test_sample_stop_range_missing_and_unit_matrix(self):
        original = copy.deepcopy(self.trace)
        for key, value in [('thermal','critical'), ('thermal','unavailable'), ('thermal','serious'),
                           ('frameP95Ms', True), ('frameP95Ms', float('inf')), ('frameP95Ms',10**500),
                           ('blackFrames',1), ('blackFrames',None), ('processEnergyJoules',0),
                           ('memory',{'kind':'resident-set','bytes':1000}), ('batteryPercent',101),
                           ('queueDepth',-1), ('elapsedMs',-1), ('checkpoint','yes')]:
            with self.subTest(key=key):
                self.trace=copy.deepcopy(original); self.trace['samples'][2][key]=value; self.write()
                with self.assertRaises(metrics.MetricsError): self.check()
    def test_gaps_checkpoint_and_normal_scheduler_jitter(self):
        self.samples[2]['elapsedMs'] += 6000; self.write()
        with self.assertRaises(metrics.MetricsError): self.check()
        self.samples[2]['elapsedMs'] -= 6000
        self.samples[-1]['elapsedMs'] += 3000
        self.write(); self.assertEqual(self.check()['durationMs'],1803000)
        self.samples[-1]['checkpoint']=False; self.write()
        with self.assertRaises(metrics.MetricsError): self.check()
    def test_bound_budget_thresholds_and_missing_optional_data(self):
        budget = dict(contract='overte-sh008-budget-v1', platform='ios-ipad', fixtureSha256=self.fixture,
                      memoryKind='ios-physical-footprint', maxFrameP95Ms=15, maxMemoryGrowthBytes=0,
                      maxQueueDepth=1, minBatteryEndPercent=80)
        path = self.root/'synthetic-test-budget.json'
        def save():
            path.write_text(json.dumps(budget)); return metrics.digest(path.read_bytes())
        sha=save()
        self.assertEqual(self.check(path,sha)['status'],'BUDGETS_CHECKED_NOT_NODE_ACCEPTED')
        with self.assertRaises(metrics.MetricsError): self.check(path,'c'*64)
        budget['maxFrameP95Ms']=14.99
        with self.assertRaises(metrics.MetricsError): self.check(path,save())
        budget['maxFrameP95Ms']=15
        self.samples[1]['queueDepth']=None; self.write()
        self.assertEqual(self.check()['status'],'METRICS_BOUND_BUDGETS_PENDING')
        with self.assertRaises(metrics.MetricsError): self.check(path,save())
    def test_duplicate_key_and_all_platform_durations(self):
        self.path.write_text('{"samples":1,"samples":2}')
        with self.assertRaises(metrics.MetricsError): self.check()
        for platform,duration in metrics.DURATION_MS.items():
            samples=[]
            for elapsed in range(0,duration+1,30000):
                sample=copy.deepcopy(self.samples[0]); sample['elapsedMs']=elapsed
                sample['checkpoint']=elapsed==1800000
                if not platform.startswith('ios-'): sample['memory']['kind']='android-total-pss'
                samples.append(sample)
            self.trace['platform']=platform; self.trace['samples']=samples; self.write()
            result=metrics.validate(self.path,'a'*40,'b'*64,platform,self.fixture)
            self.assertEqual(result['durationMs'],duration)

if __name__ == '__main__': unittest.main()
