# SPDX-License-Identifier: Apache-2.0
"""Private public-proof staging controls; no host writes or actual network."""
import hashlib,importlib.util,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_signed_proof',BASE/'workflow/prepare_signed_library.py')
P=importlib.util.module_from_spec(spec)
# The script's ordinary local import is pinned by its own reviewed source dir.
import sys
sys.path.insert(0,str(BASE/'workflow'))
try:spec.loader.exec_module(P)
finally:sys.path.pop(0)

class PublicProofs(unittest.TestCase):
 def test_exact_same_fd_bytes_and_hash_then_changed_writable_symlink_and_hardlink_refuse(self):
  with tempfile.TemporaryDirectory()as folder:
   path=Path(folder)/'data';data=b'authored-public-input';digest=hashlib.sha256(data).hexdigest();path.write_bytes(data);path.chmod(0o600)
   self.assertEqual(P.source_bytes(path,len(data),digest),data)
   path.chmod(0o777)
   with self.assertRaises(ValueError):P.source_bytes(path,len(data),digest)
   path.chmod(0o600);path.write_bytes(b'x'*len(data))
   with self.assertRaises(ValueError):P.source_bytes(path,len(data),digest)
   path.write_bytes(data);other=Path(folder)/'other';os.link(path,other)
   with self.assertRaises(ValueError):P.source_bytes(path,len(data),digest)
   other.unlink();other.symlink_to(path)
   with self.assertRaises(OSError):P.source_bytes(other,len(data),digest)
 def test_no_arbitrary_url_size_digest_or_redirect_hook(self):
  with patch.object(P.urllib.request,'build_opener')as opened:
   with self.assertRaises(ValueError):P.download('https://example.invalid/key',1,'a'*64)
   url,size,digest=next(iter(P.INPUTS.values()))
   with self.assertRaises(ValueError):P.download(url,size+1,digest)
   opened.assert_not_called()
  self.assertIsNone(P.NoRedirect().redirect_request(None,None,302,None,None,'https://example.invalid'))
 def test_source_copy_identity_changed_after_read_refuses(self):
  with tempfile.TemporaryDirectory()as folder:
   path=Path(folder)/'data';data=b'public-proof';path.write_bytes(data);path.chmod(0o600);original=os.fstat;calls=0
   def changed(fd):
    nonlocal calls
    value=original(fd);calls+=1
    if calls==2:
     fields=list(value);fields[4]=value.st_uid+1;return os.stat_result(fields)
    return value
   with patch.object(P.os,'fstat',side_effect=changed),self.assertRaises(ValueError):P.source_bytes(path,len(data),hashlib.sha256(data).hexdigest())
 def test_keyring_or_source_pair_failure_precedes_any_output_mutation(self):
  with tempfile.TemporaryDirectory()as folder:
   path=Path(folder)/'cache'
   with self.assertRaises(ValueError):P.prepare(path,source_cache='cache')
   self.assertFalse(path.exists())
   with patch.object(P,'keyring_member',return_value=b'invalid'):
    with self.assertRaises(ValueError):P.prepare(path,fetch=lambda *_:b'public')
   self.assertFalse(path.exists())
 def test_authored_write_fds_private_exclusive_all_bytes_and_auth_before_success(self):
  # Only proof-input/signature boundaries are authored here; the ACTUAL
  # production output directory/FD/write/fsync/owner/mode checks are exercised.
  key=b'k'*3607;fake={name:b'authored-'+name.encode()for name in P.INPUTS};expected_hash=hashlib.sha256(key).hexdigest()
  records={name:(row[0],len(fake[name]),hashlib.sha256(fake[name]).hexdigest())for name,row in P.INPUTS.items()}
  with tempfile.TemporaryDirectory()as folder,patch.object(P,'INPUTS',records),patch.dict(P.library.PIN,{'keyringSHA256':expected_hash}),patch.object(P,'keyring_member',return_value=key),patch.object(P.library,'authenticate_cache',return_value=P.library.PIN)as signature:
   output=Path(folder)/'cache'
   def fetch(url,size,digest):
    for name,row in P.INPUTS.items():
     if url==row[0]:return fake[name]
    return b'authored-keyring-package'
   result=P.prepare(output,fetch=fetch)
   self.assertTrue(result['completed']);self.assertFalse(result['hostInstalledBytesCompared']);self.assertFalse(result['systemPackagesModified'])
   self.assertEqual(stat.S_IMODE(output.stat().st_mode),0o700)
   self.assertEqual({p.name for p in output.iterdir()},set(fake)|{'archive-keyring.gpg'})
   for name,data in dict(fake,**{'archive-keyring.gpg':key}).items():
    path=output/name;self.assertEqual(path.read_bytes(),data);self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600);self.assertEqual(path.stat().st_uid,os.getuid());self.assertEqual(path.stat().st_nlink,1)
   signature.assert_called_once_with(output,output/'archive-keyring.gpg')
   with self.assertRaises(FileExistsError):P.prepare(output,fetch=fetch)
 def test_no_host_keyring_or_package_script_installation_and_snapshot_scope_fixed(self):
  source=(BASE/'workflow/prepare_signed_library.py').read_text()
  self.assertNotIn('/usr/share/keyrings',source.split('def keyring_member',1)[0])
  self.assertNotIn('apt-get',source);self.assertNotIn('dpkg -i',source);self.assertNotIn('extractall',source)
  for name,(url,size,digest)in P.INPUTS.items():
   self.assertTrue(url.startswith('https://snapshot.ubuntu.com/ubuntu/20261002T063000Z/'));self.assertLessEqual(size,4*1024*1024);self.assertRegex(digest,'^[0-9a-f]{64}$')

if __name__=='__main__':unittest.main()
