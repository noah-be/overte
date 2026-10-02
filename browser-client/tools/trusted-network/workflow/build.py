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
from contextlib import contextmanager
from contextvars import ContextVar

BASE=Path(__file__).resolve().parents[1]
PREFIX=Path('/usr/libexec/overte-browser-network')
NAMES=('trusted_owner','network_udp','network_route_diagnostics','owner_admission')
MAX_ALIAS_TARGETS=64
MAX_ALIAS_LINKS=128
MAX_ALIAS_BYTES=4*1024*1024
MAX_ALIAS_TOTAL_BYTES=16*1024*1024
MAX_ALIAS_READ_BYTES=32*1024*1024
MAX_ALIAS_PATH_BYTES=16*1024

_exception_add_note=getattr(BaseException,'add_note',None)
_trust_location=ContextVar('reviewed-trust-location',default=('runtime-package',0))
_TRUST_CATEGORIES=frozenset(('runtime-package-path-not-root-trusted','python-import-alias-chain-untrusted','python-import-alias-target-untrusted','python-import-tree-untrusted'))
_TRUST_KINDS=frozenset(('runtime-package','python-executable','import-root','import-alias','import-tree'))
class TrustRefusal(ValueError):
 def __init__(self,category,info=None,ancestor=0,alias_target=None):
  if type(category)is not str or category not in _TRUST_CATEGORIES:raise ValueError('invalid-trust-diagnostic-category')
  super().__init__(category);kind,ordinal=_trust_location.get()
  if type(kind)is not str or kind not in _TRUST_KINDS or type(ordinal) is not int or not 0<=ordinal<=16384:kind,ordinal='runtime-package',0
  metadata=None
  # Only a genuine immutable OS stat result is projected. Do not evaluate a
  # hostile property/getter to improve a failure diagnostic.
  if type(info) is os.stat_result:
   mode=info.st_mode;kind_value='regular'if stat.S_ISREG(mode)else'directory'if stat.S_ISDIR(mode)else'symlink'if stat.S_ISLNK(mode)else'other'
   metadata={'fileType':kind_value,'rootOwned':info.st_uid==0,'groupOrOtherWritable':bool(mode&0o022),'permissions':mode&0o7777,'aliasSizeWithinBound':0<=info.st_size<=MAX_ALIAS_BYTES,
    'boundedBytes':max(0,min(info.st_size,MAX_ALIAS_BYTES+1)),'sizeTruncated':info.st_size<0 or info.st_size>MAX_ALIAS_BYTES+1}
  self.projection={'version':1,'category':category,'entryKind':kind,'entryOrdinal':ordinal,'ancestorOrdinal':max(0,min(ancestor,4096))if type(ancestor)is int else 0,'metadata':metadata,
   'metadataSHA256':hashlib.sha256(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()).hexdigest()if metadata is not None else None}
  # Preserve category/args/exception identity while unittest prints only the
  # already validated fixed projection after its original traceback. No paths.
  if alias_target is not None:
   if not valid_alias_target_class(alias_target):raise ValueError('invalid-alias-target-diagnostic')
   self.projection['aliasTargetClass']=dict(alias_target)
  if _exception_add_note is not None:_exception_add_note(self,'TRUSTED_NETWORK_FAILURE:'+json.dumps(self.projection,sort_keys=True,separators=(',',':')))
# Diagnostic names only: no byte probe, package-authentication claim or grant.
# CPython v3.12.3 configure.ac names LIBRARY and Linux INSTSONAME this way.
_ALIAS_NAMES={'libpython3.12.a':'python312-static-library-name','libpython3.12.so.1.0':'python312-shared-library-name'}
_ALIAS_DIRECTORY_CLASSES=frozenset(('python312-config-directory','usr-library-directory','other-reviewed-directory'))
def alias_target_class(value):
 name=Path(value).name
 parent=Path(value).parent
 directory='python312-config-directory'if re.fullmatch(r'/usr/lib/python3\.12/config-3\.12-[a-z0-9_-]{1,64}',str(parent))else'usr-library-directory'if re.fullmatch(r'/usr/lib(?:64)?(?:/[a-z0-9_-]{1,64})?',str(parent))else'other-reviewed-directory'
 return {'nameClass':_ALIAS_NAMES.get(name,'unknown-name'),'directoryClass':directory,'evidence':'canonical-name-only-no-byte-read'}
def valid_alias_target_class(value):
 return type(value)is dict and set(value)=={'nameClass','directoryClass','evidence'} and type(value['nameClass'])is str and value['nameClass']in ('unknown-name',*_ALIAS_NAMES.values()) and type(value['directoryClass'])is str and value['directoryClass']in _ALIAS_DIRECTORY_CLASSES and type(value['evidence'])is str and value['evidence']=='canonical-name-only-no-byte-read'
