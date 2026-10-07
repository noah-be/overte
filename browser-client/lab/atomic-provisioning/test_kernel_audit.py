# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import kernel_audit as K

BOOT = 'a'*32
RECORD = {'pid': 321, 'startNs': 1_000_000_000, 'endNs': 2_000_000_000,
          'birthTicks': 42, 'qualified': True}
FIELDS = 'apparmor="DENIED" operation="capable" profile="unshare//unpriv" pid=321 comm="setpriv" capability=8 capname="setpcap"'


def envelope(transport='kernel', **changes):
    row = {'_TRANSPORT': transport, '_BOOT_ID': BOOT,
           '__REALTIME_TIMESTAMP': '1500000',
           'MESSAGE': 'audit: type=1400 audit(1.500:22): '+FIELDS}
    if transport == 'audit':
        row.update(_AUDIT_TYPE='1400', _AUDIT_TYPE_NAME='AVC',
                   _SOURCE_REALTIME_TIMESTAMP='1500000', _AUDIT_ID='22',
                   MESSAGE='AVC '+FIELDS)
    row.update(changes)
    return json.dumps(row).encode()


class JournalProjectionTests(unittest.TestCase):
    def test_both_real_kernel_transport_shapes_and_dual_delivery_dedup(self):
        for kind in ('kernel', 'audit'):
            self.assertEqual(K.project_journal(envelope(kind), RECORD, BOOT)['ownedSetpcapDenials'], 1)
        both = K.project_journal(envelope()+b'\n'+envelope('audit'), RECORD, BOOT)
        self.assertEqual(both['kernelAuditRows'], 2)
        self.assertEqual(both['ownedSetpcapDenials'], 1)

    def test_plain_application_stdout_cannot_forge_kernel_record(self):
        for kind in ('stdout', 'journal', 'syslog', 'driver'):
            self.assertEqual(K.project_journal(envelope(kind), RECORD, BOOT)['ownedSetpcapDenials'], 0)

    def test_other_boot_pid_and_event_time_refuse(self):
        cases = [envelope(_BOOT_ID='b'*32), envelope(MESSAGE='audit: type=1400 audit(1.500:22): '+FIELDS.replace('pid=321','pid=999')),
                 envelope(MESSAGE='audit: type=1400 audit(0.500:22): '+FIELDS),
                 envelope('audit', _SOURCE_REALTIME_TIMESTAMP='2500000')]
        for raw in cases:
            self.assertEqual(K.project_journal(raw, RECORD, BOOT)['ownedSetpcapDenials'], 0)

    def test_trusted_audit_type_and_original_exact_fields(self):
        for changes in ({'_AUDIT_TYPE':'1100'}, {'_AUDIT_TYPE_NAME':'USER_AVC'},
                        {'_SOURCE_REALTIME_TIMESTAMP':['1500000']},
                        {'MESSAGE':'AVC '+FIELDS.replace('capability=8','capability=12')}):
            self.assertEqual(K.project_journal(envelope('audit', **changes), RECORD, BOOT)['ownedSetpcapDenials'], 0)

    def test_duplicate_json_keys_and_binary_arrays_refuse(self):
        raw=envelope()[:-1]+b',"_TRANSPORT":"kernel"}'
        self.assertEqual(K.project_journal(raw, RECORD, BOOT)['ownedSetpcapDenials'], 0)
        self.assertEqual(K.project_journal(envelope(MESSAGE=[1,2,3]), RECORD, BOOT)['ownedSetpcapDenials'], 0)

    def test_recursion_bound_refuses_without_exposing_raw_record(self):
        raw = b'{"_BOOT_ID":"' + BOOT.encode() + b'","nested":' + b'['*1500 + b'0' + b']'*1500 + b'}'
        result = K.project_journal(raw, RECORD, BOOT)
        self.assertEqual(result["ownedSetpcapDenials"], 0)
        self.assertEqual(result["status"], "no-matching-owned-audit-record")

    def test_hard_byte_line_and_row_bounds(self):
        for raw in (b'x'*65537, b'x'*8193, b'\n'*129):
            result=K.project_journal(raw, RECORD, BOOT)
            self.assertEqual(result['status'],'journal-bound-refused')
            self.assertTrue(result['censored'])

    def test_no_record_is_unknown_not_success_and_output_private(self):
        result=K.project_journal(envelope(PRIVATE_PASSWORD='credential-private',_EXE='/private/identity'),RECORD,BOOT)
        encoded=json.dumps(result)
        for item in ('credential','/private','321',BOOT):self.assertNotIn(item,encoded)
        empty=K.project_journal(b'',RECORD,BOOT)
        self.assertEqual(empty['status'],'no-matching-owned-audit-record')


