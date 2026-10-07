#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Own-child pipe tests; no Qt, display, network or editor simulation."""
import ast,os,selectors,subprocess,sys,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
source=(HERE/'run.py').read_text()
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='capture_bounded')
namespace=dict(os=os,selectors=selectors,subprocess=subprocess,time=time)
exec(compile(ast.Module(body=[node],type_ignores=[]),str(HERE/'run.py'),'exec'),namespace)
capture=namespace['capture_bounded']
class OwnedPipes(unittest.TestCase):
 def child(self,script):
  return subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 def finish(self,p):
  if p.poll() is None:p.kill()
  p.wait(timeout=2);p.stdout.close();p.stderr.close()
 def test_both_streams_are_drained_and_each_retention_is_bounded(self):
  p=self.child('import os;os.write(1,b"a"*200000);os.write(2,b"b"*200000)')
  try:
   out,err,truncated=capture(p,2);self.assertEqual(out,'a'*65536);self.assertEqual(err,'b'*65536);self.assertTrue(truncated);self.assertEqual(p.returncode,0)
  finally:self.finish(p)
 def test_exact_budget_and_exit_are_preserved(self):
  p=self.child('import os;os.write(1,b"x"*65536);os.write(2,b"ok")')
  try:self.assertEqual(capture(p,2),('x'*65536,'ok',False));self.assertEqual(p.returncode,0)
  finally:self.finish(p)
 def test_original_deadline_refuses_an_unfinished_child(self):
  p=self.child('import time;time.sleep(2)')
  try:
   with self.assertRaises(subprocess.TimeoutExpired):capture(p,.05)
   self.assertIsNone(p.poll())
  finally:self.finish(p)
if __name__=='__main__':unittest.main()
