#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixed staging diagnostics; no browser, domain, system or network workload."""
import contextlib,io,json,lzma,os,subprocess,tarfile,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
import stage

SECRET='private-token/path?credential=secret-target'
class NoString(Exception):
 def __str__(self):raise AssertionError('Exception text must never be inspected')
class Projection(unittest.TestCase):
 def test_fixed_failure_classes_do_not_reflect_messages_arguments_or_streams(self):
  cases=[(urllib.error.HTTPError('https://'+SECRET,503,SECRET,{},io.BytesIO()),'download-release','download-http-error'),(urllib.error.URLError(SECRET),'download-index','download-transport-error'),(subprocess.TimeoutExpired([SECRET],15,output=SECRET,stderr=SECRET),'archive-decode','operation-timeout'),(FileNotFoundError(SECRET),'signature-run','required-tool-unavailable'),(FileNotFoundError(SECRET),'keyring-read','trusted-keyring-unavailable'),(FileNotFoundError(SECRET),'archive-member-write','required-input-unavailable'),(PermissionError(SECRET),'helper-copy','filesystem-access-refused'),(subprocess.CalledProcessError(1,[SECRET],output=SECRET,stderr=SECRET),'archive-list','external-tool-failed'),(json.JSONDecodeError(SECRET,SECRET,0),'dependency-record','record-parse-refused'),(lzma.LZMAError(SECRET),'index-decode','index-decode-refused'),(tarfile.ReadError(SECRET),'archive-decode','archive-parse-refused'),(KeyError(SECRET),'workflow-env-open','required-environment-unavailable'),(ValueError(SECRET),'signature-validation','validation-refused'),(OSError(SECRET),'helper-copy','operating-system-refused'),(NoString(),'preparation','unexpected-error')]
  for error,phase,category in cases:
   if isinstance(error,urllib.error.HTTPError):self.addCleanup(error.close)
   with self.subTest(category=category,phase=phase):
    result=stage.staging_failure(error,phase);encoded=json.dumps(result);self.assertNotIn(SECRET,encoded);self.assertLess(len(encoded),512);self.assertEqual(result['failureCategory'],category);self.assertEqual(result['phase'],phase);self.assertFalse(result['completed']);self.assertEqual(set(result),{'schemaVersion','scope','completed','phase','failureCategory'}|({'httpStatus'}if isinstance(error,urllib.error.HTTPError)else set()))
 def test_only_bounded_actual_integer_http_status_is_projected(self):
  for value in [99,600,-1,True,503.0,SECRET,None]:
   error=urllib.error.HTTPError(SECRET,value,SECRET,{},io.BytesIO());self.addCleanup(error.close);result=stage.staging_failure(error,'download-package');self.assertNotIn('httpStatus',result)
  for value in [100,404,599]:
   error=urllib.error.HTTPError(SECRET,value,SECRET,{},io.BytesIO());self.addCleanup(error.close);self.assertEqual(stage.staging_failure(error,'download-index')['httpStatus'],value)
 def test_unknown_phase_and_non_string_aliases_cannot_be_published(self):
  for phase in [SECRET,None,True,[],{}]:
   with self.assertRaises(ValueError):stage.staging_failure(ValueError(SECRET),phase)
  with self.assertRaises(ValueError):stage.staging_phase(None,SECRET)
 def test_every_internal_phase_has_bounded_fixed_failure_output(self):
  for phase in stage.STAGING_PHASES:
   result=stage.staging_failure(NoString(),phase);self.assertLess(len(json.dumps(result)),512)

