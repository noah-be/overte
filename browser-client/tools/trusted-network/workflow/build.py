#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build/stage only. Profile loading and root-owned installation are separate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat

BASE=Path(__file__).resolve().parents[1]
PREFIX=Path('/usr/libexec/overte-browser-network')
NAMES=('trusted_owner','network_udp','network_route_diagnostics','owner_admission')

def header_array(data):return '{'+','.join(str(v) for v in hashlib.sha256(data).digest())+'}'
def rooted(path):
 path=Path(path).resolve(strict=True)
 for part in (path,*path.parents):
  info=part.stat()
  if info.st_uid!=0 or info.st_mode&0o022:raise ValueError('runtime-package-path-not-root-trusted')
 return str(path)

def trusted_import_paths(python):
 output=subprocess.run([python,'-I','-S','-c','import sys,json;print(json.dumps(sys.path))'],capture_output=True,check=True,timeout=5).stdout
 if len(output)>16384:raise ValueError('python-import-path-bound')
 paths=json.loads(output)
 if type(paths) is not list or not 1<=len(paths)<=8:raise ValueError('python-import-path-count')
 entries=0
 for value in paths:
  if type(value) is not str or not re.fullmatch(r'/usr/lib(?:64)?/python[0-9./a-z-]+(?:\.zip)?',value):raise ValueError('python-import-path-scope')
  path=Path(value)
  if not path.exists():
   if not value.endswith('.zip'):raise ValueError('python-import-path-missing')
   rooted(path.parent);continue
  rooted(path)
  if path.is_dir():
   for parent,dirs,files in os.walk(path,followlinks=False):
    for name in dirs+files:
     entries+=1
     if entries>16384:raise ValueError('python-import-tree-budget')
     child=Path(parent)/name;info=child.lstat()
     if stat.S_ISLNK(info.st_mode):
      # Distro-owned regular-file aliases are safe only when the whole resolved
      # ancestry and target remain root-owned and non-writable. No directory
      # links/cycles or user-owned import targets are accepted.
      if info.st_uid or not child.resolve(strict=True).is_file():raise ValueError('python-import-tree-untrusted')
      rooted(child)
     elif info.st_uid or info.st_mode&0o022 or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):raise ValueError('python-import-tree-untrusted')
  elif not path.is_file():raise ValueError('python-import-root-type')
 return paths

