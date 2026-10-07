# SPDX-License-Identifier: Apache-2.0
"""Bounded synthetic X11/readiness and real owned-child lifecycle contracts."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
spec=importlib.util.spec_from_file_location('owned_xvfb',SOURCE/'owned-xvfb.py');x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
spec=importlib.util.spec_from_file_location('owned_prepare',SOURCE/'prepare.py');prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)

class DisplayReadiness(unittest.TestCase):
    def server(self,payload,descriptor):
        return subprocess.Popen([sys.executable,str(SOURCE/'owned-exec.py'),str(os.getpid()),sys.executable,'-c',
            'import os,sys,time;os.write(int(sys.argv[1]),bytes.fromhex(sys.argv[2]));time.sleep(10)',str(descriptor),payload.hex()],pass_fds=(descriptor,),start_new_session=True)
    def test_actual_display_pipe_requires_one_bounded_decimal_record(self):
        for payload,accepted in [(b'123\n',True),(b'3\nextra',False),(b'-1\n',False),(b'65536\n',False),(b'1'*32,False)]:
            with self.subTest(payload=payload):
                r,w=os.pipe();child=self.server(payload,w);os.close(w)
                try:
                    if accepted:self.assertEqual(x.display_number(child,r,time.monotonic()+2),123)
                    else:
                        with self.assertRaises(RuntimeError):x.display_number(child,r,time.monotonic()+2)
                finally:os.close(r);x.stop_owned(child)
                self.assertIsNotNone(child.returncode)
    def test_silent_server_deadline_and_cancellation_terminate_only_the_owned_child(self):
        for cancelled in (False,True):
            r,w=os.pipe();child=self.server(b'',w);os.close(w)
            try:
                with self.assertRaisesRegex(RuntimeError,'cancelled' if cancelled else 'deadline'):
                    x.display_number(child,r,time.monotonic()+.1,lambda:cancelled)
            finally:os.close(r);x.stop_owned(child)
            self.assertIsNotNone(child.returncode)

class X11Authentication(unittest.TestCase):
    def test_actual_unix_peer_and_X11_success_are_both_required(self):
        # This is an owned synthetic protocol peer, not an actual X server or a
        # headed-renderer pass. It binds only this test's private temp directory.
        code='''import os,socket,struct,sys
s=socket.socket(socket.AF_UNIX);s.bind(sys.argv[1]);s.listen(1);print('ready',flush=True)
c,_=s.accept();data=c.recv(256);assert data[0]==ord('l') and data[2:4]==b'\\x0b\\x00'
assert b'MIT-MAGIC-COOKIE-1' in data and data[-16:]==bytes(range(16))
c.sendall(struct.pack('<BBHHH',int(sys.argv[2]),0,11,0,1)+b'\\0'*4);c.close();s.close()
'''
        with tempfile.TemporaryDirectory(prefix='x11-auth-contract-') as root:
            for status in (1,0):
                socket_file=Path(root)/str(status)
                child=subprocess.Popen([sys.executable,str(SOURCE/'owned-exec.py'),str(os.getpid()),sys.executable,'-c',code,str(socket_file),str(status)],stdout=subprocess.PIPE,text=True,start_new_session=True)
                try:
                    self.assertEqual(child.stdout.readline().strip(),'ready')
                    if status:x.authenticated_setup(socket_file,child,bytes(range(16)),time.monotonic()+2)
                    else:
                        with self.assertRaisesRegex(RuntimeError,'setup-refused'):x.authenticated_setup(socket_file,child,bytes(range(16)),time.monotonic()+2)
                    child.wait(timeout=2);self.assertEqual(child.returncode,0)
                finally:x.stop_owned(child);child.stdout.close()
    def test_cookie_and_deadline_validation_precedes_any_connection(self):
        for cookie,deadline in [(b'invalid',time.monotonic()+2),(bytes(16),time.monotonic()-1)]:
            with self.assertRaises(RuntimeError):x.authenticated_setup('/no/socket',type('Child',(),{'pid':os.getpid()})(),cookie,deadline)

class OwnedGate(unittest.TestCase):
    def fixture(self,root):
        server=root/'fake-xvfb';server.write_text('#!'+sys.executable+'\nimport os,sys,time\na=sys.argv;open(os.environ["SERVER_PID"],"w").write(str(os.getpid()));os.write(int(a[a.index("-displayfd")+1]),b"123\\n");time.sleep(20)\n');server.chmod(0o700)
        auth=root/'fake-xauth';auth.write_text('#!'+sys.executable+'\nimport sys\na=sys.stdin.read();assert "MIT-MAGIC-COOKIE-1" in a and len(a.split()[-1])==32\n');auth.chmod(0o700)
        return server,auth
    def assert_gone(self,pid):
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)
    def test_real_gate_inherits_only_its_display_and_server_survives_until_gate_finishes(self):
        with tempfile.TemporaryDirectory(prefix='owned-xvfb-gate-') as dirname:
            root=Path(dirname);server,auth=self.fixture(root);marker=root/'server-pid'
            env=dict(os.environ,SERVER_PID=str(marker),DISPLAY=':999')
            code='import os,stat;assert os.environ["DISPLAY"]==":123";assert stat.S_IMODE(os.stat(os.environ["XAUTHORITY"]).st_mode)==0o600;os.kill(int(open(os.environ["SERVER_PID"]).read()),0)'
            with patch.object(x,'authenticated_setup'):
                self.assertEqual(x.run_gate(str(server),str(auth),[sys.executable,'-c',code],root,env),0)
            self.assert_gone(int(marker.read_text()));self.assertEqual(list(root.glob('owned-xvfb-*')),[])
    def test_real_SIGTERM_cancels_active_gate_and_reaps_both_owned_groups(self):
        with tempfile.TemporaryDirectory(prefix='owned-xvfb-cancel-') as dirname:
            root=Path(dirname);server,auth=self.fixture(root);server_marker=root/'server-pid';gate_marker=root/'gate-pid';env=dict(os.environ,SERVER_PID=str(server_marker))
            code='import os,time;open('+repr(str(gate_marker))+',"w").write(str(os.getpid()));time.sleep(20)'
            def cancel_when_started():
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    if gate_marker.exists() and gate_marker.read_text():os.kill(os.getpid(),signal.SIGTERM);return
                    time.sleep(.01)
            sender=threading.Thread(target=cancel_when_started);sender.start()
            try:
                with patch.object(x,'authenticated_setup'),self.assertRaisesRegex(RuntimeError,'cancelled'):
                    x.run_gate(str(server),str(auth),[sys.executable,'-c',code],root,env)
            finally:sender.join(timeout=4)
            self.assert_gone(int(server_marker.read_text()));self.assert_gone(int(gate_marker.read_text()));self.assertEqual(list(root.glob('owned-xvfb-*')),[])

class EarlySummary(unittest.TestCase):
    def test_actual_prepare_writes_bounded_failure_artifact_before_host_preflight(self):
        with tempfile.TemporaryDirectory(prefix='prepare-failure-summary-') as dirname:
            repo=Path(dirname);(repo/'browser-client').mkdir();(repo/'browser-client/package.json').write_text('{}')
            def preflight(_repo,_source,runtime):
                self.assertEqual(json.loads((runtime/'prepare-summary.json').read_text())['failureCategory'],'preflight-not-completed')
                raise RuntimeError('required-host-tool-unavailable:xauth')
            with patch.object(sys,'argv',['prepare.py','--repo',str(repo),'--source-sha','a'*40]),patch.object(prepare,'prepare_dependencies',side_effect=preflight),self.assertRaisesRegex(RuntimeError,'xauth'):prepare.main()
            summary=repo/'build/jenkins-browser-ci/prepare-summary.json';value=json.loads(summary.read_text());self.assertFalse(value['passed']);self.assertEqual(value['failureCategory'],'required-host-tool-unavailable:xauth');self.assertEqual(summary.stat().st_mode&0o777,0o600);self.assertLess(summary.stat().st_size,65536)
    def test_failure_summary_cannot_leak_exception_credentials_or_arbitrary_paths(self):
        with tempfile.TemporaryDirectory(prefix='prepare-private-summary-') as dirname:
            repo=Path(dirname);(repo/'browser-client').mkdir();(repo/'browser-client/package.json').write_text('{}')
            with patch.object(sys,'argv',['prepare.py','--repo',str(repo),'--source-sha','a'*40]),patch.object(prepare,'prepare_dependencies',side_effect=RuntimeError('/private/path secret=token')),self.assertRaises(RuntimeError):prepare.main()
            text=(repo/'build/jenkins-browser-ci/prepare-summary.json').read_text();self.assertNotIn('token',text);self.assertNotIn('/private/path',text);self.assertIn('RuntimeError',text)

if __name__=='__main__':unittest.main()
