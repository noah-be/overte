#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Stage fixed reviewed helpers and a signed, hash-pinned official dependency."""
import hashlib,io,json,lzma,os,re,stat,subprocess,tarfile,tempfile,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
MAX_DOWNLOAD=4*1024*1024
FILES=('observer.py','probe.py','target_projection.py','source-pins.json','native-pins.json','dependency.json')

def digest(data):return hashlib.sha256(data).hexdigest()
def regular(path,maximum=MAX_DOWNLOAD,*,private=False):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  st=os.fstat(fd)
  if private and(st.st_uid!=os.getuid()or stat.S_IMODE(st.st_mode)!=0o600 or st.st_nlink!=1):raise ValueError('private-input-required')
  if not stat.S_ISREG(st.st_mode)or st.st_size>maximum:raise ValueError('bounded-regular-input-required')
  data=bytearray()
  while len(data)<=maximum:
   part=os.read(fd,min(65536,maximum+1-len(data)))
   if not part:break
   data.extend(part)
  if len(data)>maximum:raise ValueError('input-over-limit')
  return bytes(data)
 finally:os.close(fd)
def write(path,data,mode=0o600):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,mode)
 os.fchmod(fd,mode)
 with os.fdopen(fd,'wb')as out:out.write(data)
def download(url):
 if not url.startswith('https://archive.ubuntu.com/ubuntu/')or any(c in url for c in '\r\n\0'):raise ValueError('fixed-official-url-required')
 with urllib.request.urlopen(url,timeout=15)as response:
  if response.geturl()!=url:raise ValueError('dependency-redirect-refused')
  data=response.read(MAX_DOWNLOAD+1)
 if len(data)>MAX_DOWNLOAD:raise ValueError('dependency-over-limit')
 return data

