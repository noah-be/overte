# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
import hashlib,json,tempfile,unittest
from pathlib import Path
from application_key_attestation import attest_input
class Attestation(unittest.TestCase):
    def fixture(self, directory):
        root=Path(directory);source=root/'source/native-input.cpp';source.parent.mkdir();source.write_bytes(b'cpp reviewed bytes')
        header=source.with_name('application-key-route.h');header.write_bytes(b'header reviewed bytes')
        build=root/'build';plugin=build/'qml/BrowserNativeInput/libbrowsernativeinput.so';plugin.parent.mkdir(parents=True);plugin.write_bytes(b'owned module')
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        data={'sourceSha256':sha(source),'applicationKeyRouteSha256':sha(header),'pluginSha256':sha(plugin),'qtSDKVersion':'5.15.3','qtRuntimeVersion':'5.15.3','packages':[]}
        (build/'artifacts.json').write_text(json.dumps(data));return source,header,build,plugin,data
    def test_exact_tuple_and_no_paths_or_source_values_exported(self):
        with tempfile.TemporaryDirectory() as d:
            s,h,b,p,_=self.fixture(d);result=attest_input(b,s);self.assertEqual(set(result),{'sourceSHA256','applicationKeyRouteSHA256','pluginLibrarySHA256','pluginArtifactsSHA256'});self.assertTrue(all(len(v)==64 for v in result.values()));self.assertNotIn(d,json.dumps(result))
    def test_independently_mutated_cpp_header_module_are_refused(self):
        for index in range(3):
            with self.subTest(index=index),tempfile.TemporaryDirectory() as d:
                s,h,b,p,_=self.fixture(d);[s,h,p][index].write_bytes(b'mutated')
                with self.assertRaisesRegex(ValueError,'native-key-attestation'):attest_input(b,s)
    def test_missing_header_binding_cpp_only_metadata_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            s,h,b,p,data=self.fixture(d);del data['applicationKeyRouteSha256'];(b/'artifacts.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'source-refused'):attest_input(b,s)
    def test_each_input_symlink_is_refused(self):
        for index in range(4):
            with self.subTest(index=index),tempfile.TemporaryDirectory() as d:
                s,h,b,p,_=self.fixture(d);target=[s,h,p,b/'artifacts.json'][index];saved=target.with_name(target.name+'.saved');target.rename(saved);target.symlink_to(saved)
                with self.assertRaises(OSError):attest_input(b,s)
    def test_bounded_oversize_header_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            s,h,b,p,_=self.fixture(d);h.write_bytes(b'x'*32769)
            with self.assertRaisesRegex(ValueError,'input-refused'):attest_input(b,s)
    def test_wrong_module_metadata_does_not_accept_current_source(self):
        with tempfile.TemporaryDirectory() as d:
            s,h,b,p,data=self.fixture(d);data['pluginSha256']='0'*64;(b/'artifacts.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'module-refused'):attest_input(b,s)
    def test_qt_runtime_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            s,h,b,p,data=self.fixture(d);data['qtRuntimeVersion']='6.0.0';(b/'artifacts.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'source-refused'):attest_input(b,s)
    def test_after_cohort_mutation_cannot_keep_initial_binding(self):
        with tempfile.TemporaryDirectory() as d:
            s,h,b,p,data=self.fixture(d);initial=attest_input(b,s)
            h.write_bytes(b'new reviewed header');data['applicationKeyRouteSha256']=hashlib.sha256(h.read_bytes()).hexdigest();(b/'artifacts.json').write_text(json.dumps(data))
            self.assertNotEqual(attest_input(b,s),initial)
    def test_non_object_and_invalid_json_metadata_is_refused(self):
        for raw in ['[]','not json']:
            with tempfile.TemporaryDirectory() as d:
                s,h,b,p,_=self.fixture(d);(b/'artifacts.json').write_text(raw)
                with self.assertRaises(ValueError):attest_input(b,s)
if __name__=='__main__':unittest.main()
