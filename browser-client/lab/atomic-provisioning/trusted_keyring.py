#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Bootstrap only a reviewed Ubuntu keyring; never trust the writable host keyring."""
import io,json,lzma,os,re,selectors,stat,subprocess,sys,tarfile,tempfile,time,zlib
from pathlib import Path
import stage
HERE=Path(__file__).resolve().parent
MAX_TAR=128*1024
NAME='archive-keyring.gpg'

def spec():
 record=json.loads(stage.regular(HERE/'keyring-bootstrap.json',4096))
 expected={'schemaVersion','package','version','architecture','packageURL','packageSHA256','packageBytes','memberName','memberSHA256','memberBytes','trustSource'}
 if set(record)!=expected or (type(record['schemaVersion'])is not int or record['schemaVersion']!=1) or record['package']!='ubuntu-keyring' or record['version']!='2023.11.28.1' or record['architecture']!='all' or record['packageURL']!='https://archive.ubuntu.com/ubuntu/pool/main/u/ubuntu-keyring/ubuntu-keyring_2023.11.28.1_all.deb' or record['packageBytes']!=11124 or record['memberBytes']!=3607 or record['memberName']!='./usr/share/keyrings/ubuntu-archive-keyring.gpg' or record['trustSource']!='reviewed-repository-package-and-member-digests' or not all(type(record[key])is str and re.fullmatch('[0-9a-f]{64}',record[key])for key in('packageSHA256','memberSHA256')):raise ValueError('reviewed-keyring-record-refused')
 dependency=json.loads(stage.regular(HERE/'dependency.json'))
 if record['memberSHA256']!=dependency['keyringSHA256']:raise ValueError('reviewed-keyring-member-pin-refused')
 return record

def deb_data(package):
 if not isinstance(package,bytes) or len(package)>11124 or package[:8]!=b'!<arch>\n':raise ValueError('reviewed-keyring-deb-refused')
 members=[];offset=8
 while offset<len(package):
  header=package[offset:offset+60]
  if len(header)!=60 or header[58:60]!=b'`\n':raise ValueError('reviewed-keyring-ar-header-refused')
  raw=header[48:58].strip()
  if not raw or len(raw)>8 or not raw.isdigit():raise ValueError('reviewed-keyring-ar-size-refused')
  size=int(raw);offset+=60
  if size>11124 or offset+size>len(package):raise ValueError('reviewed-keyring-ar-bounds-refused')
  name=header[:16].rstrip(b' ')
  # Debian ar uses padded bare names; GNU ar may append one slash.
  if name.endswith(b'/'):name=name[:-1]
  if name not in(b'debian-binary',b'control.tar.xz',b'control.tar.zst',b'control.tar.gz',b'data.tar.xz',b'data.tar.zst',b'data.tar.gz'):raise ValueError('reviewed-keyring-ar-name-refused')
  members.append((name,package[offset:offset+size]));offset+=size
  if size%2:
   if package[offset:offset+1]!=b'\n':raise ValueError('reviewed-keyring-ar-padding-refused')
   offset+=1
  if len(members)>3:raise ValueError('reviewed-keyring-ar-count-refused')
 if len(members)!=3 or members[0]!=(b'debian-binary',b'2.0\n') or members[1][0] not in(b'control.tar.xz',b'control.tar.zst',b'control.tar.gz') or members[2][0] not in(b'data.tar.xz',b'data.tar.zst',b'data.tar.gz'):raise ValueError('reviewed-keyring-ar-layout-refused')
 return members[2]

def zstd_data(data):
 # Invoked only after exact reviewed package authentication. Still bound output
 # and deadline, never extract a filesystem tree or run package scripts.
 with tempfile.TemporaryFile()as input_file:
  input_file.write(data);input_file.seek(0)
  child=subprocess.Popen(['zstd','-dc'],stdin=input_file,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  try:
   output=bytearray();deadline=time.monotonic()+5
   with selectors.DefaultSelector()as selector:
    os.set_blocking(child.stdout.fileno(),False);selector.register(child.stdout,selectors.EVENT_READ)
    while selector.get_map():
     remaining=deadline-time.monotonic()
     if remaining<=0:raise subprocess.TimeoutExpired('reviewed-keyring-decode',5)
     for key,_ in selector.select(min(remaining,.1)):
      part=os.read(key.fileobj.fileno(),min(16384,MAX_TAR+1-len(output)))
      if not part:selector.unregister(key.fileobj);continue
      output.extend(part)
      if len(output)>MAX_TAR:raise ValueError('reviewed-keyring-tar-over-limit')
   if child.wait(timeout=max(.001,deadline-time.monotonic())):raise ValueError('reviewed-keyring-decode-refused')
   return bytes(output)
  finally:
   child.stdout.close()
   if child.poll()is None:
    child.terminate()
    try:child.wait(timeout=.5)
    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=.5)

def decoded_data(name,data):
 if name==b'data.tar.xz':
  decoder=lzma.LZMADecompressor();result=decoder.decompress(data,max_length=MAX_TAR+1)
  if len(result)>MAX_TAR or not decoder.eof or decoder.unused_data:raise ValueError('reviewed-keyring-tar-over-limit')
  return result
 if name==b'data.tar.gz':
  decoder=zlib.decompressobj(16+zlib.MAX_WBITS);result=decoder.decompress(data,MAX_TAR+1)
  if len(result)>MAX_TAR or not decoder.eof or decoder.unused_data:raise ValueError('reviewed-keyring-tar-over-limit')
  return result
 if name==b'data.tar.zst':return zstd_data(data)
 raise ValueError('reviewed-keyring-compression-refused')