def signed_dependency(directory,keyring,fetch=download):
 record=json.loads(regular(HERE/'dependency.json'))
 release=fetch(record['releaseURL']);index=fetch('https://archive.ubuntu.com/ubuntu/dists/noble/'+record['packagesPath']);package=fetch(record['packageURL'])
 for data,key in((release,'releaseSHA256'),(index,'packagesSHA256'),(package,'packageSHA256')):
  if digest(data)!=record[key]:raise ValueError('signed-dependency-digest-refused')
 if len(package)!=record['packageBytes']:raise ValueError('signed-package-size-refused')
 for name,data in(('InRelease',release),('Packages.xz',index),('strace.deb',package)):write(directory/name,data)
 keyring=Path(keyring).resolve(strict=True);st=keyring.stat()
 if st.st_uid not in(0,os.getuid())or st.st_mode&0o022:raise ValueError('trusted-keyring-permissions-refused')
 regular(keyring,1024*1024)
 result=subprocess.run(['gpgv','--homedir',str(directory),'--status-fd','1','--keyring',str(keyring),str(directory/'InRelease')],capture_output=True,timeout=10)
 status=result.stdout.decode('ascii','replace')
 if len(result.stdout)+len(result.stderr)>65536:raise ValueError('signature-status-over-limit')
 signatures=[line.split()[2]for line in status.splitlines()if line.startswith('[GNUPG:] VALIDSIG ')]
 if result.returncode or signatures!=[record['signingFingerprint']]:raise ValueError('trusted-archive-signature-refused')
 write(directory/'signature.private.log',result.stdout+result.stderr)
 wanted=re.compile(r'^ '+re.escape(record['packagesSHA256'])+r' +'+str(len(index))+r' '+re.escape(record['packagesPath'])+r'$',re.M)
 # The pinned clear-signed Release body was verified above, including its SHA256 section.
 sha_section=release.decode('ascii').split('SHA256:\n',1)[1].split('\n-----BEGIN PGP SIGNATURE-----',1)[0]
 if not wanted.search(sha_section):raise ValueError('signed-index-record-refused')
 decoder=lzma.LZMADecompressor();plain=decoder.decompress(index,max_length=16*1024*1024+1)
 if len(plain)>16*1024*1024 or not decoder.eof:raise ValueError('package-index-over-limit')
 found=[]
 for stanza in plain.decode('utf8').split('\n\n'):
  fields={line.split(': ',1)[0]:line.split(': ',1)[1]for line in stanza.splitlines()if ': 'in line and not line.startswith(' ')}
  if fields.get('Package')=='strace'and fields.get('Version')==record['version']and fields.get('Architecture')==record['architecture']:found.append(fields)
 if len(found)!=1 or found[0].get('Filename')!=record['packageURL'].removeprefix('https://archive.ubuntu.com/ubuntu/')or found[0].get('SHA256')!=record['packageSHA256']or found[0].get('Size')!=str(len(package)):raise ValueError('signed-package-record-refused')
 members=subprocess.check_output(['ar','t',directory/'strace.deb'],timeout=5,text=True).splitlines()
 if members!=['debian-binary','control.tar.zst','data.tar.zst']:raise ValueError('reviewed-deb-layout-refused')
 fd=os.open(directory/'data.tar.zst',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as out:subprocess.run(['ar','p',directory/'strace.deb','data.tar.zst'],stdout=out,check=True,timeout=5)
 # Only a reviewed checksum-pinned archive is given to tar. Never extract its tree.
 contents=subprocess.check_output(['zstd','-dc',directory/'data.tar.zst'],timeout=5)
 if len(contents)>8*1024*1024:raise ValueError('reviewed-archive-over-limit')
 with tarfile.open(fileobj=io.BytesIO(contents),mode='r:')as archive:
  items=[member for member in archive if member.name=='./usr/bin/strace']
  if len(items)!=1 or not items[0].isreg()or items[0].size!=record['binaryBytes']:raise ValueError('reviewed-regular-member-required')
  binary=archive.extractfile(items[0]).read(record['binaryBytes']+1)
 if digest(binary)!=record['binarySHA256']or len(binary)!=record['binaryBytes']:raise ValueError('reviewed-executable-refused')
 write(directory/'strace',binary,0o755)
 return {'signature':'verified-trusted-archive-key','dependency':'exact-reviewed-noble-amd64','binarySHA256':record['binarySHA256']}

def main():
 repo=HERE.parents[2];sha=os.environ.get('PROBE_SOURCE_SHA','')
 if not re.fullmatch('[0-9a-f]{40}',sha)or subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True,timeout=10).strip()!=sha:raise ValueError('exact-reviewed-source-required')
 if os.environ.get('GITHUB_REPOSITORY')!='noah-be/overte':raise ValueError('authorized-fork-required')
 parent=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
 base=Path(tempfile.mkdtemp(prefix='owned-atomic-settings-',dir=parent));base.chmod(0o700)
 for name in('probe','lab','output'):(base/name).mkdir(mode=0o700)
 for name in FILES:write(base/'probe'/name,regular(HERE/name))
 proof=signed_dependency(base/'probe','/usr/share/keyrings/ubuntu-archive-keyring.gpg')
 write(base/'dependency-proof.private.json',(json.dumps(proof)+'\n').encode())
 env=Path(os.environ['GITHUB_ENV']);lines={'ATOMIC_PROBE_DIRECTORY':base/'probe','OVERTE_LAB_ROOT':base/'lab','ATOMIC_PROBE_OUTPUT':base/'output'}
 fd=os.open(env,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('owned-workflow-env-refused')
  payload=''.join(str(key)+'='+str(value)+'\n'for key,value in lines.items())
  if any('\n'in str(value)or'\r'in str(value)for value in lines.values()):raise ValueError('workflow-path-refused')
  os.write(fd,payload.encode())
 finally:os.close(fd)
if __name__=='__main__':
 try:main()
 except Exception:raise SystemExit('owned-atomic-dependency-staging-refused')