class CommandBoundary(unittest.TestCase):
 def invoke(self,action):
  out,err=io.StringIO(),io.StringIO()
  with patch.object(stage,'main',action),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=stage.run()
  result=json.loads(out.getvalue());self.assertEqual(len(out.getvalue().splitlines()),1);self.assertNotIn(SECRET,out.getvalue()+err.getvalue());return code,result,err.getvalue()
 def test_failure_is_single_fixed_json_and_original_nonzero_refusal(self):
  def main(*,progress):progress('download-index');raise urllib.error.HTTPError(SECRET,429,SECRET,{},io.BytesIO())
  code,result,err=self.invoke(main);self.assertEqual(code,1);self.assertEqual(result['phase'],'download-index');self.assertEqual(result['httpStatus'],429);self.assertEqual(err,'owned-atomic-dependency-staging-refused\n')
 def test_actual_unclosed_http_error_is_closed_before_exception_finalizer_can_reflect_reason(self):
  import gc,warnings
  resource=urllib.error.HTTPError(SECRET,503,SECRET,{},None)
  def main(*,progress):progress('download-release');raise resource
  with warnings.catch_warnings(record=True)as caught:
   warnings.simplefilter('always',ResourceWarning)
   code,result,err=self.invoke(main);self.assertEqual(code,1);self.assertEqual(result['httpStatus'],503);self.assertTrue(resource.closed);gc.collect();self.assertEqual(caught,[])
 def test_unknown_exception_does_not_stringify_or_print_traceback(self):
  def main(*,progress):raise NoString()
  code,result,err=self.invoke(main);self.assertEqual(code,1);self.assertEqual(result['failureCategory'],'unexpected-error');self.assertEqual(result['phase'],'preparation')
 def test_success_is_printed_only_after_main_completes_and_contains_no_private_paths(self):
  calls=[]
  def main(*,progress):progress('workflow-env-write');calls.append('completed')
  code,result,err=self.invoke(main);self.assertEqual(calls,['completed']);self.assertEqual(code,0);self.assertTrue(result['completed']);self.assertEqual(result['phase'],'complete');self.assertEqual(err,'');self.assertEqual(set(result),{'schemaVersion','scope','completed','phase'})
 def test_real_cli_invalid_source_retains_exit_one_and_only_safe_output(self):
  import sys
  child=subprocess.run([sys.executable,'-B',str(Path(stage.__file__))],env={**os.environ,'PROBE_SOURCE_SHA':SECRET},capture_output=True,text=True,timeout=5)
  self.assertEqual(child.returncode,1);self.assertEqual(child.stderr,'owned-atomic-dependency-staging-refused\n');self.assertNotIn(SECRET,child.stdout+child.stderr);summary=json.loads(child.stdout);self.assertEqual(summary['phase'],'source-check');self.assertEqual(summary['failureCategory'],'validation-refused');self.assertFalse(summary['completed'])
 def test_bad_progress_token_refuses_without_reflection(self):
  def main(*,progress):progress(SECRET)
  code,result,err=self.invoke(main);self.assertEqual(code,1);self.assertEqual(result['phase'],'preparation');self.assertEqual(result['failureCategory'],'validation-refused')

