# SPDX-License-Identifier: Apache-2.0
"""Source-exact hook controls; no kernel, namespace, sudo or native execution."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('atomic_observer_hook_contract',HERE/'test_observer.py')
T=importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)
ORIGINAL_SOURCE_SHA256='8f58965bf4878d6144594ad4c5a76ffbee6713d4a2c35fbc1f5ff2cb2c53f485'
WORKFLOW_ORIGINAL_SHA256='9d8940cb73ec6d68ea89dbbdb17ec3078aa175055c9c0b97200e5efa5b07efe3'
IMPORTS="""from contextlib import nullcontext
kernel_spec = importlib.util.spec_from_file_location('atomic_kernel_audit', HERE / 'kernel_audit.py')
kernel_audit = importlib.util.module_from_spec(kernel_spec)
kernel_spec.loader.exec_module(kernel_audit)
"""
HOOK="""            audit_mode = os.environ.get('ATOMIC_DIAGNOSTIC_KERNEL_AUDIT')
            audit_context = (kernel_audit.observe_original_run() if audit_mode in ('readonly', 'sudo-noninteractive')
                             else nullcontext(None))
            with audit_context as audit_receipt:
"""
FAILURE="""                if audit_receipt is not None:
                    cause = kernel_audit.collect(audit_receipt, allow_sudo=audit_mode == 'sudo-noninteractive')
                    print('ATOMIC_PREFLIGHT_KERNEL_AUDIT:' + json.dumps(cause, sort_keys=True, separators=(',', ':')), flush=True)
"""
WORKFLOW_DIAGNOSTICS=(
"""      continue_diagnostics_after_contract_failure:
        description: 'Collect the owned domain trace after a contract failure; the job remains failed'
        type: boolean
        default: false
""",
"        id: source\n", "        id: stage\n", "        id: contracts\n",
"""        id: prepare
        # Explicit diagnostics never turn the failed contract into a passing gate.
        if: ${{ !cancelled() && steps.source.outcome == 'success' && steps.stage.outcome == 'success' && (steps.contracts.outcome == 'success' || (github.event_name == 'workflow_dispatch' && inputs.continue_diagnostics_after_contract_failure && steps.contracts.outcome == 'failure')) }}
""",
"        if: ${{ !cancelled() && steps.prepare.outcome == 'success' }}\n",
"""      confined_native_diagnostic:
        description: 'Explicit alternate signed-bwrap launch; original failed contracts remain failed'
        type: boolean
        default: false
""",
"""        env:
          CONFINED_NATIVE_DIAGNOSTIC: ${{ github.event_name == 'workflow_dispatch' && inputs.confined_native_diagnostic && 'true' || 'false' }}
""",
"""          probe_options=()
          if [ "$CONFINED_NATIVE_DIAGNOSTIC" = true ]; then
            probe_options=(--confined-diagnostic)
          fi
""",
)

def original_workflow(workflow):
    # Strip only the reviewed default-off continuation, retaining the original
    # whole-workflow hash and every original command, gate and artifact rule.
    for addition in WORKFLOW_DIAGNOSTICS:
        if workflow.count(addition)!=1:
            raise ValueError('changed-diagnostic-workflow')
        workflow=workflow.replace(addition,'',1)
    options=' "${probe_options[@]}"'
    if workflow.count(options)!=1:raise ValueError('changed-diagnostic-workflow')
    workflow=workflow.replace(options,'',1)
    return workflow

def original_source(source):
    for addition in (IMPORTS,HOOK,FAILURE):
        if source.count(addition)!=1:
            raise ValueError('changed-diagnostic-source')
    source=source.replace(IMPORTS,'',1).replace(HOOK,'',1).replace(FAILURE,'',1)
    begin=source.index("                result = subprocess.run(['/usr/bin/unshare'")
    end=source.index('\n            if result.returncode != 0:',begin)
    lines=source[begin:end].splitlines()
    if any(not line.startswith('    ') for line in lines):
        raise ValueError('changed-command-indentation')
    return source[:begin]+'\n'.join(line[4:] for line in lines)+source[end:]

class IntegrationTests(unittest.TestCase):
    def run_control(self,mode=None,code=127,timeout=False):
        calls=[];state={'inside':False};receipt=object()
        @contextlib.contextmanager
        def observed():
            calls.append(('observe',));state['inside']=True
            try:yield receipt
            finally:state['inside']=False;calls.append(('finished',))
        def command(argv,**kwargs):
            calls.append(('command',state['inside'],argv,kwargs))
            if timeout:raise subprocess.TimeoutExpired(argv,8)
            return subprocess.CompletedProcess(argv,code,b'',b'setpriv: apply bounding set: Operation not permitted\n')
        def collected(value,**kwargs):
            self.assertIs(value,receipt);self.assertFalse(state['inside'])
            calls.append(('collect',kwargs))
            return {'status':'ownership-unqualified','censored':False,'kernelAuditRows':0,'ownedSetpcapDenials':0,'authentication':'unqualified'}
        output=io.StringIO();failure=None
        env={} if mode is None else {'ATOMIC_DIAGNOSTIC_KERNEL_AUDIT':mode}
        with patch.dict(os.environ,env,clear=True),patch.object(T.subprocess,'run',side_effect=command),patch.object(T.kernel_audit,'observe_original_run',side_effect=observed),patch.object(T.kernel_audit,'collect',side_effect=collected),contextlib.redirect_stdout(output):
            try:T.ObserverTests('test_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight').test_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight()
            except (AssertionError,subprocess.TimeoutExpired) as error:failure=error
        return calls,output.getvalue(),failure

    def test_literal_stripping_restores_entire_original_source(self):
        source=(HERE/'test_observer.py').read_text()
        self.assertEqual(hashlib.sha256(original_source(source).encode()).hexdigest(),ORIGINAL_SOURCE_SHA256)
        for old,new in [('timeout=8','timeout=9'),("'--keep-caps'","'--map-root-user'"),('assert r["exitCode"]==0','assert True'),("self.assertEqual(result.returncode, 0,","self.assertEqual(result.returncode, 127,")]:
            self.assertIn(old,source)
            self.assertNotEqual(hashlib.sha256(original_source(source.replace(old,new,1)).encode()).hexdigest(),ORIGINAL_SOURCE_SHA256)
        for old,new in [('allow_sudo=audit_mode == \'sudo-noninteractive\'','allow_sudo=True'),("('readonly', 'sudo-noninteractive')","('anything',)")]:
            with self.assertRaises(ValueError):original_source(source.replace(old,new,1))

    def test_workflow_removes_only_explicit_unit_step_authority(self):
        workflow=(HERE.parents[2]/'.github/workflows/browser-client-atomic-settings.yml').read_text()
        addition="""        env:
          # Explicit read-only, noninteractive diagnostic authority. The original
          # command, policy setup and every capability assertion remain unchanged.
          ATOMIC_DIAGNOSTIC_KERNEL_AUDIT: sudo-noninteractive
