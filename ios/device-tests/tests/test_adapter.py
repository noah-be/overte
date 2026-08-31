#!/usr/bin/env python3
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ADAPTER=Path(__file__).resolve().parents[1]/"adapter.py"
MOCK='''#!/usr/bin/env python3
import json,pathlib,sys
a=sys.argv[1:]; out=pathlib.Path(a[a.index("--json-output")+1])
if a[:3]==["devicectl","list","devices"]: value={"result":{"devices":[{"identifier":"ios-private","connectionProperties":{"tunnelState":"connected","pairingState":"paired"},"deviceProperties":{"developerModeStatus":"enabled","ddiServicesAvailable":True,"osVersionNumber":"18.5"},"hardwareProperties":{"deviceType":"iPad","productType":"iPad14,5","marketingName":"iPad Pro"}}]}}
elif a[:5]==["devicectl","device","process","launch","--device"]: value={"result":{"launched":True}}
elif a[:5]==["devicectl","device","process","terminate","--device"]: value={"result":{"terminated":True}}
else: raise SystemExit(3)
out.write_text(json.dumps(value))
'''
class Test(unittest.TestCase):
 def test_protocol_and_cleanup(self):
  with tempfile.TemporaryDirectory() as d:
   tool=Path(d)/"xcrun";tool.write_text(MOCK);tool.chmod(0o700);env=os.environ|{"OVERTE_APPLE_XCRUN":str(tool)}
   r=subprocess.run([sys.executable,str(ADAPTER),"discover"],text=True,capture_output=True,env=env);self.assertEqual(0,r.returncode,r.stderr);self.assertEqual("ios",json.loads(r.stdout)[0]["platform"])
   r=subprocess.run([sys.executable,str(ADAPTER),"describe","--target","ios-private"],text=True,capture_output=True,env=env);self.assertEqual(0,r.returncode,r.stderr);self.assertNotIn("ios-private",r.stdout)
   r=subprocess.run([sys.executable,str(ADAPTER),"invoke","--target","ios-private","--operation","app.launch"],text=True,capture_output=True,env=env);self.assertEqual(0,r.returncode,r.stderr)
   for _ in range(2):
    r=subprocess.run([sys.executable,str(ADAPTER),"cleanup","--target","ios-private"],text=True,capture_output=True,env=env);self.assertEqual(0,r.returncode,r.stderr)
if __name__=="__main__":unittest.main()
