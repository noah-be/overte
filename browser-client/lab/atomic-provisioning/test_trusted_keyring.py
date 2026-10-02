# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Real cached trust bytes plus authored parser/security negative controls."""
import contextlib,hashlib,io,json,lzma,os,stat,subprocess,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import stage,trusted_keyring as k
KEYRING=Path(os.environ['ATOMIC_DIAGNOSTIC_TEST_KEYRING'])
CACHE=Path(os.environ['ATOMIC_DIAGNOSTIC_CACHE'])

def ar(rows,slash=False):
 out=bytearray(b'!<arch>\n')
 for name,data in rows:
  encoded=(name+('/'if slash else'')).encode()
  out.extend(encoded.ljust(16,b' ')+b'0'.ljust(12,b' ')+b'0'.ljust(6,b' ')+b'0'.ljust(6,b' ')+b'100644'.ljust(8,b' ')+str(len(data)).encode().ljust(10,b' ')+b'`\n'+data)
  if len(data)%2:out.extend(b'\n')
 return bytes(out)

def tar(data,*,kind=tarfile.REGTYPE,duplicate=False,name=None):
 out=io.BytesIO()
 with tarfile.open(fileobj=out,mode='w:')as archive:
  for _ in range(2 if duplicate else 1):
   member=tarfile.TarInfo(name or k.spec()['memberName']);member.type=kind;member.size=len(data)if kind==tarfile.REGTYPE else 0;member.linkname='untrusted-link';archive.addfile(member,io.BytesIO(data)if member.size else None)
 return out.getvalue()

