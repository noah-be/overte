# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Validate owned launch records without executing any traced/native process."""
import hashlib,json,os
from pathlib import Path
import tempfile,unittest
import observer

class EnvironmentBound(unittest.TestCase):
 def setUp(self):
  self.temporary=tempfile.TemporaryDirectory(prefix="overte-environment-record-test-")
  self.addCleanup(self.temporary.cleanup)
  root=Path(self.temporary.name).resolve()
  self.document={"version":1,"cwd":str(root),"output":str(root),"environment":{"HOME":os.environ["HOME"]}}
  for name in ("strace","native","unshare"):
   path=root/("domain-server"if name=="native"else name)
   path.write_bytes(b"owned non-executed executable fixture");path.chmod(0o700)
   self.document[name]=str(path);self.document[name+"SHA256"]=hashlib.sha256(path.read_bytes()).hexdigest()
  settings=root/"settings.json";settings.write_text("{}");self.document["settings"]=str(settings)
 def test_more_than_128_short_inherited_variables_preserve_exact_launch_contract(self):
  env={"HOME":os.environ["HOME"],**{f"INHERITED_{i}":"short"for i in range(128)}}
  self.document["environment"]=env
  before=json.dumps(self.document,sort_keys=True)
  argv=observer.validated_launch(self.document)
  self.assertEqual(argv,[self.document["unshare"],"--user","--map-current-user","--ipc","--",self.document["native"],"--user-config",self.document["settings"],"--logOptions","nocolor,nojournald"])
  self.assertEqual(json.dumps(self.document,sort_keys=True),before)
 def test_total_record_bytes_guard_environment_even_when_each_value_is_within_original_limit(self):
  self.document["environment"].update({f"VARIABLE_{i}":"x"*8192 for i in range(8)})
  self.assertGreater(len((json.dumps(self.document,indent=2)+"\n").encode()),observer.MAX_CONFIG)
  with self.assertRaises(ValueError):observer.validated_launch(self.document)
 def test_exact_total_byte_boundary_and_one_extra_byte(self):
  env=self.document["environment"]
  env.update({f"VARIABLE_{i}":"x"*8192 for i in range(7)})
  env["PADDING"]=""
  base=len((json.dumps(self.document,indent=2)+"\n").encode())
  remaining=observer.MAX_CONFIG-base
  self.assertTrue(0<remaining<8192)
  env["PADDING"]="x"*remaining
  self.assertEqual(len((json.dumps(self.document,indent=2)+"\n").encode()),observer.MAX_CONFIG)
  observer.validated_launch(self.document)
  env["PADDING"]+="x"
  with self.assertRaises(ValueError):observer.validated_launch(self.document)
 def test_finite_count_types_original_key_value_loader_and_home_guards_remain(self):
  cases=[{f"VARIABLE_{i}":"x"for i in range(257)}, {"HOME":os.environ["HOME"],"LD_PRELOAD":"/unapproved"}, {"HOME":"/different"}, {"HOME":os.environ["HOME"],"X"*129:"x"}, {"HOME":os.environ["HOME"],"X":"x"*8193}, {"HOME":os.environ["HOME"],"X":123}, {"HOME":os.environ["HOME"],"X":"x\0y"}]
  for env in cases:
   with self.subTest(case=list(env)[:2]):
    self.document["environment"]=env
    with self.assertRaises(ValueError):observer.validated_launch(self.document)

if __name__=="__main__":unittest.main()
