#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Explicit reviewed ephemeral setup only; never replace an existing profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

PREFIX=Path('/usr/libexec/overte-browser-network')
PROFILE=Path('/etc/apparmor.d/overte-browser-network')
MODULES={'trusted_owner.py','network_udp.py','network_route_diagnostics.py','owner_admission.py'}
REQUIRED=MODULES|{'launcher','native-boundary-exec','policy.json','overte-browser-network','image.h'}
LIMIT=8*1024*1024

class Refusal(ValueError): pass

def bounded_file(path,maximum=LIMIT):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=maximum:raise Refusal('bundle-file-bound')
  value=os.read(fd,maximum+1)
  after=os.fstat(fd)
  if len(value)!=info.st_size or len(value)>maximum or (info.st_dev,info.st_ino,info.st_size)!=(after.st_dev,after.st_ino,after.st_size):raise Refusal('bundle-file-changed')
  return value
 finally:os.close(fd)

def unique_object(pairs):
 result={}
 for key,value in pairs:
  if key in result:raise Refusal('bundle-duplicate-key')
  result[key]=value
 return result

def verified_bundle(directory,digest):
 directory=Path(directory)
 if directory.resolve(strict=True)!=directory or not directory.is_dir():raise Refusal('bundle-alias')
 if not re.fullmatch('[a-f0-9]{64}',digest):raise Refusal('review-manifest-required')
 manifest_bytes=bounded_file(directory/'manifest.json',65536)
 if hashlib.sha256(manifest_bytes).hexdigest()!=digest:raise Refusal('review-manifest-mismatch')
 manifest=json.loads(manifest_bytes,object_pairs_hook=unique_object)
 if type(manifest) is not dict or set(manifest)!={'version','prefix','python','files','pythonImportPaths','rootSource','activated','actualNamespaceCapabilityRoutingProof'} \
    or type(manifest['version']) is not int or manifest['version']!=1 or manifest['prefix']!=str(PREFIX) \
    or type(manifest['python']) is not str or not re.fullmatch(r'/usr/bin/python3\.[0-9]{1,2}',manifest['python']) \
    or type(manifest['files']) is not dict or set(manifest['files'])!=REQUIRED \
    or manifest['activated'] is not False or manifest['actualNamespaceCapabilityRoutingProof'] is not False:raise Refusal('bundle-manifest-schema')
 if {p.name for p in directory.iterdir()}!=REQUIRED|{'manifest.json'}:raise Refusal('bundle-extra-file')
 result={}
 for name,digest in manifest['files'].items():
  if type(digest) is not str or not re.fullmatch('[a-f0-9]{64}',digest):raise Refusal('bundle-record-hash')
  value=bounded_file(directory/name)
  if hashlib.sha256(value).hexdigest()!=digest:raise Refusal('bundle-hash-mismatch')
  result[name]=value
 # Snapshot all authenticated bytes before any installation mutation.
 return manifest,result

def trusted_directory(path):
 path=Path(path)
 if path.resolve(strict=True)!=path:raise Refusal('install-directory-alias')
 for item in (path,*path.parents):
  info=item.lstat()
  if not stat.S_ISDIR(info.st_mode) or info.st_uid or info.st_mode&0o022:raise Refusal('install-directory-not-root-trusted')

def parse_loaded_profiles(content):
 if type(content) is not str or len(content.encode())>1024*1024:raise Refusal('loaded-profile-size')
 result={}
 for line in content.splitlines():
  match=re.fullmatch(r'(.+) \((enforce|complain|kill|unconfined)\)',line)
  if not match or match[1] in result:raise Refusal('loaded-profile-record')
  result[match[1]]=match[2]
 return result

