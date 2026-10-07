# SPDX-License-Identifier: Apache-2.0
"""Actual private file admission and schema controls; no browser/services/signals."""
import hashlib,importlib,json,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
c=importlib.import_module('chrome-payload')
import gates as g

class Completion(unittest.TestCase):
 def rows(self):return [{'stage':name,'passed':True} for name in g.GOOGLE_CHROME_REQUIRED_STAGES]
 def test_current_complete_seventeen_stages_and_distinct_historical_schema(self):
  self.assertEqual(len(g.GOOGLE_CHROME_REQUIRED_STAGES),17);self.assertTrue(g.complete_chrome_pass(self.rows()));self.assertFalse(g.complete_pass(self.rows()));self.assertEqual(len(g.REQUIRED_STAGES),19)
  old=[{'stage':name,'passed':True} for name in g.REQUIRED_STAGES];self.assertTrue(g.complete_pass(old));self.assertFalse(g.complete_chrome_pass(old))
 def test_missing_failed_duplicate_and_cleanup_are_refused(self):
  for name in g.GOOGLE_CHROME_REQUIRED_STAGES:
   rows=self.rows();self.assertFalse(g.complete_chrome_pass([row for row in rows if row['stage']!=name]));next(row for row in rows if row['stage']==name)['passed']=False;self.assertFalse(g.complete_chrome_pass(rows))
  rows=self.rows();self.assertFalse(g.complete_chrome_pass(rows+[rows[0]]))
 def test_actual_source_selects_only_chrome_and_explicit_curator(self):
  source=Path(g.__file__).read_text();self.assertEqual(source.count("for engine in ('chrome',):"),2);self.assertIn("'--browser','chrome'",source);self.assertIn("env['OVERTE_BROWSER_CHROME_EXECUTABLE']=admitted_executable(runtime,config['browserPayloadManifestSHA256'])",source)
  source=Path(__file__).with_name('prepare.py').read_text();self.assertNotIn("'install','chromium'",source);self.assertNotIn("'install','chrome'",source);self.assertIn('qualification-requires-reviewed-nonroot-Fedora-agent',source)
  import run;self.assertIn('chrome-payload.py',run.SOURCE_FILES)

