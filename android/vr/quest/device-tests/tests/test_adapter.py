#!/usr/bin/env python3
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ADAPTER=Path(__file__).resolve().parents[1]/"adapter.py"
MOCK='''#!/usr/bin/env python3
import sys
a=sys.argv[1:]
if a==["devices","-l"]: print("List of devices attached\\nquest-private device model:Quest_3")
elif a==["-s","quest-private","get-state"]: print("device")
elif a[:3]==["-s","quest-private","shell"]:
 s=a[3:]; p={"ro.product.manufacturer":"Meta","ro.product.brand":"Oculus","ro.product.model":"Quest 3","ro.product.device":"eureka","ro.kernel.qemu":"0","ro.product.cpu.abilist":"arm64-v8a","ro.build.version.sdk":"34"}
 if s[:1]==["getprop"]: print(p.get(s[1],""))
 elif s[:3]==["am","force-stop","io.highfidelity.questInterface"]: pass
 else: print("")
else: raise SystemExit(3)
'''
class Test(unittest.TestCase):
 def test_contract(self):
  with tempfile.TemporaryDirectory() as d:
   adb=Path(d)/"adb";adb.write_text(MOCK);adb.chmod(0o700);env=os.environ|{"OVERTE_ANDROID_ADB":str(adb)}
   r=subprocess.run([sys.executable,str(ADAPTER),"discover"],text=True,capture_output=True,env=env);self.assertEqual(0,r.returncode,r.stderr);self.assertEqual("android-vr-quest",json.loads(r.stdout)[0]["platform"])
   r=subprocess.run([sys.executable,str(ADAPTER),"describe","--target","quest-private"],text=True,capture_output=True,env=env);self.assertEqual(0,r.returncode,r.stderr);self.assertNotIn("quest-private",r.stdout)
   for _ in range(2):
    r=subprocess.run([sys.executable,str(ADAPTER),"cleanup","--target","quest-private"],text=True,capture_output=True,env=env);self.assertEqual(0,r.returncode,r.stderr)
if __name__=="__main__":unittest.main()