def verified_member(contents,record):
 if len(contents)>MAX_TAR:raise ValueError('reviewed-keyring-tar-over-limit')
 with tarfile.open(fileobj=io.BytesIO(contents),mode='r:')as archive:
  found=[];count=0
  for member in archive:
   count+=1
   if count>128:raise ValueError('reviewed-keyring-member-count-refused')
   if member.name==record['memberName']:found.append(member)
  if len(found)!=1 or not found[0].isreg() or found[0].size!=record['memberBytes']:raise ValueError('reviewed-keyring-regular-member-refused')
  data=archive.extractfile(found[0]).read(record['memberBytes']+1)
 if len(data)!=record['memberBytes'] or stage.digest(data)!=record['memberSHA256']:raise ValueError('reviewed-keyring-member-digest-refused')
 return data

def locked_write(directory,data,record):
 if len(data)!=record['memberBytes'] or stage.digest(data)!=record['memberSHA256']:raise ValueError('reviewed-keyring-member-digest-refused')
 directory=Path(directory);owner=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  metadata=os.fstat(owner)
  if metadata.st_uid!=os.getuid() or stat.S_IMODE(metadata.st_mode)!=0o700:raise ValueError('private-keyring-directory-required')
  fd=os.open(NAME,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=owner)
  try:
   os.fchmod(fd,0o600)
   with os.fdopen(fd,'wb',closefd=False)as stream:stream.write(data)
   metadata=os.fstat(fd)
   if metadata.st_uid!=os.getuid() or stat.S_IMODE(metadata.st_mode)!=0o600 or metadata.st_nlink!=1 or not stat.S_ISREG(metadata.st_mode) or metadata.st_size!=len(data):raise ValueError('private-keyring-file-required')
  finally:os.close(fd)
 finally:os.close(owner)
 return directory/NAME

class NoRedirect(stage.urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def download_package(url):
 if url!=spec()['packageURL']:raise ValueError('reviewed-keyring-official-url-required')
 with stage.urllib.request.build_opener(NoRedirect()).open(url,timeout=15)as response:
  if response.geturl()!=url:raise ValueError('reviewed-keyring-redirect-refused')
  package=response.read(11125)
 if len(package)>11124:raise ValueError('reviewed-keyring-package-over-limit')
 return package

def provision(directory,fetch=download_package,*,progress=None):
 stage.staging_phase(progress,'dependency-record');record=spec()
 stage.staging_phase(progress,'download-package');package=fetch(record['packageURL'])
 stage.staging_phase(progress,'download-digests')
 if len(package)!=record['packageBytes'] or stage.digest(package)!=record['packageSHA256']:raise ValueError('reviewed-keyring-package-digest-refused')
 stage.staging_phase(progress,'archive-layout');name,compressed=deb_data(package)
 stage.staging_phase(progress,'archive-decode');contents=decoded_data(name,compressed)
 stage.staging_phase(progress,'keyring-bounded-regular');data=verified_member(contents,record)
 stage.staging_phase(progress,'dependency-write');return locked_write(directory,data,record)

def main(*,progress=None):
 stage.staging_phase(progress,'source-check');repo=HERE.parents[2];source=os.environ.get('PROBE_SOURCE_SHA','')
 if not re.fullmatch('[0-9a-f]{40}',source) or subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True,timeout=10,stderr=subprocess.PIPE).strip()!=source:raise ValueError('exact-reviewed-source-required')
 stage.staging_phase(progress,'fork-check')
 if os.environ.get('GITHUB_REPOSITORY')!='noah-be/overte':raise ValueError('authorized-fork-required')
 stage.staging_phase(progress,'temporary-root');parent=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
 stage.staging_phase(progress,'private-directories');directory=Path(tempfile.mkdtemp(prefix='owned-atomic-keyring-',dir=parent));directory.chmod(0o700)
 keyring=provision(directory,progress=progress)
 stage.staging_phase(progress,'workflow-env-open');fd=os.open(os.environ['GITHUB_ENV'],os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode) or any(c in str(keyring)for c in '\r\n\0'):raise ValueError('owned-workflow-env-refused')
  stage.staging_phase(progress,'workflow-env-write');payload=('ATOMIC_REVIEWED_KEYRING='+str(keyring)+'\n').encode()
  if os.write(fd,payload)!=len(payload):raise ValueError('owned-workflow-env-short-write')
 finally:os.close(fd)

def run():
 phase='preparation'
 def progress(value):
  nonlocal phase
  stage.staging_phase(None,value);phase=value
 try:main(progress=progress)
 except Exception as error:
  summary=stage.staging_failure(error,phase);summary['scope']='owned-atomic-trusted-keyring-bootstrap'
  if isinstance(error,stage.urllib.error.HTTPError):
   try:error.close()
   except Exception:pass
  print(json.dumps(summary,sort_keys=True,separators=(',',':')),flush=True)
  print('owned-atomic-trusted-keyring-bootstrap-refused',file=sys.stderr);return 1
 print(json.dumps({'schemaVersion':1,'scope':'owned-atomic-trusted-keyring-bootstrap','completed':True,'phase':'complete'},sort_keys=True,separators=(',',':')),flush=True);return 0
if __name__=='__main__':raise SystemExit(run())