class Payload(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='chrome-payload-contract-');self.root=Path(self.tmp.name);self.runtime=self.root/'runtime';self.runtime.mkdir(mode=0o700);self.bundle=self.root/'reviewed';self.bundle.mkdir();self.payload=self.bundle/'payload';self.payload.mkdir()
  (self.payload/'chrome').write_bytes(b'\x7fELFauthored nonexecuted test');(self.payload/'chrome').chmod(0o500)
  (self.payload/'resources.pak').write_bytes(b'authored resources');(self.payload/'locales').mkdir();(self.payload/'locales/en-US.pak').write_bytes(b'authored locale')
  self.manifest=self.bundle/'bundle.json';self.save()
 def tearDown(self):self.tmp.cleanup()
 def save(self):
  rows=[]
  for file in sorted(self.payload.rglob('*')):
   if file.is_file():rows.append({'path':str(file.relative_to(self.payload)),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'executable':file.name=='chrome'})
  self.document={'version':1,'executable':'chrome','files':rows};self.manifest.write_text(json.dumps(self.document));self.expected=hashlib.sha256(self.manifest.read_bytes()).hexdigest()
 def stage(self):return c.stage(self.runtime,self.manifest,self.expected)
 def test_exact_copy_is_private_revalidated_and_within_checkout_runtime(self):
  exe=self.stage();self.assertEqual(exe,str(self.runtime/'google-chrome/chrome'));self.assertEqual(c.admitted_executable(self.runtime),exe);self.assertEqual(Path(exe).read_bytes(),(self.payload/'chrome').read_bytes());self.assertEqual(stat.S_IMODE(Path(exe).stat().st_mode),0o500)
  self.assertEqual(stat.S_IMODE((self.runtime/'google-chrome/resources.pak').stat().st_mode),0o400)
 def test_manifest_mismatch_does_not_start_or_publish(self):
  self.expected='0'*64
  with self.assertRaises(RuntimeError):self.stage()
  self.assertFalse((self.runtime/'google-chrome').exists());self.assertFalse((self.runtime/'google-chrome-pending').exists())
 def test_changed_source_bytes_refuse_and_clean_only_pending(self):
  (self.payload/'resources.pak').write_bytes(b'changed');marker=self.runtime/'unchanged';marker.write_text('preserve')
  with self.assertRaises(RuntimeError):self.stage()
  self.assertFalse((self.runtime/'google-chrome').exists());self.assertFalse((self.runtime/'google-chrome-pending').exists());self.assertEqual(marker.read_text(),'preserve')
 def test_link_final_component_and_directory_refuse(self):
  original=self.payload/'locales/en-US.pak';copy=self.root/'copy';copy.write_bytes(original.read_bytes());original.unlink();original.symlink_to(copy)
  with self.assertRaises((RuntimeError,OSError)):self.stage()
 def test_added_unlisted_file_refuses(self):
  (self.payload/'foreign.so').write_bytes(b'foreign')
  with self.assertRaises(RuntimeError):self.stage()
 def test_cached_payload_tampering_refuses_fresh_gate(self):
  self.stage();file=self.runtime/'google-chrome/resources.pak';file.chmod(0o600);file.write_bytes(b'changed')
  with self.assertRaises(RuntimeError):c.admitted_executable(self.runtime)
 def test_parent_bound_manifest_identity_refuses_rebinding(self):
  self.stage()
  with self.assertRaises(RuntimeError):c.admitted_executable(self.runtime,'0'*64)
  self.assertEqual(c.admission_identity(self.runtime),self.expected)
 def test_existing_output_is_never_replaced(self):
  exe=self.stage();original=Path(exe).read_bytes()
  with self.assertRaises(RuntimeError):self.stage()
  self.assertEqual(Path(exe).read_bytes(),original)
 def test_nonelf_executable_refuses_even_with_matching_reviewed_hash(self):
  (self.payload/'chrome').chmod(0o700);(self.payload/'chrome').write_bytes(b'not ELF');self.save()
  with self.assertRaises(RuntimeError):self.stage()
 def test_payload_count_byte_depth_reserved_path_and_bool_refuse(self):
  variants=[{'path':'../escape'},{'path':'/escape'},{'path':'admission.json'},{'path':'chrome','bytes':True},{'path':'chrome','bytes':c.MAX_BYTES+1},{'path':'chrome','executable':1},{'path':'a/'*17+'chrome'}]
  for fields in variants:
   with self.subTest(fields=fields):
    doc=json.loads(json.dumps(self.document));doc['files'][0].update(fields);self.manifest.write_text(json.dumps(doc));expected=hashlib.sha256(self.manifest.read_bytes()).hexdigest()
    with self.assertRaises(RuntimeError):c.manifest_bytes(self.manifest,expected)
 def test_runtime_symlink_and_nonprivate_directory_refuse(self):
  self.runtime.chmod(0o755)
  with self.assertRaises(RuntimeError):self.stage()
 def test_strict_manifest_rejects_duplicate_keys_and_boolean_version(self):
  for data in [b'{"version":1,"version":1,"executable":"chrome","files":[]}',json.dumps({**self.document,'version':True}).encode()]:
   self.manifest.write_bytes(data)
   with self.assertRaises(RuntimeError):c.manifest_bytes(self.manifest,hashlib.sha256(data).hexdigest())
 def test_final_target_creation_race_never_replaces_another_directory(self):
  original=c.check_rows
  def raced(*args,**kwargs):
   original(*args,**kwargs);target=self.runtime/'google-chrome';target.mkdir();(target/'preserve').write_text('unchanged')
  with patch.object(c,'check_rows',side_effect=raced),self.assertRaises(FileExistsError):self.stage()
  self.assertEqual((self.runtime/'google-chrome/preserve').read_text(),'unchanged');self.assertFalse((self.runtime/'google-chrome-pending').exists())
 def test_stage_has_no_download_launch_or_browser_environment_capability(self):
  source=Path(c.__file__).read_text();self.assertNotIn('subprocess',source);self.assertNotIn('execvp',source);self.assertNotIn('urllib',source)

if __name__=='__main__':unittest.main()