class ReceiptTests(unittest.TestCase):
    def fake_launch(self):
        class Child:
            pid=321
        return Child()

    def observed(self, calls=1):
        with patch.object(subprocess,'Popen',lambda *a,**kw:self.fake_launch()),patch.object(K,'_child_birth',return_value=42):
            with K.observe_original_run() as receipt:
                for _ in range(calls):
                    subprocess.Popen([*K._ORIGINAL_PREFIX,sys.executable,'/authored/entry.py'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        return receipt

    def test_same_original_arguments_object_and_timeout_run_not_reimplemented(self):
        calls=[];child=self.fake_launch()
        def spawn(*args,**kwargs):calls.append((args,kwargs));return child
        argv=[*K._ORIGINAL_PREFIX,sys.executable,'/authored/entry.py']
        with patch.object(subprocess,'Popen',spawn),patch.object(K,'_child_birth',return_value=42):
            with K.observe_original_run() as receipt:
                returned=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertIs(returned,child);self.assertIs(calls[0][0][0],argv)
        self.assertEqual(calls[0][1],{'stdout':subprocess.PIPE,'stderr':subprocess.PIPE})
        self.assertTrue(K._runs[receipt]['qualified'])

    def test_multiple_nested_missing_birth_and_wrong_argv_unqualified(self):
        self.assertFalse(K._runs[self.observed(2)]['qualified'])
        with patch.object(subprocess,'Popen',lambda *a,**kw:self.fake_launch()),patch.object(K,'_child_birth',side_effect=FileNotFoundError):
            with K.observe_original_run() as receipt:
                subprocess.Popen([*K._ORIGINAL_PREFIX,sys.executable,'/authored/entry.py'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertFalse(K._runs[receipt]['qualified'])
        with patch.object(subprocess,'Popen',lambda *a,**kw:self.fake_launch()),patch.object(K,'_child_birth',return_value=42):
            with K.observe_original_run() as outer:
                with K.observe_original_run():
                    subprocess.Popen(['/other'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertFalse(K._runs[outer]['qualified'])

    def test_only_source_minted_receipt_and_one_consumption(self):
        for fake in (None,{},K.RunReceipt()):self.assertEqual(K.collect(fake)['status'],'ownership-unqualified')
        receipt=self.observed()
        with patch.object(K,'_checked_executable'),patch.object(K,'_boot_id',return_value=BOOT),patch.object(K,'_bounded_journal',return_value=('complete',b'')):
            self.assertEqual(K.collect(receipt)['status'],'no-matching-owned-audit-record')
            self.assertEqual(K.collect(receipt)['status'],'ownership-unqualified')

    def test_fixed_root_readonly_recipe_and_home_preserved(self):
        receipt=self.observed();calls=[]
        def read(argv,env):
            calls.append((argv,env))
            return ('journal-access-or-command-refused', b'') if len(calls)==1 else ('complete',b'')
        with patch.object(K,'_checked_executable'),patch.object(K,'_boot_id',return_value=BOOT),patch.object(K,'_bounded_journal',side_effect=read):
            K.collect(receipt,allow_sudo=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0][0], '/usr/bin/journalctl')
        argv,env=calls[1]
        self.assertEqual(argv[:7],['/usr/bin/sudo','-n','--','/usr/bin/timeout','--kill-after=1s','2s','/usr/bin/journalctl'])
        self.assertIn('_TRANSPORT=kernel',argv);self.assertIn('_TRANSPORT=audit',argv)
        self.assertNotIn('LD_PRELOAD',env)
        if 'HOME' in os.environ:self.assertEqual(env['HOME'],os.environ['HOME'])

    def test_sudo_never_follows_complete_censored_or_deadline_read(self):
        for terminal in ('complete', 'journal-bound-refused', 'journal-read-deadline'):
            receipt=self.observed()
            with patch.object(K,'_checked_executable') as checked,patch.object(K,'_boot_id',return_value=BOOT),patch.object(K,'_bounded_journal',return_value=(terminal,b'{}' if terminal=='complete' else b'')) as reader:
                K.collect(receipt,allow_sudo=True)
            self.assertEqual(reader.call_count,1)
            self.assertEqual(checked.call_args_list, [unittest.mock.call('/usr/bin/journalctl')])

    def test_explicit_sudo_after_empty_ordinary_view_is_not_a_cause_claim(self):
        receipt=self.observed()
        with patch.object(K,'_checked_executable'),patch.object(K,'_boot_id',return_value=BOOT),patch.object(K,'_bounded_journal',return_value=('complete',b'')) as reader:
            result=K.collect(receipt,allow_sudo=True)
        self.assertEqual(reader.call_count,2)
        self.assertEqual(reader.call_args_list[0].args[0][0],'/usr/bin/journalctl')
        self.assertEqual(reader.call_args_list[1].args[0][0],'/usr/bin/sudo')
        self.assertEqual(result['status'],'no-matching-owned-audit-record')
        self.assertEqual(result['ownedSetpcapDenials'],0)

    def test_readonly_access_refusal_does_not_acquire_privilege(self):
        receipt=self.observed()
        with patch.object(K,'_checked_executable') as checked,patch.object(K,'_boot_id',return_value=BOOT),patch.object(K,'_bounded_journal',return_value=('journal-access-or-command-refused',b'')) as reader:
            result=K.collect(receipt)
        self.assertEqual(result['status'],'journal-access-or-command-refused')
        self.assertEqual(reader.call_count,1)
        self.assertEqual(checked.call_args_list, [unittest.mock.call('/usr/bin/journalctl')])

    def test_refused_collection_does_not_throw_or_return_raw_error(self):
        receipt=self.observed()
        with patch.object(K,'_checked_executable',side_effect=OSError('private-secret')):
            result=K.collect(receipt)
        self.assertEqual(result['status'],'journal-source-or-access-refused')
        self.assertNotIn('private',json.dumps(result))


class PipeBoundsTests(unittest.TestCase):
    def test_real_authored_stalled_pipe_deadline_reaps_same_child(self):
        children = []
        original = subprocess.Popen
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        start = time.monotonic()
        with patch.object(K, 'AUDIT_SECONDS', .1), patch.object(subprocess, 'Popen', spawn):
            terminal, raw = K._bounded_journal(
                [sys.executable, '-c', 'import time;time.sleep(30)'], {'PATH': '/usr/bin'})
        self.assertEqual((terminal, raw), ('journal-read-deadline', b''))
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)
        self.assertTrue(children[0].stderr.closed)
        self.assertLess(time.monotonic() - start, 2)

    def test_real_authored_pipe_bytes_cleanup_and_bound(self):
        env={'PATH':'/usr/bin'}
        terminal,raw=K._bounded_journal([sys.executable,'-c','print("authored-pipe")'],env)
        self.assertEqual((terminal,raw),('complete',b'authored-pipe\n'))
        terminal,raw=K._bounded_journal([sys.executable,'-c','import os;os.write(1,b"x"*100000)'],env)
        self.assertEqual((terminal,raw),('journal-bound-refused',b''))


if __name__=='__main__':unittest.main()