@contextmanager
def trust_location(kind,ordinal):
 if type(kind)is not str or kind not in _TRUST_KINDS or type(ordinal)is not int or not 0<=ordinal<=16384:raise ValueError('invalid-trust-diagnostic-location')
 token=_trust_location.set((kind,ordinal))
 try:yield
 finally:_trust_location.reset(token)
def staging_failure(error):
 if type(error)is TrustRefusal:
  fields=vars(error).get('projection')
  required={'version','category','entryKind','entryOrdinal','ancestorOrdinal','metadata','metadataSHA256'}
  if type(fields)is dict and (set(fields)==required or set(fields)==required|{'aliasTargetClass'}) and ('aliasTargetClass'not in fields or valid_alias_target_class(fields['aliasTargetClass'])) and type(fields['version'])is int and fields['version']==1 and type(fields['category'])is str and fields['category']in _TRUST_CATEGORIES and type(fields['entryKind'])is str and fields['entryKind']in _TRUST_KINDS \
    and type(fields['entryOrdinal'])is int and 0<=fields['entryOrdinal']<=16384 and type(fields['ancestorOrdinal'])is int and 0<=fields['ancestorOrdinal']<=4096:
   metadata=fields['metadata'];valid=metadata is None
   if type(metadata)is dict and set(metadata)=={'fileType','rootOwned','groupOrOtherWritable','permissions','aliasSizeWithinBound','boundedBytes','sizeTruncated'}:
    valid=type(metadata['fileType'])is str and metadata['fileType']in ('regular','directory','symlink','other') and all(type(metadata[key])is bool for key in ('rootOwned','groupOrOtherWritable','aliasSizeWithinBound','sizeTruncated')) \
      and type(metadata['permissions'])is int and 0<=metadata['permissions']<=0o7777 and type(metadata['boundedBytes'])is int and 0<=metadata['boundedBytes']<=MAX_ALIAS_BYTES+1
   if valid:
    projected={key:fields[key]for key in ('version','category','entryKind','entryOrdinal','ancestorOrdinal')};projected['metadata']=dict(metadata)if metadata is not None else None
    projected['metadataSHA256']=hashlib.sha256(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()).hexdigest()if metadata is not None else None
    if 'aliasTargetClass'in fields:projected['aliasTargetClass']=dict(fields['aliasTargetClass'])
    return projected
 # No arbitrary exception text, URL/path, argument, username or environment is
 # reflected. errno is read only from a genuine built-in OS exception class.
 number=error.errno if type(error)in (OSError,PermissionError,FileNotFoundError,NotADirectoryError,IsADirectoryError,BlockingIOError,TimeoutError,ConnectionError,ConnectionRefusedError,BrokenPipeError)else None
 return {'version':1,'category':'trusted-network-build-refused','errnoObserved':number if type(number)is int and 0<=number<=4095 else None}

def header_array(data):return '{'+','.join(str(v) for v in hashlib.sha256(data).digest())+'}'
def rooted(path):
 path=Path(path).resolve(strict=True)
 for ancestor,part in enumerate((path,*path.parents)):
  info=part.stat()
  if info.st_uid!=0 or info.st_mode&0o022:raise TrustRefusal('runtime-package-path-not-root-trusted',info,ancestor)
 return str(path)

def alias_path_shape(value):
 # Exact literal policy only. A reviewed distro alias is discovered from the
 # fixed isolated interpreter import tree, never operator/browser argv input.
 if type(value) is not str or not 1<len(value)<=4096 or not re.fullmatch(r'/(?:usr|etc)/[A-Za-z0-9._+@= /-]+',value) \
   or '//' in value or value.endswith('/') or any(part in ('.','..') for part in value.split('/')) or len(Path(value).parts)>33:raise ValueError('python-import-alias-path')
 return value

def rooted_alias(path):
 # Validate every lexical symlink hop/ancestor, not just the final canonical
 # regular file. Link modes are conventionally0777; their owner and immutable
 # parent directory are what prevents an unprivileged link replacement.
 path=os.path.normpath(str(path));hops=0
 while True:
  parts=Path(path).parts;current=Path(parts[0]);restart=False
  info=current.lstat()
  if info.st_uid or info.st_mode&0o022 or not stat.S_ISDIR(info.st_mode):raise TrustRefusal('python-import-alias-chain-untrusted',info,0)
  for index,part in enumerate(parts[1:]):
   current=current/part;info=current.lstat();last=index==len(parts)-2
   if info.st_uid:raise TrustRefusal('python-import-alias-chain-untrusted',info,index+1)
   if stat.S_ISLNK(info.st_mode):
    hops+=1
    if hops>40:raise ValueError('python-import-alias-chain-bound')
    target=os.readlink(current)
    if not target or len(os.fsencode(target))>4096:raise ValueError('python-import-alias-chain-bound')
    next_path=Path(target) if os.path.isabs(target) else current.parent/target
    path=os.path.normpath(str(next_path.joinpath(*parts[index+2:])))
    restart=True;break
   if info.st_mode&0o022 or (not stat.S_ISREG(info.st_mode) if last else not stat.S_ISDIR(info.st_mode)):raise TrustRefusal('python-import-alias-chain-untrusted',info,index+1)
  if not restart:return alias_path_shape(str(current))

