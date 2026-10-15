# SPDX-License-Identifier: Apache-2.0
"""Private public-proof staging controls; no host writes or actual network."""
import contextlib,hashlib,importlib.util,io,json,os,ssl,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
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

class DownloadRecovery(unittest.TestCase):
 def setUp(self):
  self.data=b'authored-public-proof'
  self.row=(next(iter(P.INPUTS.values()))[0],len(self.data),hashlib.sha256(self.data).hexdigest())
  self.pins=patch.object(P,'INPUTS',{'InRelease':self.row});self.pins.start();self.addCleanup(self.pins.stop)
  opener_patch=patch.object(P.urllib.request,'build_opener');self.opener=opener_patch.start();self.addCleanup(opener_patch.stop)
  sleep_patch=patch.object(P.time,'sleep');self.sleep=sleep_patch.start();self.addCleanup(sleep_patch.stop)
 def response(self,*,data=None,url=None):
  response=MagicMock();response.status=200;response.geturl.return_value=url or self.row[0]
  response.read.return_value=self.data if data is None else data
  response.__enter__.return_value=response
  return response
 def http_error(self,status):
  return P.urllib.error.HTTPError('https://private.invalid/token',status,'private diagnostic',{},io.BytesIO(b'private body'))
 def test_transient_http_recovery_keeps_original_pins_and_reads_bound(self):
  errors=[self.http_error(500),self.http_error(503)];response=self.response()
  self.opener.return_value.open.side_effect=[*errors,response]
  self.assertEqual(P.download(*self.row),self.data)
  self.assertEqual(self.opener.return_value.open.call_args_list,[unittest.mock.call(self.row[0],timeout=15)]*3)
  self.assertEqual(self.sleep.call_args_list,[unittest.mock.call(1),unittest.mock.call(2)])
  response.read.assert_called_once_with(len(self.data)+1)
  for error in errors:self.assertTrue(error.fp.closed)
 def test_each_permitted_transient_status_can_recover(self):
  for status in [408,429,500,502,503,504]:
   with self.subTest(status=status):
    self.opener.return_value.open.reset_mock();self.sleep.reset_mock()
    error=self.http_error(status);self.opener.return_value.open.side_effect=[error,self.response()]
    self.assertEqual(P.download(*self.row),self.data)
    self.assertEqual(self.opener.return_value.open.call_count,2);self.sleep.assert_called_once_with(1);self.assertTrue(error.fp.closed)
 def test_exhausted_preparation_creates_no_partial_cache(self):
  self.opener.return_value.open.side_effect=self.http_error(503)
  with tempfile.TemporaryDirectory()as folder:
   output=Path(folder)/'cache'
   with self.assertRaises(P.DownloadFailure):P.prepare(output)
   self.assertFalse(output.exists());self.assertEqual(self.opener.return_value.open.call_count,3)
 def test_transient_http_exhaustion_is_bounded_and_reports_only_fixed_fields(self):
  errors=[self.http_error(503)for _ in range(3)];self.opener.return_value.open.side_effect=errors
  with self.assertRaises(P.DownloadFailure)as caught:P.download(*self.row)
  self.assertEqual(caught.exception.details,{'phase':'download','reason':'http-status','attempts':3,'httpStatus':503})
  self.assertEqual(self.opener.return_value.open.call_count,3);self.assertEqual(self.sleep.call_count,2)
  for error in errors:self.assertTrue(error.fp.closed)
 def test_timeout_and_connection_recover_but_only_after_original_bytes_verify(self):
  self.opener.return_value.open.side_effect=[TimeoutError('private timeout'),P.urllib.error.URLError(ConnectionResetError('private reset')),self.response()]
  self.assertEqual(P.download(*self.row),self.data);self.assertEqual(self.sleep.call_count,2)
 def test_network_exhaustion_is_bounded(self):
  self.opener.return_value.open.side_effect=P.urllib.error.URLError('private DNS detail')
  with self.assertRaises(P.DownloadFailure)as caught:P.download(*self.row)
  self.assertEqual(caught.exception.details,{'phase':'download','reason':'network','attempts':3})
  self.assertEqual(self.opener.return_value.open.call_count,3);self.assertEqual(self.sleep.call_count,2)
 def test_redirect_and_nontransient_http_refuse_without_retry(self):
  for status in [301,302,307,308,400,401,403,404,410]:
   with self.subTest(status=status):
    self.opener.return_value.open.reset_mock();self.sleep.reset_mock();error=self.http_error(status)
    self.opener.return_value.open.side_effect=error
    with self.assertRaises(P.DownloadFailure)as caught:P.download(*self.row)
    self.assertEqual(caught.exception.details['httpStatus'],status)
    self.opener.return_value.open.assert_called_once();self.sleep.assert_not_called();self.assertTrue(error.fp.closed)
 def test_tls_trust_failure_refuses_without_retry(self):
  self.opener.return_value.open.side_effect=P.urllib.error.URLError(ssl.SSLCertVerificationError('private cert detail'))
  with self.assertRaises(P.DownloadFailure):P.download(*self.row)
  self.opener.return_value.open.assert_called_once();self.sleep.assert_not_called()
 def test_changed_digest_oversize_or_response_url_refuse_without_retry(self):
  for response in [self.response(data=b'x'*len(self.data)),self.response(data=self.data+b'x'),self.response(url='https://foreign.invalid/')]:
   with self.subTest(response=response):
    self.opener.return_value.open.reset_mock();self.sleep.reset_mock();self.opener.return_value.open.side_effect=None
    self.opener.return_value.open.return_value=response
    with self.assertRaises(P.DownloadFailure):P.download(*self.row)
    self.opener.return_value.open.assert_called_once();self.sleep.assert_not_called()
 def test_cli_redacts_raw_exception_paths_urls_and_response_bodies(self):
  for error,details in [(P.DownloadFailure('http-status',3,503),{'phase':'download','reason':'http-status','attempts':3,'httpStatus':503}),(ValueError('/private/path?token=secret'),None)]:
   with self.subTest(error=type(error).__name__),patch.object(P.sys,'argv',['prepare','--output','/private/output']),patch.object(P,'prepare',side_effect=error):
    output=io.StringIO()
    with contextlib.redirect_stdout(output):self.assertEqual(P.main(),1)
    result=json.loads(output.getvalue());self.assertFalse(result['completed']);self.assertEqual(result['category'],'pinned-input-preparation-refused')
    self.assertEqual(result.get('failure'),details)
    for private in ['private','token','secret','Traceback']:self.assertNotIn(private,output.getvalue())

if __name__=='__main__':unittest.main()