def build(destination,policy,python=None,static_libraries=None):
 destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 if any(destination.iterdir()):raise ValueError('stage-must-be-empty')
 # Policy is operator input, never browser input. Admission validates every use.
 if set(policy)!={'version','hostUID','hostGID','sessionParent','nativeExecutables','nativeReadRoots'} \
   or type(policy['version']) is not int or policy['version']!=1 or type(policy['hostUID']) is not int or not 1<=policy['hostUID']<2**32-1 \
   or type(policy['hostGID']) is not int or not 1<=policy['hostGID']<2**32-1:raise ValueError('policy-header')
 python=rooted(python or '/usr/bin/python3')
 if not re.fullmatch(r'/usr/bin/python3\.\d{1,2}',python):raise ValueError('python-distro-canonical-path')
 if policy['sessionParent'] not in ('/tmp','/run/user/'+str(policy['hostUID'])):raise ValueError('policy-session-parent')
 for key,maximum in (('nativeExecutables',8),('nativeReadRoots',32)):
  values=policy[key]
  if type(values) is not list or not 1<=len(values)<=maximum or any(type(value) is not str for value in values) or len(set(values))!=len(values):raise ValueError('policy-runtime-scope')
  for value in values:
   if type(value) is not str or len(value.encode())>4096 or not value.startswith('/') or value in ('/','/tmp','/home','/root','/etc','/run','/proc','/dev') \
      or '//' in value or any(part in ('.','..') for part in value.split('/')) or any(ord(c)<32 or ord(c)==127 for c in value) \
      or re.search(r'/(?:\.ssh|\.gnupg|\.config|\.cache|\.local)(?:/|$)',value):raise ValueError('policy-runtime-path')
 import_paths=trusted_import_paths(python)
 policy_bytes=(json.dumps(policy,sort_keys=True,separators=(',',':'))+'\n').encode()
 (destination/'policy.json').write_bytes(policy_bytes)
 records=[]
 for name in NAMES:
  data=(BASE/'src'/(name+'.py')).read_bytes()
  (destination/(name+'.py')).write_bytes(data);records.append(data)
 paths=[str(PREFIX/(name+'.py')) for name in NAMES]
 header='#ifndef OVERTE_NATIVE_BOUNDARY\n#define PYTHON_PATH '+json.dumps(python)+'\n'
 header+='static const char *PYTHON_IMPORT_PATHS['+str(len(import_paths))+']='+json.dumps(import_paths).replace('[','{').replace(']','}')+';\n'
 header+='#define PYTHON_IMPORT_COUNT '+str(len(import_paths))+'\n'
 header+='#define POLICY_PATH '+json.dumps(str(PREFIX/'policy.json'))+'\n'
 header+='static const char *OWNER_PATHS[4]='+json.dumps(paths).replace('[','{').replace(']','}')+';\n'
 header+='static const unsigned char OWNER_HASHES[4][32]={'+','.join(header_array(data) for data in records)+'};\n'
 header+='static const unsigned char PYTHON_HASH[32]='+header_array(Path(python).read_bytes())+';\n'
 header+='static const unsigned char POLICY_HASH[32]='+header_array(policy_bytes)+';\n'
 header+='#else\n'
 header+='static const char *NATIVE_EXECUTABLES['+str(len(policy['nativeExecutables']))+']=' + json.dumps(policy['nativeExecutables']).replace('[','{').replace(']','}')+';\n'
 header+='#define NATIVE_EXECUTABLE_COUNT '+str(len(policy['nativeExecutables']))+'\n#endif\n'
 (destination/'image.h').write_text(header)
 linker=['-static']
 if static_libraries is not None:
  archives=Path(static_libraries).resolve(strict=True)
  if not archives.is_dir() or any(not (archives/name).is_file() for name in ('libc.a','libcrypto.a')):raise ValueError('reviewed-static-libraries-required')
  linker+=['-L'+str(archives)]
 subprocess.run(['cc',*linker,'-std=c11','-Wall','-Wextra','-Werror','-O2','-D_FORTIFY_SOURCE=3',
  '-fstack-protector-strong','-Wl,-z,relro,-z,now,-s','-I'+str(destination),
  str(BASE/'src'/'launcher.c'),'-lcrypto','-o',str(destination/'launcher')],check=True,capture_output=True)
 subprocess.run(['cc',*linker,'-std=c11','-Wall','-Wextra','-Werror','-O2','-D_FORTIFY_SOURCE=3',
  '-fstack-protector-strong','-Wl,-z,relro,-z,now,-s','-I'+str(destination),
  str(BASE/'src'/'native-boundary-exec.c'),'-o',str(destination/'native-boundary-exec')],check=True,capture_output=True)
 for name in ('launcher','native-boundary-exec'):
  result=subprocess.run(['/usr/bin/readelf','-lW',str(destination/name)],capture_output=True,check=True,timeout=5)
  if len(result.stdout)>65536 or b'INTERP' in result.stdout:raise ValueError('static-entrypoint-required')
 # Preserve actual Ubuntu-installed interpreter path for its own scoped domain.
 # No wildcard executable, mutable workspace executable or generic Python exec.
 profile='''abi <abi/4.0>,
include <tunables/global>
profile overte-browser-network-setup /usr/libexec/overte-browser-network/launcher flags=(attach_disconnected) {
  capability sys_admin,
  capability net_admin,
  capability setpcap,
  userns,
  network inet,
  network netlink,
  signal,
  / r,
  /usr/ r,
  /usr/bin/ r,
  /usr/libexec/ r,
  /usr/libexec/overte-browser-network/ r,
  /usr/lib/ r,
  /usr/lib64/ r,
  /memfd:overte-trusted-stage* rw,
  /usr/libexec/overte-browser-network/launcher mr,
  /usr/libexec/overte-browser-network/*.py r,
  /usr/libexec/overte-browser-network/policy.json r,
  /usr/lib/** r,
  /usr/lib64/** r,
  /lib/** r,
  /lib64/** r,
  /etc/ld.so.cache r,
  /proc/@{pid}/** rw,
  /proc/sys/kernel/cap_last_cap r,
  '''+policy['sessionParent']+'''/overte-browser-*/native-network.json r,
  '''+python+''' r,
  '''+python+''' Px -> overte-browser-network-owner,
}
profile overte-browser-network-owner flags=(attach_disconnected) {
  audit deny capability,
  userns,
  network,
  unix,
  signal,
  ptrace,
  allow file rwlkm /{**,},
  # Only the fixed reviewed bwrap setup domain may cross the owner boundary.
  /usr/bin/bwrap Px -> bwrap,
}
'''
 # Ubuntu ABI source is pinned; parser/runtime semantics still require live proof.
 (destination/'overte-browser-network').write_text(profile)
 files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir() if p.is_file()}
 manifest={'version':1,'prefix':str(PREFIX),'python':python,'files':files,
  'pythonImportPaths':import_paths,'rootSource':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'src').iterdir() if p.is_file()},
  'activated':False,'actualNamespaceCapabilityRoutingProof':False}
 (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return manifest

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True);parser.add_argument('--policy',required=True);parser.add_argument('--static-libraries')
 args=parser.parse_args();build(args.stage,json.loads(Path(args.policy).read_text()),static_libraries=args.static_libraries)
