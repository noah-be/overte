#!/usr/bin/env python3
"""Static and mocked contracts for the Pico device adapter."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ADAPTER = Path(__file__).resolve().parents[1] / "adapter.py"
MOCK = r'''#!/usr/bin/env python3
import sys
a=sys.argv[1:]
if a==["devices","-l"]: print("List of devices attached\npico-secret device model:PICO_4")
elif a==["-s","pico-secret","get-state"]: print("device")
elif a[:3]==["-s","pico-secret","shell"]:
 s=a[3:]
 props={"ro.product.manufacturer":"PICO","ro.product.brand":"PICO","ro.product.model":"PICO 4","ro.product.device":"A8110","ro.kernel.qemu":"0","ro.product.cpu.abilist":"arm64-v8a","ro.build.version.sdk":"32"}
 if s[:1]==["getprop"]: print(props.get(s[1], "1"))
 elif s[:3]==["am","force-stop","org.overte.pico"]: pass
 else: print("")
else: raise SystemExit(3)
'''

class PicoAdapterTest(unittest.TestCase):
    def test_discovery_and_private_description(self):
        with tempfile.TemporaryDirectory() as directory:
            adb=Path(directory)/"adb"; adb.write_text(MOCK); adb.chmod(0o700)
            env=os.environ|{"OVERTE_ANDROID_ADB":str(adb)}
            found=subprocess.run([sys.executable,str(ADAPTER),"discover"],text=True,capture_output=True,env=env)
            self.assertEqual(0,found.returncode,found.stderr)
            self.assertEqual("android-vr-pico",json.loads(found.stdout)[0]["platform"])
            described=subprocess.run([sys.executable,str(ADAPTER),"describe","--target","pico-secret"],text=True,capture_output=True,env=env)
            self.assertEqual(0,described.returncode,described.stderr)
            self.assertNotIn("pico-secret",described.stdout)
            for _ in range(2):
                cleaned=subprocess.run([sys.executable,str(ADAPTER),"cleanup","--target","pico-secret"],text=True,capture_output=True,env=env)
                self.assertEqual(0,cleaned.returncode,cleaned.stderr)

if __name__=="__main__": unittest.main()