class TrustedKeyring(unittest.TestCase):
 def setUp(self):self.record=k.spec();self.key=stage.regular(KEYRING);self.assertEqual(len(self.key),3607);self.assertEqual(stage.digest(self.key),self.record['memberSHA256'])
 def test_pinned_package_record_is_exact_signed_cached_noble_index_member(self):
  text=lzma.decompress(stage.regular(CACHE/'Packages.xz')).decode();blocks=[b for b in text.split('\n\n')if b.startswith('Package: ubuntu-keyring\n')];self.assertEqual(len(blocks),1);fields=dict(line.split(': ',1)for line in blocks[0].splitlines()if ': 'in line and not line.startswith(' '));self.assertEqual(fields['Version'],self.record['version']);self.assertEqual(fields['Architecture'],'all');self.assertEqual(fields['SHA256'],self.record['packageSHA256']);self.assertEqual(int(fields['Size']),11124);self.assertEqual(self.record['packageURL'],'https://archive.ubuntu.com/ubuntu/'+fields['Filename'])
 def test_debian_bare_names_and_gnu_suffix_decode_same_exact_layout(self):
  rows=[('debian-binary',b'2.0\n'),('control.tar.xz',b'x'),('data.tar.xz',b'y')]
  for slash in(False,True):self.assertEqual(k.deb_data(ar(rows,slash)),(b'data.tar.xz',b'y'))
 def test_special_paths_bad_layout_header_padding_and_limit_refused(self):
  good=ar([('debian-binary',b'2.0\n'),('control.tar.xz',b'x'),('data.tar.xz',b'y')])
  bad=[b'',good+b'x',b'!<arch>\n'+b' '*60,good[:-1]+b'x',b'x'*11125,ar([('debian-binary',b'2.0\n'),('../control',b'x'),('data.tar.xz',b'y')]),ar([('debian-binary',b'3.0\n'),('control.tar.xz',b'x'),('data.tar.xz',b'y')])]
  for data in bad:
   with self.assertRaises(ValueError):k.deb_data(data)
 def test_member_exact_digest_and_no_tree_or_link_extraction(self):
  self.assertEqual(k.verified_member(tar(self.key),self.record),self.key)
  for data in(tar(self.key,kind=tarfile.SYMTYPE),tar(self.key,duplicate=True),tar(self.key,name='../archive-keyring.gpg'),tar(b'changed'),tar(self.key[:-1])):
   with self.assertRaises(ValueError):k.verified_member(data,self.record)
 def test_decode_bounds_trailing_archive_and_unknown_format(self):
  self.assertEqual(k.decoded_data(b'data.tar.xz',lzma.compress(b'valid')),b'valid')
  for payload in(lzma.compress(b'x'*(k.MAX_TAR+1)),lzma.compress(b'valid')+b'trailing'):
   with self.assertRaises(ValueError):k.decoded_data(b'data.tar.xz',payload)
  with self.assertRaises(ValueError):k.decoded_data(b'data.tar.untrusted',b'unknown')
 def test_package_authentication_precedes_parse_and_every_write(self):
  with tempfile.TemporaryDirectory()as temp,patch.object(k,'deb_data')as parser,patch.object(k,'locked_write')as writer:
   phases=[]
   with self.assertRaisesRegex(ValueError,'package-digest-refused'):k.provision(temp,lambda _:b'changed',progress=phases.append)
   self.assertEqual(phases[-1],'download-digests');parser.assert_not_called();writer.assert_not_called();self.assertEqual(list(Path(temp).iterdir()),[])
 def test_locked_exact_key_is_owned_single_link_private_and_original_unchanged(self):
  initial=KEYRING.stat();original=KEYRING.read_bytes()
  with tempfile.TemporaryDirectory()as temp:
   result=k.locked_write(temp,self.key,self.record);s=result.stat();self.assertEqual(s.st_uid,os.getuid());self.assertEqual(s.st_nlink,1);self.assertEqual(stat.S_IMODE(s.st_mode),0o600);self.assertEqual(result.read_bytes(),self.key)
   with self.assertRaises(FileExistsError):k.locked_write(temp,self.key,self.record)
  self.assertEqual(KEYRING.read_bytes(),original);self.assertEqual(KEYRING.stat().st_mode,initial.st_mode)
 def test_public_or_symlink_directory_preexisting_fifo_and_modified_key_refused(self):
  with tempfile.TemporaryDirectory()as temp:
   root=Path(temp);public=root/'public';public.mkdir(mode=0o755)
   with self.assertRaises(ValueError):k.locked_write(public,self.key,self.record)
   link=root/'alias';link.symlink_to(root,target_is_directory=True)
   with self.assertRaises(OSError):k.locked_write(link,self.key,self.record)
   os.mkfifo(root/k.NAME,0o600)
   with self.assertRaises(FileExistsError):k.locked_write(root,self.key,self.record)
   with self.assertRaises(ValueError):k.locked_write(root,b'changed',self.record)
 def test_exact_record_and_member_pin_no_extra_keys_boolean_schema_or_foreign_url(self):
  for changes in({'schemaVersion':True},{'packageURL':'https://example.invalid/package'},{'memberSHA256':'f'*64},{'extra':'private'}):
   record={**self.record,**changes}
   with patch.object(k.stage,'regular',side_effect=lambda path,*a,**kw:json.dumps(record).encode()if Path(path).name=='keyring-bootstrap.json'else json.dumps({'keyringSHA256':self.record['memberSHA256']}).encode()):
    with self.assertRaises(ValueError):k.spec()
 def test_official_download_is_no_redirect_exact_bound_and_timeout(self):
  response=contextlib.nullcontext();response.enter_result=response;response.geturl=lambda:self.record['packageURL'];calls=[];response.read=lambda n:calls.append(n)or b'x'*11125
  with patch.object(k.stage.urllib.request,'build_opener')as opener:
   opener.return_value.open.return_value=response
   with self.assertRaises(ValueError):k.download_package(self.record['packageURL'])
   self.assertEqual(calls,[11125]);opener.return_value.open.assert_called_once_with(self.record['packageURL'],timeout=15)
  self.assertIsNone(k.NoRedirect().redirect_request(None,None,302,'private',{},'https://example.invalid'))
 def test_main_source_and_fork_failure_precedes_provision(self):
  with patch.dict(os.environ,{'PROBE_SOURCE_SHA':'a'*40,'GITHUB_REPOSITORY':'untrusted/repo'},clear=True),patch.object(k.subprocess,'check_output',return_value='a'*40+'\n'),patch.object(k,'provision')as provision:
   with self.assertRaises(ValueError):k.main()
   provision.assert_not_called()
 def test_main_private_trust_input_export_only_after_locked_creation(self):
  with tempfile.TemporaryDirectory()as temp:
   env=Path(temp)/'env';env.write_bytes(b'');env.chmod(0o600)
   with patch.dict(os.environ,{'PROBE_SOURCE_SHA':'a'*40,'GITHUB_REPOSITORY':'noah-be/overte','RUNNER_TEMP':temp,'GITHUB_ENV':str(env)},clear=True),patch.object(k.subprocess,'check_output',return_value='a'*40+'\n'),patch.object(k,'provision',side_effect=lambda directory,**kw:k.locked_write(directory,self.key,self.record)):
    k.main()
   lines=env.read_text().splitlines();self.assertEqual(len(lines),1);name,value=lines[0].split('=',1);self.assertEqual(name,'ATOMIC_REVIEWED_KEYRING');result=Path(value);self.assertEqual(stat.S_IMODE(result.parent.stat().st_mode),0o700);self.assertEqual(stage.regular(result,private=True),self.key)
 def test_safe_cli_failure_never_reflects_exception_or_private_paths(self):
  out=io.StringIO();err=io.StringIO()
  with patch.object(k,'main',side_effect=ValueError('PRIVATE_URL_SECRET')),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):self.assertEqual(k.run(),1)
  self.assertNotIn('PRIVATE',out.getvalue()+err.getvalue());self.assertEqual(json.loads(out.getvalue())['scope'],'owned-atomic-trusted-keyring-bootstrap')
 def test_stage_main_owned_snapshot_keeps_original_cached_signature_chain(self):
  record=json.loads((stage.HERE/'dependency.json').read_text());mapping={record['releaseURL']:CACHE/'InRelease','https://archive.ubuntu.com/ubuntu/dists/noble/'+record['packagesPath']:CACHE/'Packages.xz',record['packageURL']:CACHE/'strace.deb'};original=stage.signed_dependency;actual=stage.subprocess.check_output
  with tempfile.TemporaryDirectory()as temp:
   root=Path(temp);source=root/'reviewed.gpg';stage.write(source,self.key);env=root/'env';stage.write(env,b'');observed=[]
   def dependency(directory,keyring,*,progress):
    self.assertNotEqual(Path(keyring),source);self.assertEqual(stage.regular(keyring,private=True),self.key);observed.append(keyring);return original(directory,keyring,lambda url:mapping[url].read_bytes(),progress=progress)
   with patch.dict(os.environ,{'PROBE_SOURCE_SHA':'a'*40,'GITHUB_REPOSITORY':'noah-be/overte','RUNNER_TEMP':temp,'GITHUB_ENV':str(env),'ATOMIC_REVIEWED_KEYRING':str(source)},clear=True),patch.object(stage.subprocess,'check_output',wraps=stage.subprocess.check_output)as output,patch.object(stage,'signed_dependency',side_effect=dependency):
    output.side_effect=lambda argv,**kw:'a'*40+'\n'if argv[0]=='git'else actual(argv,**kw);stage.main()
   self.assertEqual(len(observed),1);self.assertIn('ATOMIC_PROBE_DIRECTORY=',env.read_text())
 def test_stage_main_refuses_modified_writable_symlink_hardlink_before_signature(self):
  with tempfile.TemporaryDirectory()as temp:
   root=Path(temp);valid=root/'key';stage.write(valid,self.key);bad=root/'bad';stage.write(bad,b'changed');writable=root/'writable';stage.write(writable,self.key,0o666);alias=root/'alias';alias.symlink_to(valid);linked=root/'linked';stage.write(linked,self.key);os.link(linked,root/'otherlink');env=root/'env';stage.write(env,b'')
   for path in(bad,writable,alias,linked):
    with patch.dict(os.environ,{'PROBE_SOURCE_SHA':'a'*40,'GITHUB_REPOSITORY':'noah-be/overte','RUNNER_TEMP':temp,'GITHUB_ENV':str(env),'ATOMIC_REVIEWED_KEYRING':str(path)},clear=True),patch.object(stage.subprocess,'check_output',return_value='a'*40+'\n'),patch.object(stage,'signed_dependency')as dependency:
     with self.assertRaises((ValueError,OSError)):stage.main()
     dependency.assert_not_called()

if __name__=='__main__':unittest.main()