def loaded_profiles():
 fd=os.open('/sys/kernel/security/apparmor/profiles',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  chunks=[];total=0
  while True:
   value=os.read(fd,min(65536,1024*1024+1-total))
   if not value:break
   chunks.append(value);total+=len(value)
   if total>1024*1024:raise Refusal('loaded-profile-size')
  return parse_loaded_profiles(b''.join(chunks).decode())
 finally:os.close(fd)

def preserve_owned_policy_markers():
    # AppArmor administrative markers name the source file, not its two labels.
    # Preserve disabled/complain state, including a dangling marker symlink.
    for name in ('disable', 'force-complain'):
        directory = PROFILE.parent / name
        if os.path.lexists(directory / PROFILE.name):
            raise Refusal('existing-owned-profile-state-marker-preserved')
        if os.path.lexists(directory):
            trusted_directory(directory)

def verify_python_imports(manifest):
 # Load the reviewed build module locally only in the explicit administrator
 # installer, never under the capability-enabled runtime profile.
 import importlib.util
 spec=importlib.util.spec_from_file_location('trusted_build',Path(__file__).with_name('build.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 if module.trusted_import_paths(manifest['python'])!=manifest['pythonImportPaths']:raise Refusal('python-import-runtime-mismatch')

def install(directory,digest):
 if os.geteuid()!=0:raise Refusal('root-required-for-explicit-install')
 manifest,data=verified_bundle(directory,digest)
 trusted_directory('/usr');trusted_directory('/etc/apparmor.d')
 preserve_owned_policy_markers()
 parser=Path('/usr/sbin/apparmor_parser');python=Path(manifest['python']);bwrap=Path('/usr/bin/bwrap')
 for path in (parser,python,bwrap):
  if path.resolve(strict=True)!=path:raise Refusal('installed-executable-alias')
  trusted_directory(path.parent)
  info=path.lstat()
  if not stat.S_ISREG(info.st_mode) or info.st_uid or info.st_mode&0o6022 or not info.st_mode&stat.S_IXUSR:raise Refusal('installed-executable-not-trusted')
 verify_python_imports(manifest)
 before=loaded_profiles()
 if any(name.startswith('overte-browser-network-') for name in before) or PREFIX.exists() or PREFIX.is_symlink() or PROFILE.exists() or PROFILE.is_symlink():raise Refusal('existing-install-or-profile-preserved')
 if before.get('bwrap')!='enforce' or before.get('unpriv_bwrap')!='enforce':raise Refusal('reviewed-distro-bwrap-profile-required')
 source=Path('/usr/share/apparmor/extra-profiles/bwrap-userns-restrict')
 trusted_directory(source.parent)
 if hashlib.sha256(bounded_file(source,262144)).hexdigest()!='11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9':raise Refusal('reviewed-distro-bwrap-source-mismatch')
 # Explicit no-load parser check BEFORE writes; -a later never replaces policy.
 subprocess.run([str(parser),'-Q','-K','-b','/etc/apparmor.d',str(Path(directory)/'overte-browser-network')],check=True,capture_output=True,timeout=15,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'})
 parent=PREFIX.parent
 if not parent.exists():parent.mkdir(mode=0o755)
 trusted_directory(parent)
 PREFIX.mkdir(mode=0o755);PREFIX.chmod(0o755)
 installed=[]
 try:
  for name,value in data.items():
   if name=='overte-browser-network':continue
   path=PREFIX/name
   fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o755 if name in ('launcher','native-boundary-exec') else 0o644)
   os.fchmod(fd,0o755 if name in ('launcher','native-boundary-exec') else 0o644)
   with os.fdopen(fd,'wb') as stream:stream.write(value);stream.flush();os.fsync(stream.fileno())
   installed.append(path)
   if bounded_file(path)!=value:raise Refusal('installed-byte-verification')
  descriptor=os.open(PROFILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
  os.fchmod(descriptor,0o644)
  with os.fdopen(descriptor,'wb') as stream:stream.write(data['overte-browser-network']);stream.flush();os.fsync(stream.fileno())
  installed.append(PROFILE)
  subprocess.run([str(parser),'-a','-K','-b','/etc/apparmor.d',str(PROFILE)],check=True,capture_output=True,timeout=15,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'})
  after=loaded_profiles()
  if any(after.get(name)!='enforce' for name in ('overte-browser-network-setup','overte-browser-network-owner')):raise Refusal('owned-profile-not-enforcing')
  if any(after.get(name)!=mode for name,mode in before.items()):raise Refusal('existing-profile-changed')
  return {'installed':True,'existingProfilesPreserved':True,'actualRuntimeProof':False}
 except BaseException:
  # Never automatically unload a successfully/partially loaded policy. Preserve
  # files and fail; an administrator can review the owned incomplete install.
  raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--bundle',required=True);parser.add_argument('--manifest-sha256',required=True)
 args=parser.parse_args()
 try:print(json.dumps(install(args.bundle,args.manifest_sha256)))
 except (Refusal,OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
  print(json.dumps({'installed':False,'category':'trusted-network-install-refused','existingProfileReplacement':False}));raise SystemExit(1)
