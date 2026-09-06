# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'provenance'))
from artifact_identity import EVIDENCE_KEYS, INPUT_KEYS, IdentityError, digest_file, normalized_inputs, read_record, validate

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.artifact=self.root/'fixture.bin'; self.artifact.write_bytes(b'test-only byte-binding fixture, not an APK')
        self.files={key:self.root/(key+'.json') for key in EVIDENCE_KEYS}
        for key,path in self.files.items(): path.write_text(json.dumps({'testOnly':key}))
        self.inputs={key:'c'*64 for key in INPUT_KEYS}
        self.record=dict(contract='overte-sh009-identity-v1', sourceRevision='a'*40,product='android-phone',versionCode=2,
                         channel='source-proof',artifactSha256=digest_file(self.artifact),inputs=self.inputs,
                         normalizedInputsSha256=normalized_inputs(self.inputs),evidence={key:digest_file(path) for key,path in self.files.items()},
                         signature=dict(state='not-applicable-source-proof',receiptSha256=None),upgrade=dict(state='pending',receiptSha256=None))
    def check(self): return validate(self.record,self.artifact,self.files,'a'*40,self.inputs,1)
    def test_positive_cli_and_normalization(self):
        self.assertEqual(self.check()['status'],'ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING')
        self.assertEqual(normalized_inputs(dict(reversed(list(self.inputs.items())))),normalized_inputs(self.inputs))
        record=self.root/'identity.json'; record.write_text(json.dumps(self.record))
        inputs=self.root/'inputs.json'; inputs.write_text(json.dumps(self.inputs))
        command=[sys.executable,str(ROOT/'tools/sbom/verify-artifact-identity.py'),'--record',str(record),'--artifact',str(self.artifact),
                 '--expected-source-sha','a'*40,'--expected-inputs',str(inputs),'--minimum-version','1']
        for key,path in self.files.items(): command.extend(['--'+key,str(path)])
        result=subprocess.run(command,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_wrong_source_version_and_claim(self):
        for key,value in [('sourceRevision','b'*40),('versionCode',1),('versionCode',True),('channel','public-release'),
                          ('signature',dict(state='verified',receiptSha256='f'*64))]:
            with self.subTest(key=key):
                old=copy.deepcopy(self.record); self.record[key]=value
                with self.assertRaises(IdentityError): self.check()
                self.record=old
    def test_foreign_bytes_and_missing_evidence(self):
        self.artifact.write_bytes(b'foreign')
        with self.assertRaises(IdentityError): self.check()
        self.record['artifactSha256']=digest_file(self.artifact)
        self.files['targetPackages'].unlink()
        with self.assertRaises(IdentityError): self.check()
    def test_wrong_normalized_inputs(self):
        self.record['inputs']=dict(self.inputs,toolchain='d'*64)
        self.record['normalizedInputsSha256']=normalized_inputs(self.record['inputs'])
        with self.assertRaises(IdentityError): self.check()
    def test_duplicate_nonfinite_and_symlink(self):
        path=self.root/'bad.json'
        for content in ('{"a":1,"a":2}','{"a":NaN}'):
            path.write_text(content)
            with self.assertRaises(IdentityError): read_record(path)
        link=self.root/'alias'; link.symlink_to(self.artifact)
        with self.assertRaises(IdentityError): digest_file(link)
if __name__ == '__main__': unittest.main()
