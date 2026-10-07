# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name('namespace-owner.py')

class NamespaceReaping(unittest.TestCase):
    def test_actual_owner_reaps_real_adopted_zombie_without_stealing_gate_status(self):
        code=r"""
import ctypes,os,runpy,subprocess,sys,time
reap=runpy.run_path(sys.argv[1])['reap_adopted_children']
assert ctypes.CDLL(None).prctl(36,1,0,0,0)==0
# This is our own supervisor subtree; no existing host process is adopted.
gate=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.15);raise SystemExit(7)'])
mid=subprocess.Popen([sys.executable,'-c',"import subprocess,sys;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.04)']);print(p.pid,flush=True)"],stdout=subprocess.PIPE,text=True)
owned=int(mid.stdout.readline());mid.wait(timeout=3);mid.stdout.close()
try:
 deadline=time.monotonic()+3;reaped=0
 while time.monotonic()<deadline:
  reaped+=reap(gate.pid)
  try:os.kill(owned,0)
  except ProcessLookupError:break
  time.sleep(.01)
 else:raise AssertionError('Owned adopted zombie was not reaped')
 assert reaped==1
 assert gate.wait(timeout=3)==7,'Popen must preserve its actual nonzero exit status'
 assert reap(gate.pid)==0
finally:
 if gate.poll() is None:gate.kill();gate.wait(timeout=3)
 try:os.kill(owned,9)
 except ProcessLookupError:pass
 try:os.waitpid(owned,0)
 except ChildProcessError:pass
"""
        result=subprocess.run([sys.executable,'-c',code,str(SOURCE)],capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_actual_owner_never_reaps_or_signals_live_children(self):
        code=r"""
import runpy,subprocess,sys
reap=runpy.run_path(sys.argv[1])['reap_adopted_children']
gate=subprocess.Popen([sys.executable,'-c',"import sys;print('ready',flush=True);sys.stdin.read(1);raise SystemExit(9)"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
other=subprocess.Popen([sys.executable,'-c',"import sys;print('ready',flush=True);sys.stdin.read(1);raise SystemExit(8)"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
try:
 assert gate.stdout.readline().strip()=='ready'
 assert other.stdout.readline().strip()=='ready'
 assert reap(gate.pid)==0
 gate.stdin.write('x');gate.stdin.flush();other.stdin.write('x');other.stdin.flush()
 assert gate.wait(timeout=3)==9
 assert other.wait(timeout=3)==8
finally:
 for p in [gate,other]:
  if p.poll() is None:p.kill();p.wait(timeout=3)
  p.stdin.close();p.stdout.close()
"""
        result=subprocess.run([sys.executable,'-c',code,str(SOURCE)],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