class ActualStage(unittest.TestCase):
 def setUp(self):
  self.cache=Path(os.environ['ATOMIC_DIAGNOSTIC_CACHE']);self.keyring=Path(os.environ['ATOMIC_DIAGNOSTIC_TEST_KEYRING']);self.record=json.loads((stage.HERE/'dependency.json').read_text());self.mapping={self.record['releaseURL']:self.cache/'InRelease','https://archive.ubuntu.com/ubuntu/dists/noble/'+self.record['packagesPath']:self.cache/'Packages.xz',self.record['packageURL']:self.cache/'strace.deb'}
 def fetch(self,url):return self.mapping[url].read_bytes()
 def test_real_cached_signature_chain_reports_order_and_keeps_original_return_contract(self):
  phases=[]
  with tempfile.TemporaryDirectory()as temp:
   result=stage.signed_dependency(Path(temp),self.keyring,self.fetch,progress=phases.append);self.assertEqual(result,{'signature':'verified-trusted-archive-key','dependency':'exact-reviewed-noble-amd64','binarySHA256':self.record['binarySHA256']});self.assertEqual(phases[:4],['dependency-record','download-release','download-index','download-package']);self.assertIn('signature-validation',phases);self.assertEqual(phases[-1],'executable-write');self.assertTrue(set(phases)<=stage.STAGING_PHASES)
 def test_actual_download_failures_preserve_exact_phase_and_never_advance(self):
  for position,name in enumerate(['download-release','download-index','download-package']):
   phases=[];calls=[]
   def fetch(url):
    calls.append(url)
    if len(calls)==position+1:
     error=urllib.error.HTTPError(SECRET,502,SECRET,{},io.BytesIO());self.addCleanup(error.close);raise error
    return self.fetch(url)
   with tempfile.TemporaryDirectory()as temp:
    with self.assertRaises(urllib.error.HTTPError)as caught:stage.signed_dependency(Path(temp),self.keyring,fetch,progress=phases.append)
    self.assertEqual(phases[-1],name);self.assertEqual(len(calls),position+1);self.assertEqual(stage.staging_failure(caught.exception,phases[-1])['httpStatus'],502);self.assertFalse((Path(temp)/'strace').exists())
 def test_real_changed_digest_still_refuses_before_keyring_or_any_subprocess(self):
  phases=[]
  with tempfile.TemporaryDirectory()as temp,patch.object(stage.subprocess,'run')as run,patch.object(stage.subprocess,'check_output')as output:
   with self.assertRaisesRegex(ValueError,'digest-refused'):stage.signed_dependency(Path(temp),self.keyring,lambda url:b'changed',progress=phases.append)
   self.assertEqual(phases[-1],'download-digests');run.assert_not_called();output.assert_not_called();self.assertEqual(list(Path(temp).iterdir()),[])
 def test_actual_missing_keyring_does_not_execute_signature_or_extraction(self):
  phases=[]
  with tempfile.TemporaryDirectory()as temp,patch.object(stage.subprocess,'run')as run:
   with self.assertRaises(FileNotFoundError)as caught:stage.signed_dependency(Path(temp),Path(temp)/'absent',self.fetch,progress=phases.append)
   self.assertEqual(phases[-1],'keyring-read');run.assert_not_called();self.assertEqual(stage.staging_failure(caught.exception,phases[-1])['failureCategory'],'trusted-keyring-unavailable');self.assertFalse((Path(temp)/'strace').exists())
 def test_actual_missing_signature_tool_is_distinct_from_missing_keyring(self):
  phases=[]
  with tempfile.TemporaryDirectory()as temp,patch.object(stage.subprocess,'run',side_effect=FileNotFoundError(SECRET)):
   with self.assertRaises(FileNotFoundError)as caught:stage.signed_dependency(Path(temp),self.keyring,self.fetch,progress=phases.append)
   self.assertEqual(phases[-1],'signature-run');self.assertEqual(stage.staging_failure(caught.exception,phases[-1])['failureCategory'],'required-tool-unavailable')
 def test_failed_signature_gate_preserves_private_capture_and_refuses_before_archive(self):
  phases=[];result=subprocess.CompletedProcess(['gpgv'],1,b'',SECRET.encode())
  with tempfile.TemporaryDirectory()as temp,patch.object(stage.subprocess,'run',return_value=result)as run,patch.object(stage.subprocess,'check_output')as output:
   with self.assertRaisesRegex(ValueError,'signature-refused'):stage.signed_dependency(Path(temp),self.keyring,self.fetch,progress=phases.append)
   self.assertEqual(phases[-1],'signature-validation');self.assertTrue(run.call_args.kwargs['capture_output']);output.assert_not_called();self.assertFalse((Path(temp)/'strace').exists())
 def test_extraction_tool_failure_stderr_is_captured_not_published(self):
  phases=[];real=stage.subprocess.check_output
  def output(command,**kwargs):
   if command[0]=='ar':
    self.assertIs(kwargs.get('stderr'),subprocess.PIPE);raise subprocess.CalledProcessError(1,command,stderr=SECRET.encode())
   return real(command,**kwargs)
  with tempfile.TemporaryDirectory()as temp,patch.object(stage.subprocess,'check_output',side_effect=output):
   with self.assertRaises(subprocess.CalledProcessError)as caught:stage.signed_dependency(Path(temp),self.keyring,self.fetch,progress=phases.append)
   self.assertEqual(phases[-1],'archive-list');self.assertNotIn(SECRET,json.dumps(stage.staging_failure(caught.exception,phases[-1])))
 def test_actual_source_and_fork_refusal_precedes_directory_and_dependency(self):
  sha='a'*40
  for env,returned,wanted in [({'PROBE_SOURCE_SHA':sha,'GITHUB_REPOSITORY':'noah-be/overte'},'b'*40,'source-check'),({'PROBE_SOURCE_SHA':sha,'GITHUB_REPOSITORY':'overte-org/overte'},sha,'fork-check')]:
   phases=[]
   with patch.dict(os.environ,env,clear=True),patch.object(stage.subprocess,'check_output',return_value=returned)as output,patch.object(stage.tempfile,'mkdtemp')as make,patch.object(stage,'signed_dependency')as dependency:
    with self.assertRaises(ValueError):stage.main(progress=phases.append)
    self.assertEqual(phases[-1],wanted);make.assert_not_called();dependency.assert_not_called();self.assertIs(output.call_args.kwargs['stderr'],subprocess.PIPE)
 def test_real_main_cached_chain_and_private_env_write_keep_success_gates(self):
  sha='a'*40;original=stage.signed_dependency;phases=[]
  def dependency(directory,keyring,*,progress):
   self.assertEqual(keyring,'/usr/share/keyrings/ubuntu-archive-keyring.gpg');return original(directory,self.keyring,self.fetch,progress=progress)
  with tempfile.TemporaryDirectory()as temp:
   env=Path(temp)/'env';env.write_text('')
   with patch.dict(os.environ,{'PROBE_SOURCE_SHA':sha,'GITHUB_REPOSITORY':'noah-be/overte','RUNNER_TEMP':temp,'GITHUB_ENV':str(env)},clear=True),patch.object(stage.subprocess,'check_output',wraps=stage.subprocess.check_output)as output,patch.object(stage,'signed_dependency',side_effect=dependency):
    real=output._mock_wraps
    def check(command,**kwargs):return sha+'\n'if command[0]=='git'else real(command,**kwargs)
    output.side_effect=check;stage.main(progress=phases.append)
   self.assertEqual(phases[-1],'workflow-env-write');entries=dict(line.split('=',1)for line in env.read_text().splitlines());self.assertEqual(set(entries),{'ATOMIC_PROBE_DIRECTORY','OVERTE_LAB_ROOT','ATOMIC_PROBE_OUTPUT'});self.assertTrue((Path(entries['ATOMIC_PROBE_DIRECTORY'])/'strace').is_file());self.assertEqual((Path(entries['ATOMIC_PROBE_DIRECTORY']).parent/'dependency-proof.private.json').stat().st_mode&0o777,0o600)

if __name__=='__main__':unittest.main()
