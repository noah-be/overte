#!/usr/bin/env python3
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ADAPTER=Path(__file__).resolve().parents[1]/"adapter.py"
class Test(unittest.TestCase):
 def test_local_process_contract_and_cleanup(self):
  with tempfile.TemporaryDirectory() as d:
   app=Path(d)/"interface";app.write_text("#!/bin/sh\nsleep 60\n");app.chmod(0o700)
   env=os.environ|{"OVERTE_MACOS_ALLOW_NON_DARWIN":"1","OVERTE_MACOS_EXECUTABLE":str(app),"TMPDIR":d}
   def call(*a):return subprocess.run([sys.executable,str(ADAPTER),*a],text=True,capture_output=True,env=env)
   r=call("discover");self.assertEqual(0,r.returncode,r.stderr);target=json.loads(r.stdout)[0];self.assertEqual("macos",target["platform"]);self.assertEqual(sorted(target["capabilities"]),target["capabilities"]);selector=target["selector"]
   r=call("describe","--target",selector);self.assertEqual(0,r.returncode,r.stderr);self.assertNotIn(selector,r.stdout)
   r=call("invoke","--target",selector,"--operation","app.launch");self.assertEqual(0,r.returncode,r.stderr)
   r=call("invoke","--target",selector,"--operation","app.process");self.assertTrue(json.loads(r.stdout)["running"])
   r=call("invoke","--target",selector,"--operation","telemetry.snapshot");self.assertEqual(0,r.returncode,r.stderr)
   for _ in range(2):
    r=call("cleanup","--target",selector);self.assertEqual(0,r.returncode,r.stderr)
if __name__=="__main__":unittest.main()