def alias_record(path):
 value=alias_path_shape(rooted(path));fd=os.open(value,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
 try:
  before=os.fstat(fd)
  if not stat.S_ISREG(before.st_mode) or before.st_uid or before.st_mode&0o022 or not 0<=before.st_size<=MAX_ALIAS_BYTES:raise TrustRefusal('python-import-alias-target-untrusted',before,alias_target=alias_target_class(value))
  digest=hashlib.sha256();total=0
  while True:
   chunk=os.read(fd,min(65536,MAX_ALIAS_BYTES+1-total))
   if not chunk:break
   total+=len(chunk)
   if total>MAX_ALIAS_BYTES:raise ValueError('python-import-alias-target-bound')
   digest.update(chunk)
  after=os.fstat(fd)
  identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
  if total!=before.st_size or identity(before)!=identity(after):raise ValueError('python-import-alias-target-changed')
  return {'path':value,'bytes':total,'sha256':digest.hexdigest()}
 finally:os.close(fd)

def validate_alias_records(records):
 if type(records) is not list or len(records)>MAX_ALIAS_TARGETS:raise ValueError('python-import-alias-target-count')
 previous='';total=0;path_bytes=0
 for record in records:
  if type(record) is not dict or set(record)!={'path','bytes','sha256'}:raise ValueError('python-import-alias-record')
  path=alias_path_shape(record['path'])
  if path<=previous or type(record['bytes']) is not int or not 0<=record['bytes']<=MAX_ALIAS_BYTES or type(record['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',record['sha256']):raise ValueError('python-import-alias-record')
  previous=path;total+=record['bytes'];path_bytes+=len(path.encode('ascii'))
  if total>MAX_ALIAS_TOTAL_BYTES:raise ValueError('python-import-alias-total-bound')
  if path_bytes>MAX_ALIAS_PATH_BYTES:raise ValueError('python-import-alias-path-bound')
 return records

def alias_read_rules(records):
 validate_alias_records(records);directories=set()
 for record in records:
  for ancestor in Path(record['path']).parents:
   if str(ancestor) not in ('/','/usr','/usr/lib','/usr/lib64'):directories.add(str(ancestor)+'/')
 # Quoted ASCII literals cannot introduce AppArmor globs, variables, escapes,
 # execution, writable rules or capability grants. Directory reads are exact.
 return ''.join('  '+json.dumps(value)+' r,\n' for value in sorted(directories))+''.join('  '+json.dumps(record['path'])+' r,\n' for record in records)

def trusted_import_paths(python,*,aliases=None):
 output=subprocess.run([python,'-I','-S','-c','import sys,json;print(json.dumps(sys.path))'],capture_output=True,check=True,timeout=5).stdout
 if len(output)>16384:raise ValueError('python-import-path-bound')
 paths=json.loads(output)
 if type(paths) is not list or not 1<=len(paths)<=8:raise ValueError('python-import-path-count')
 entries=0;alias_links=0;alias_read_bytes=0;targets={}
 for root_ordinal,value in enumerate(paths,1):
  if type(value) is not str or not re.fullmatch(r'/usr/lib(?:64)?/python[0-9./a-z-]+(?:\.zip)?',value):raise ValueError('python-import-path-scope')
  path=Path(value)
  if not path.exists():
   if not value.endswith('.zip'):raise ValueError('python-import-path-missing')
   with trust_location('import-root',root_ordinal):rooted(path.parent)
   continue
  with trust_location('import-root',root_ordinal):rooted(path)
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
      canonical=None
      try:
       with trust_location('import-alias',alias_links+1):canonical=rooted_alias(child);record=alias_record(canonical)
      except TrustRefusal as error:
       if os.environ.get('OVERTE_TRUSTED_ALIAS_DIAGNOSTICS')=='1' and type(canonical)is str:
        # Failure-only observations after the ORIGINAL admission refused.
        # No exception replacement, retry, generic alias bound or read grant.
        try:
         import importlib.util,sys
         specification=importlib.util.spec_from_file_location('reviewed_alias_diagnostics',Path(__file__).with_name('alias_diagnostics.py'))
         observer=importlib.util.module_from_spec(specification);specification.loader.exec_module(observer)
         projection=observer.observe_alias(python,str(child),canonical)
         print('TRUSTED_ALIAS_PROVENANCE:'+json.dumps(projection,sort_keys=True,separators=(',',':')),file=sys.stderr)
        except Exception:
         print('TRUSTED_ALIAS_PROVENANCE:{"schema":1,"scope":"failure-only-installed-alias-provenance","status":"observation-refused"}',file=sys.stderr)
       raise
      alias_links+=1;alias_read_bytes+=record['bytes']
      if alias_links>MAX_ALIAS_LINKS or alias_read_bytes>MAX_ALIAS_READ_BYTES:raise ValueError('python-import-alias-read-budget')
      previous=targets.get(canonical)
      if previous is not None and previous!=record:raise ValueError('python-import-alias-target-changed')
      targets[canonical]=record
      if len(targets)>MAX_ALIAS_TARGETS or sum(item['bytes'] for item in targets.values())>MAX_ALIAS_TOTAL_BYTES:raise ValueError('python-import-alias-total-bound')
     elif info.st_uid or info.st_mode&0o022 or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
      with trust_location('import-tree',entries):raise TrustRefusal('python-import-tree-untrusted',info)
  elif not path.is_file():raise ValueError('python-import-root-type')
 records=validate_alias_records([targets[key] for key in sorted(targets)])
 if aliases is not None:aliases.extend(records)
 return paths

def build(destination,policy,python=None,static_libraries=None):
 destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 if any(destination.iterdir()):raise ValueError('stage-must-be-empty')
 # Policy is operator input, never browser input. Admission validates every use.
 if set(policy)!={'version','hostUID','hostGID','sessionParent','nativeExecutables','nativeReadRoots'} \
   or type(policy['version']) is not int or policy['version']!=1 or type(policy['hostUID']) is not int or not 1<=policy['hostUID']<2**32-1 \
   or type(policy['hostGID']) is not int or not 1<=policy['hostGID']<2**32-1:raise ValueError('policy-header')
 with trust_location('python-executable',0):python=rooted(python or '/usr/bin/python3')
 if not re.fullmatch(r'/usr/bin/python3\.\d{1,2}',python):raise ValueError('python-distro-canonical-path')
 if policy['sessionParent'] not in ('/tmp','/run/user/'+str(policy['hostUID'])):raise ValueError('policy-session-parent')
 for key,maximum in (('nativeExecutables',8),('nativeReadRoots',32)):
  values=policy[key]
  if type(values) is not list or not 1<=len(values)<=maximum or any(type(value) is not str for value in values) or len(set(values))!=len(values):raise ValueError('policy-runtime-scope')
  for value in values:
   if type(value) is not str or len(value.encode())>4096 or not value.startswith('/') or value in ('/','/tmp','/home','/root','/etc','/run','/proc','/dev') \
      or '//' in value or any(part in ('.','..') for part in value.split('/')) or any(ord(c)<32 or ord(c)==127 for c in value) \
      or re.search(r'/(?:\.ssh|\.gnupg|\.config|\.cache|\.local)(?:/|$)',value):raise ValueError('policy-runtime-path')
 import_aliases=[];import_paths=trusted_import_paths(python,aliases=import_aliases)
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
 header+='#define PYTHON_IMPORT_ALIAS_COUNT '+str(len(import_aliases))+'\n'
 header+='static const char *PYTHON_IMPORT_ALIAS_PATHS['+str(max(1,len(import_aliases)))+']='+json.dumps([record['path'] for record in import_aliases] or [None]).replace('[','{').replace(']','}').replace('null','NULL')+';\n'
 header+='static const unsigned PYTHON_IMPORT_ALIAS_BYTES['+str(max(1,len(import_aliases)))+']={'+','.join(str(record['bytes']) for record in import_aliases or [{'bytes':0}])+'};\n'
 header+='static const unsigned char PYTHON_IMPORT_ALIAS_HASHES['+str(max(1,len(import_aliases)))+'][32]={'+','.join('{'+','.join(str(value) for value in bytes.fromhex(record['sha256']))+'}' for record in import_aliases or [{'sha256':'0'*64}])+'};\n'

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
  '''+alias_read_rules(import_aliases)+python+''' r,
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
 manifest={'version':2,'prefix':str(PREFIX),'python':python,'files':files,
  'pythonImportPaths':import_paths,'pythonImportAliases':import_aliases,'rootSource':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'src').iterdir() if p.is_file()},
  'activated':False,'actualNamespaceCapabilityRoutingProof':False}
 (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return manifest

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True);parser.add_argument('--policy',required=True);parser.add_argument('--static-libraries')
 args=parser.parse_args()
 try:build(args.stage,json.loads(Path(args.policy).read_text()),static_libraries=args.static_libraries)
 except Exception as error:
  print(json.dumps(staging_failure(error),sort_keys=True));raise SystemExit(1)
