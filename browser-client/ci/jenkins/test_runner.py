# SPDX-License-Identifier: Apache-2.0
"""Guard, source, owned-child and complete-result contracts; no services."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,SOURCE/filename)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
r=module('ci_runner','run.py')
g=module('ci_gates','gates.py')
x=module('ci_xml','create-job-xml.py')
owner=module('ci_namespace','namespace-owner.py')
prepare=module('ci_prepare','prepare.py')


class Source(unittest.TestCase):
    def test_runtime_environment_does_not_copy_credentials_or_desktop_devices(self):
        with patch.dict(os.environ,{'PATH':'/usr/bin','HOME':'/unchanged/authored-home',
             'JENKINS_SECRET':'authored-secret','GITHUB_TOKEN':'authored-token',
             'DISPLAY':':999','PULSE_SERVER':'unix:authored-device','LD_LIBRARY_PATH':'/other/native'},clear=True):
            environment=r.safe_environment()
        self.assertEqual(environment['HOME'],'/unchanged/authored-home')
        self.assertEqual(environment['PATH'],'/usr/bin')
        self.assertEqual(environment['CI'],'true')
        for key in ('JENKINS_SECRET','GITHUB_TOKEN','DISPLAY','PULSE_SERVER','LD_LIBRARY_PATH'):
            self.assertNotIn(key,environment)

    def test_exact_authorized_commit_and_fetch_url_are_required(self):
        sha='a'*40
        answers=[SimpleNamespace(stdout=sha+'\n'),SimpleNamespace(stdout=r.REMOTE+'\n')]
        with patch.object(r.subprocess,'run',side_effect=answers):
            self.assertEqual(r.checked_source(Path('/owned/checkout'),sha),sha)

    def test_wrong_fork_or_wrong_commit_is_refused(self):
        for head,url in [('b'*40,r.REMOTE),('a'*40,'https://github.com/overte-org/overte')]:
            with self.subTest(head=head,url=url),patch.object(r.subprocess,'run',side_effect=[
                    SimpleNamespace(stdout=head),SimpleNamespace(stdout=url)]),self.assertRaises(RuntimeError):
                r.checked_source(Path('/owned/checkout'),'a'*40)

    def test_invalid_sha_fails_before_any_git_or_network_command(self):
        for sha in ('main','A'*40,'a'*39,'a'*40+'; command','../fork'):
            with self.subTest(sha=sha),patch.object(r.subprocess,'run') as command,self.assertRaises(RuntimeError):
                r.checked_source(Path('/owned/checkout'),sha)
            command.assert_not_called()


class Completion(unittest.TestCase):
    def rows(self):
        return [{'stage':name,'passed':True} for name in g.REQUIRED_STAGES]

    def test_complete_all_stage_result_is_required(self):
        self.assertTrue(g.complete_pass(self.rows()))

    def test_missing_or_failed_firefox_is_not_a_pass(self):
        rows=self.rows()
        self.assertFalse(g.complete_pass([row for row in rows if row['stage']!='native-core-firefox']))
        for row in rows:
            if row['stage']=='native-core-firefox':row['passed']=False
        self.assertFalse(g.complete_pass(rows))

    def test_cleanup_failure_or_extra_duplicate_stage_is_not_a_pass(self):
        rows=self.rows()
        self.assertFalse(g.complete_pass(rows+[rows[0]]))
        for row in rows:
            if row['stage']=='owned-lab-cleanup':row['passed']=False
        self.assertFalse(g.complete_pass(rows))

    def test_early_failure_with_only_successful_cleanup_is_not_a_pass(self):
        self.assertFalse(g.complete_pass([{'stage':'owned-lab-cleanup','passed':True},
            {'stage':'curate-native-core','passed':True}]))

    def test_missing_manager_state_contract_is_not_a_pass(self):
        self.assertIn('test_manage_state-py',g.REQUIRED_STAGES)
        self.assertFalse(g.complete_pass([row for row in self.rows()
            if row['stage']!='test_manage_state-py']))


class Identity(unittest.TestCase):
    def test_root_gate_process_is_refused(self):
        with patch.object(g.os,'getuid',return_value=0),self.assertRaisesRegex(RuntimeError,'must-not-run-as-root'):
            g.isolated_identity()

    def test_each_capability_set_must_be_cleared(self):
        names=('CapInh','CapPrm','CapEff','CapBnd','CapAmb')
        for active in names:
            document='\n'.join(name+':\t'+('0000000000000001' if name==active else '0000000000000000') for name in names)
            with self.subTest(active=active),patch.object(g.os,'getuid',return_value=1000),\
                 patch.object(Path,'read_text',return_value=document),self.assertRaisesRegex(RuntimeError,'retained'):
                g.isolated_identity()

    def test_zero_caps_nonroot_is_accepted(self):
        document='\n'.join(name+':\t0000000000000000' for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
        with patch.object(g.os,'getuid',return_value=1000),patch.object(Path,'read_text',return_value=document):
            g.isolated_identity()

    def test_namespace_setup_cannot_run_outside_private_pid_init(self):
        with patch.object(owner.os,'getpid',return_value=123),patch.object(owner.subprocess,'run') as command,\
             self.assertRaisesRegex(RuntimeError,'private-PID-init'):
            owner.main()
        command.assert_not_called()


class OwnedChildren(unittest.TestCase):
    def test_installers_have_parent_death_private_pid_and_capability_dropping(self):
        with patch.object(prepare,'checked_executable',side_effect=lambda name:'/usr/bin/'+name):
            command=prepare.installer_command(['/authored/npm','ci'])
        self.assertEqual(command[:3],[sys.executable,str(SOURCE/'owned-exec.py'),str(os.getpid())])
        self.assertIn('--kill-child=KILL',command)
        self.assertIn('--keep-caps',command)
        self.assertIn('--pid',command)
        self.assertNotIn('--net',command)
        drop=command.index('--bounding-set=-all')
        self.assertEqual(command[drop:],['--bounding-set=-all','--inh-caps=-all',
            '--ambient-caps=-all','--',sys.executable,str(SOURCE/'prepare.py'),
            '--execute-installer','/authored/npm','ci'])

    def test_installer_execution_requires_actual_five_zero_capability_sets(self):
        document='\n'.join(name+':\t0000000000000000' for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
        with patch.object(sys,'argv',['prepare.py','--execute-installer','/authored/npm','ci']),\
            patch('gates.os.getuid',return_value=1000),patch.object(Path,'read_text',return_value=document),\
            patch.object(prepare.os,'execvpe',side_effect=SystemExit(0)) as execute,self.assertRaises(SystemExit):
            prepare.main()
        execute.assert_called_once_with('/authored/npm',['/authored/npm','ci'],os.environ)

    def test_retained_setup_capability_refuses_installer_before_exec(self):
        document='\n'.join(name+':\t'+('1' if name=='CapEff' else '0') for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
        with patch.object(sys,'argv',['prepare.py','--execute-installer','/authored/npm','ci']),\
            patch('gates.os.getuid',return_value=1000),patch.object(Path,'read_text',return_value=document),\
            patch.object(prepare.os,'execvpe') as execute,self.assertRaisesRegex(RuntimeError,'retained'):
            prepare.main()
        execute.assert_not_called()

    def test_helper_is_kernel_killed_after_its_actual_parent_is_hard_killed(self):
        # The isolated test supervisor adopts and reaps its own orphan. No PID
        # lookup, user service, namespace, daemon or global policy is modified.
        supervisor = '''
import ctypes, os, signal, subprocess, sys, time
libc=ctypes.CDLL(None,use_errno=True)
assert libc.prctl(36,1,0,0,0)==0
parent_script="""import os,subprocess,sys,time
p=subprocess.Popen([sys.executable,sys.argv[1],str(os.getpid()),sys.executable,'-c','import time;print("ready",flush=True);time.sleep(30)'],stdout=subprocess.PIPE,text=True)
print(p.pid,flush=True)
print(p.stdout.readline().strip(),flush=True)
time.sleep(30)
"""
parent=subprocess.Popen([sys.executable,'-c',parent_script,sys.argv[1]],stdout=subprocess.PIPE,text=True)
child=None;reaped=False
try:
 child=int(parent.stdout.readline())
 assert parent.stdout.readline().strip()=='ready'
 parent.kill();parent.wait(timeout=3)
 deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  pid,status=os.waitpid(child,os.WNOHANG)
  if pid:
   reaped=True
   assert os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGKILL
   break
  time.sleep(.01)
 assert reaped,'owned helper survived actual parent death'
finally:
 if parent.poll() is None:parent.kill();parent.wait(timeout=3)
 if child and not reaped:
  try:os.kill(child,signal.SIGKILL)
  except ProcessLookupError:pass
  os.waitpid(child,0)
 parent.stdout.close()
'''
        subprocess.run([sys.executable,'-c',supervisor,str(SOURCE/'owned-exec.py')],
            check=True,capture_output=True,timeout=10,env=r.safe_environment())

    def test_parent_registration_race_refuses_to_execute_command(self):
        result=subprocess.run([sys.executable,str(SOURCE/'owned-exec.py'),
            str(os.getpid()+1000000),sys.executable,'-c','print("must-not-execute")'],
            capture_output=True,text=True,timeout=5,env=r.safe_environment())
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(result.stdout,'')
        self.assertEqual(result.stderr.strip(),'owned-helper-launch-failed')

    def test_finished_child_is_never_signalled(self):
        child=SimpleNamespace(poll=lambda:0)
        with patch.object(r.os,'killpg') as kill:r.stop_owned(child)
        kill.assert_not_called()

    def test_changed_group_is_never_signalled(self):
        child=SimpleNamespace(pid=1234,poll=lambda:None)
        with patch.object(r.os,'getpgid',return_value=4567),patch.object(r.os,'killpg') as kill,\
             self.assertRaisesRegex(RuntimeError,'group-changed'):
            r.stop_owned(child)
        kill.assert_not_called()

    def test_real_owned_process_group_is_terminated_and_reaped(self):
        process=subprocess.Popen([sys.executable,'-c','import time;print("ready",flush=True);time.sleep(30)'],
            stdout=subprocess.PIPE,text=True,start_new_session=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'ready')
            r.stop_owned(process)
            self.assertEqual(process.returncode,-signal.SIGTERM)
        finally:
            if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
            process.stdout.close()


class PrivateConfiguration(unittest.TestCase):
    def test_xml_contains_exact_selector_without_disclosing_it_on_stdout(self):
        with tempfile.TemporaryDirectory(prefix='overte-ci-xml-') as directory:
            root=Path(directory);root.chmod(0o700)
            label=root/'selector';label.write_text('authored-test-selector');label.chmod(0o600)
            result=root/'job.xml';output=io.StringIO()
            with patch.object(sys,'argv',['create-job-xml.py','--agent-label-file',str(label),'--output',str(result)]),\
                 contextlib.redirect_stdout(output):x.main()
            self.assertNotIn('authored-test-selector',output.getvalue())
            self.assertEqual(result.stat().st_mode & 0o777,0o600)
            xml=ET.fromstring(result.read_text())
            parameter=xml.find('properties/hudson.model.ParametersDefinitionProperty/parameterDefinitions/hudson.model.StringParameterDefinition')
            self.assertIsNotNone(parameter)
            self.assertEqual(parameter.findtext('name'),'SOURCE_SHA')
            self.assertEqual(parameter.findtext('defaultValue'),'')
            concurrent=xml.find('properties/org.jenkinsci.plugins.workflow.job.properties.DisableConcurrentBuildsJobProperty')
            self.assertIsNotNone(concurrent)
            self.assertEqual(concurrent.findtext('abortPrevious'),'false')
            script=xml.find('definition/script').text
            self.assertIn('node("authored-test-selector")',script)
            self.assertIn('https://github.com/noah-be/overte',script)
            self.assertIn('disableConcurrentBuilds()',script)
            self.assertIn('browser-client/ci/jenkins/prepare.py',script)
            self.assertIn('browser-client/ci/jenkins/run.py',script)
            self.assertNotIn('browser-client/lab/jenkins-ci/',script)
            self.assertNotIn('withCredentials',script)

    def test_writable_or_expression_selector_is_refused_before_xml_creation(self):
        for text,mode in [('test-label',0o644),('test || another',0o600),('bad";command',0o600)]:
            with self.subTest(text=text,mode=mode),tempfile.TemporaryDirectory(prefix='overte-ci-xml-') as directory:
                root=Path(directory);root.chmod(0o700)
                label=root/'selector';label.write_text(text);label.chmod(mode)
                result=root/'job.xml'
                with patch.object(sys,'argv',['create-job-xml.py','--agent-label-file',str(label),'--output',str(result)]),\
                     self.assertRaises(RuntimeError):x.main()
                self.assertFalse(result.exists())


# The standard CI contract entry point also exercises the owned display helper.
from test_owned_xvfb import DisplayReadiness, X11Authentication, OwnedGate, EarlySummary

if __name__=='__main__':unittest.main()
