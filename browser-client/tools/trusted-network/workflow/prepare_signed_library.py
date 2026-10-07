#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Only stage pinned public proofs privately; never install packages or policy."""
import argparse,hashlib,importlib.util,json,os,stat,sys,urllib.request
from pathlib import Path
import signed_library as library
HERE=Path(__file__).resolve().parent
SNAPSHOT='https://snapshot.ubuntu.com/ubuntu/20261002T063000Z/'
INPUTS={
 'InRelease':(SNAPSHOT+'dists/noble-security/InRelease',126127,library.PIN['releaseSHA256']),
 'Packages.xz':(SNAPSHOT+'dists/noble-security/main/binary-amd64/Packages.xz',1069168,library.PIN['indexSHA256']),
 'package-0.private.deb':(SNAPSHOT+'pool/main/p/python3.12/python3.12-minimal_3.12.3-1ubuntu0.17_amd64.deb',library.PIN['interpreterPackageBytes'],library.PIN['interpreterPackageSHA256']),
 'package-2.private.deb':(SNAPSHOT+'pool/main/p/python3.12/libpython3.12t64_3.12.3-1ubuntu0.17_amd64.deb',library.PIN['packageBytes'],library.PIN['packageSHA256'])}
KEYRING_URL='https://archive.ubuntu.com/ubuntu/pool/main/u/ubuntu-keyring/ubuntu-keyring_2023.11.28.1_all.deb'
KEYRING_PACKAGE_HASH='36de43b15853ccae0028e9a767613770c704833f82586f28eb262f0311adb8a8'

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def download(url,size,digest):
 # Every permitted URL and byte bound is source-pinned, not caller input.
 known={(row[0],row[1],row[2])for row in INPUTS.values()}|{(KEYRING_URL,11124,KEYRING_PACKAGE_HASH)}
 if(url,size,digest)not in known:raise ValueError('signed-library-download-scope')
 with urllib.request.build_opener(NoRedirect()).open(url,timeout=15)as response:
  if response.status!=200 or response.geturl()!=url:raise ValueError('signed-library-download-refused')
  content=response.read(size+1)
 if len(content)!=size or hashlib.sha256(content).hexdigest()!=digest:raise ValueError('signed-library-download-digest')
 return content

def source_bytes(path,size,digest):
 # Public proofs are not a source of execution authority: require exact digest
 # and immutable SAME-FD bytes before any output creation. A root administrator
 # may copy a caller-owned private cache into its own fresh private cache.
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
 try:
  before=os.fstat(fd)
  if not stat.S_ISREG(before.st_mode)or before.st_mode&0o022 or before.st_size!=size or before.st_nlink!=1:raise ValueError('signed-library-copy-input')
  result=bytearray()
  while len(result)<=size:
   part=os.read(fd,min(65536,size+1-len(result)))
   if not part:break
   result.extend(part)
  after=os.fstat(fd)
  identity=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns,value.st_uid,value.st_mode,value.st_nlink)
  if identity(before)!=identity(after)or len(result)!=size or hashlib.sha256(result).hexdigest()!=digest:raise ValueError('signed-library-copy-digest')
  return bytes(result)
 finally:os.close(fd)

def keyring_member(package):
 # Reuse the already-reviewed exact ubuntu-keyring decoder; never consult the
 # hosted runner's writable /usr/share/keyrings or global GnuPG trust state.
 if type(package)is not bytes or len(package)!=11124 or hashlib.sha256(package).hexdigest()!=KEYRING_PACKAGE_HASH:raise ValueError('signed-library-keyring-package')
 folder=HERE.parents[2]/'lab/atomic-provisioning'
 def load(name):
  spec=importlib.util.spec_from_file_location('reviewed_'+name,folder/(name+'.py'))
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 previous=sys.modules.get('stage')
 try:
  stage=load('stage');sys.modules['stage']=stage;helper=load('trusted_keyring')
 finally:
  if previous is None:sys.modules.pop('stage',None)
  else:sys.modules['stage']=previous
 record=helper.spec()
 if record['memberSHA256']!=library.PIN['keyringSHA256']or record['packageSHA256']!=KEYRING_PACKAGE_HASH:raise ValueError('signed-library-keyring-pin')
 name,payload=helper.deb_data(package)
 return helper.verified_member(helper.decoded_data(name,payload),record)

def prepare(output,*,source_cache=None,keyring=None,fetch=download):
 if(source_cache is None)!=(keyring is None):raise ValueError('signed-library-copy-pair')
 # No writes until ALL new input buffers are completely hash-pinned.
 if source_cache is None:
  buffers={name:fetch(*row)for name,row in INPUTS.items()}
  key=keyring_member(fetch(KEYRING_URL,11124,KEYRING_PACKAGE_HASH))
 else:
  buffers={name:source_bytes(Path(source_cache)/name,row[1],row[2])for name,row in INPUTS.items()}
  key=source_bytes(keyring,3607,library.PIN['keyringSHA256'])
 for name,data in buffers.items():
  _,size,digest=INPUTS[name]
  if type(data)is not bytes or len(data)!=size or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('signed-library-input-buffer')
 if len(key)!=3607 or hashlib.sha256(key).hexdigest()!=library.PIN['keyringSHA256']:raise ValueError('signed-library-keyring-digest')
 buffers['archive-keyring.gpg']=key
 output=Path(output)
 if not output.is_absolute()or output.parent.resolve(strict=True)!=output.parent:raise ValueError('signed-library-cache-parent')
 output.mkdir(mode=0o700)  # Exclusive: never overwrite an existing cache.
 directory=os.open(output,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  info=os.fstat(directory)
  if info.st_uid!=os.getuid()or stat.S_IMODE(info.st_mode)!=0o700:raise ValueError('signed-library-cache-owner')
  for name,data in buffers.items():
   fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
   try:
    os.fchmod(fd,0o600);offset=0
    while offset<len(data):
     count=os.write(fd,data[offset:offset+65536])
     if count<=0:raise ValueError('signed-library-cache-write')
     offset+=count
    os.fsync(fd)
    info=os.fstat(fd)
    if info.st_uid!=os.getuid()or not stat.S_ISREG(info.st_mode)or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size!=len(data):raise ValueError('signed-library-cache-file')
   finally:os.close(fd)
  os.fsync(directory)
 finally:os.close(directory)
 # Recompute signature/index/package/member verification from the actual own
 # output FDs. This is not installed-library equivalence; build/install do that.
 library.authenticate_cache(output,output/'archive-keyring.gpg')
 return {'version':1,'scope':'pinned-signed-python-library-inputs','completed':True,'files':5,'hostInstalledBytesCompared':False,'systemPackagesModified':False}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--source-cache');parser.add_argument('--keyring')
 args=parser.parse_args()
 try:result=prepare(args.output,source_cache=args.source_cache,keyring=args.keyring)
 except Exception:
  # Private developer traceback is deliberately not reflected into CI output.
  print(json.dumps({'version':1,'scope':'pinned-signed-python-library-inputs','completed':False,'category':'pinned-input-preparation-refused'}));return 1
 print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
