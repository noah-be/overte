# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from result_binding import validate
from terminal_evidence import digest, EvidenceError

ROOT = Path(__file__).resolve().parents[1]
class ResultBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        module = json.loads((ROOT / 'catalog.json').read_text())['modules'][0]
        self.module = module['id']
        self.run = dict(schemaVersion=1, adapter='appium.android', suite='smoke', platform='android', physical=False,
                        requireComplete=True, capabilities=module['requires'], modules=[self.module], startedEpochMs=1000,
                        finishedEpochMs=2000, durationSeconds=1, status='passed')
        self.summary = dict(schemaVersion=1, adapter='appium.android', suite='smoke', status='passed',
                            results=[dict(id=self.module, description=module['description'], status='passed', returncode=0, durationSeconds=1)])
        self.xml = ('<testsuite name="device-smoke" tests="1" failures="0" errors="0" skipped="0" time="1">'
                    '<testcase classname="overte.device" name="launch-smoke" time="1"><system-out>OVT_REDACTED</system-out></testcase></testsuite>')
        self.write()
    def write(self):
        run = json.dumps(self.run).encode(); summary = json.dumps(self.summary).encode(); xml = self.xml.encode()
        (self.root/'run-manifest.json').write_bytes(run); (self.root/'summary.json').write_bytes(summary); (self.root/'junit.xml').write_bytes(xml)
        identity = dict(contract='overte-sh004-result-v1', sourceRevision='a'*40, artifactSha256='b'*64,
                        runSha256=digest(run), summarySha256=digest(summary), junitSha256=digest(xml))
        (self.root/'result-identity.json').write_text(json.dumps(identity))
    def check(self):
        return validate(self.root, 'a'*40, 'b'*64, 'appium.android', 'android', [self.module], False)
    def test_positive_and_real_cli(self):
        self.assertEqual(self.check()['moduleCount'],1)
        result = subprocess.run([sys.executable, str(ROOT/'verify-result.py'), '--result-dir',str(self.root),
            '--expected-source-sha','a'*40,'--expected-artifact-sha256','b'*64,'--expected-adapter','appium.android',
            '--expected-platform','android','--required-module',self.module,'--device-class','virtual'],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_negative_run_matrix(self):
        for key,value in [('physical',True),('requireComplete',False),('modules',[]),('capabilities',[]),
                          ('adapter','canary-device'),('status','failed'),('durationSeconds',True),('finishedEpochMs',1)]:
            with self.subTest(key=key):
                old=copy.deepcopy(self.run); self.run[key]=value; self.write()
                with self.assertRaises(EvidenceError): self.check()
                self.run=old
    def test_result_skip_error_and_private_description(self):
        for key,value in [('status','skipped'),('returncode',True),('description','canary-secret'),('id','unknown')]:
            with self.subTest(key=key):
                old=copy.deepcopy(self.summary); self.summary['results'][0][key]=value; self.write()
                with self.assertRaises(EvidenceError): self.check()
                self.summary=old
    def test_junit_private_and_nonpass(self):
        original=self.xml
        for replacement in ['canary-secret', '<![CDATA[canary-secret]]>']:
            self.xml=original.replace('OVT_REDACTED',replacement); self.write()
            with self.assertRaises(EvidenceError): self.check()
        for replacement in ['<skipped/>','<failure/>','<error/>']:
            self.xml=original.replace('</testcase>',replacement+'</testcase>'); self.write()
            with self.assertRaises(EvidenceError): self.check()
    def test_tamper_missing_stale(self):
        (self.root/'summary.json').write_text('{}')
        with self.assertRaises(EvidenceError): self.check()
        self.write()
        with self.assertRaises(EvidenceError): validate(self.root,'c'*40,'b'*64,'appium.android','android',[self.module],False)
        (self.root/'junit.xml').unlink()
        with self.assertRaises(EvidenceError): self.check()

if __name__ == '__main__': unittest.main()