"""
        self.assertEqual(workflow.count(addition),1)
        original=original_workflow(workflow.replace(addition,'',1))
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),WORKFLOW_ORIGINAL_SHA256)
        for old,new in [('default: false','default: true'),("steps.source.outcome == 'success'","true"),("steps.stage.outcome == 'success'","true"),("github.event_name == 'workflow_dispatch'","true")]:
            with self.assertRaises(ValueError):original_workflow(workflow.replace(old,new,1))
        changed=original_workflow(workflow.replace('            --private-output "$ATOMIC_PROBE_OUTPUT"','            --private-output /tmp/unowned',1).replace(addition,'',1))
        self.assertNotEqual(hashlib.sha256(changed.encode()).hexdigest(),WORKFLOW_ORIGINAL_SHA256)

    def test_default_and_unknown_modes_never_observe_or_collect(self):
        for mode in (None,'1','arbitrary'):
            calls,output,failure=self.run_control(mode)
            self.assertEqual([item[0] for item in calls],['command'])
            self.assertNotIn('ATOMIC_PREFLIGHT_KERNEL_AUDIT:',output)
            self.assertIsInstance(failure,AssertionError)

    def test_failed_original_readonly_and_explicit_sudo_modes(self):
        for mode,allowed in [('readonly',False),('sudo-noninteractive',True)]:
            calls,output,failure=self.run_control(mode)
            self.assertEqual([item[0] for item in calls],['observe','command','finished','collect'])
            self.assertTrue(calls[1][1])
            self.assertEqual(calls[1][2][:-1],['/usr/bin/unshare','--user','--map-current-user','--keep-caps','--ipc','--','/usr/bin/setpriv','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','--',sys.executable])
            self.assertEqual(calls[1][3],{'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'timeout':8})
            self.assertEqual(calls[-1][1],{'allow_sudo':allowed})
            lines=[line for line in output.splitlines() if line.startswith('ATOMIC_PREFLIGHT_KERNEL_AUDIT:')]
            self.assertEqual(len(lines),1)
            self.assertEqual(json.loads(lines[0].split(':',1)[1])['status'],'ownership-unqualified')
            self.assertIsInstance(failure,AssertionError)
            self.assertIn('unchanged-own-child-confinement-preflight-refused:',str(failure))
            self.assertIn('ATOMIC_PREFLIGHT_PRIVATE_CAPTURE:',output)

    def test_success_and_original_timeout_do_not_collect(self):
        calls,output,failure=self.run_control('sudo-noninteractive',code=0)
        self.assertIsNone(failure)
        self.assertEqual([item[0] for item in calls],['observe','command','finished'])
        self.assertEqual(output,'')
        calls,output,failure=self.run_control('sudo-noninteractive',timeout=True)
        self.assertIsInstance(failure,subprocess.TimeoutExpired)
        self.assertEqual(failure.timeout,8)
        self.assertEqual([item[0] for item in calls],['observe','command','finished'])
        self.assertEqual(output,'')

if __name__=='__main__':unittest.main()
