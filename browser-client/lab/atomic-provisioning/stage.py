#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Stage fixed reviewed helpers and a signed, hash-pinned official dependency."""
import hashlib,io,json,lzma,os,re,stat,subprocess,tarfile,tempfile,urllib.request,urllib.error,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
MAX_DOWNLOAD=4*1024*1024
FILES=('observer.py','probe.py','target_projection.py','source-pins.json','native-pins.json','dependency.json','confined_launch.py','native_launch.py')

# Internal operation labels and exception classes are the only public inputs.
# No exception text, argv, tool output, pathname, URL or environment is projected.
STAGING_PHASES=frozenset(('preparation','source-check','fork-check','temporary-root',
 'private-directories','helper-copy','dependency-record','download-release','download-index',
 'download-package','download-digests','package-size','dependency-write','keyring-read','keyring-ownership','keyring-write-permissions','keyring-bounded-regular',
 'signature-run','signature-output','signature-validation','signature-log','signed-index-record',
 'index-decode','package-record','archive-list','archive-layout','archive-member-write','archive-member-extract','archive-decode',
 'binary-record','executable-write','dependency-proof','workflow-env-open','workflow-env-write','complete'))
TOOL_PHASES=frozenset(('source-check','signature-run','archive-list','archive-member-extract','archive-decode'))
ENV_PHASES=frozenset(('temporary-root','workflow-env-open'))
KEYRING_PHASES=frozenset(('keyring-read','keyring-ownership','keyring-write-permissions','keyring-bounded-regular'))

def staging_phase(progress,phase):
 if type(phase)is not str or phase not in STAGING_PHASES:raise ValueError('fixed-staging-phase-required')
 if progress is not None:progress(phase)

def staging_failure(error,phase):
 if type(phase)is not str or phase not in STAGING_PHASES:raise ValueError('fixed-staging-phase-required')
 category='unexpected-error';code=None
 if isinstance(error,urllib.error.HTTPError):
  category='download-http-error'
  if type(error.code)is int and 100<=error.code<=599:code=error.code
 elif isinstance(error,urllib.error.URLError):category='download-transport-error'
 elif isinstance(error,(TimeoutError,subprocess.TimeoutExpired)):category='operation-timeout'
 elif isinstance(error,FileNotFoundError):
  category='required-tool-unavailable'if phase in TOOL_PHASES else'trusted-keyring-unavailable'if phase in KEYRING_PHASES else'required-input-unavailable'
 elif isinstance(error,PermissionError):category='filesystem-access-refused'
 elif isinstance(error,subprocess.CalledProcessError):category='external-tool-failed'
 elif isinstance(error,json.JSONDecodeError):category='record-parse-refused'
 elif isinstance(error,lzma.LZMAError):category='index-decode-refused'
 elif isinstance(error,tarfile.TarError):category='archive-parse-refused'
 elif isinstance(error,KeyError)and phase in ENV_PHASES:category='required-environment-unavailable'
 elif isinstance(error,(ValueError,KeyError,IndexError,UnicodeError)):category='validation-refused'
 elif isinstance(error,OSError):category='operating-system-refused'
 result={'schemaVersion':1,'scope':'owned-atomic-dependency-staging','completed':False,'phase':phase,'failureCategory':category}
 if code is not None:result['httpStatus']=code
 return result

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

def signed_dependency(directory,keyring,fetch=download,*,progress=None):
 staging_phase(progress,'dependency-record')
 record=json.loads(regular(HERE/'dependency.json'))
 staging_phase(progress,'download-release');release=fetch(record['releaseURL'])
 staging_phase(progress,'download-index');index=fetch('https://archive.ubuntu.com/ubuntu/dists/noble/'+record['packagesPath'])
 staging_phase(progress,'download-package');package=fetch(record['packageURL'])
 staging_phase(progress,'download-digests')
 for data,key in((release,'releaseSHA256'),(index,'packagesSHA256'),(package,'packageSHA256')):
  if digest(data)!=record[key]:raise ValueError('signed-dependency-digest-refused')
 staging_phase(progress,'package-size')
 if len(package)!=record['packageBytes']:raise ValueError('signed-package-size-refused')
 staging_phase(progress,'dependency-write')
 for name,data in(('InRelease',release),('Packages.xz',index),('strace.deb',package)):write(directory/name,data)
 staging_phase(progress,'keyring-read')
 keyring=Path(keyring).resolve(strict=True);st=keyring.stat()
 staging_phase(progress,'keyring-ownership')
 if st.st_uid not in(0,os.getuid()):raise ValueError('trusted-keyring-permissions-refused')
 staging_phase(progress,'keyring-write-permissions')
 if st.st_mode&0o022:raise ValueError('trusted-keyring-permissions-refused')
 staging_phase(progress,'keyring-bounded-regular')
 regular(keyring,1024*1024)
 staging_phase(progress,'signature-run')
 result=subprocess.run(['gpgv','--homedir',str(directory),'--status-fd','1','--keyring',str(keyring),str(directory/'InRelease')],capture_output=True,timeout=10)
 staging_phase(progress,'signature-output')
 status=result.stdout.decode('ascii','replace')
 if len(result.stdout)+len(result.stderr)>65536:raise ValueError('signature-status-over-limit')
 signatures=[line.split()[2]for line in status.splitlines()if line.startswith('[GNUPG:] VALIDSIG ')]
 staging_phase(progress,'signature-validation')
 if result.returncode or signatures!=[record['signingFingerprint']]:raise ValueError('trusted-archive-signature-refused')
 staging_phase(progress,'signature-log')
 write(directory/'signature.private.log',result.stdout+result.stderr)
 staging_phase(progress,'signed-index-record')
 wanted=re.compile(r'^ '+re.escape(record['packagesSHA256'])+r' +'+str(len(index))+r' '+re.escape(record['packagesPath'])+r'$',re.M)
 # The pinned clear-signed Release body was verified above, including its SHA256 section.
 sha_section=release.decode('ascii').split('SHA256:\n',1)[1].split('\n-----BEGIN PGP SIGNATURE-----',1)[0]
 if not wanted.search(sha_section):raise ValueError('signed-index-record-refused')
 staging_phase(progress,'index-decode')
 decoder=lzma.LZMADecompressor();plain=decoder.decompress(index,max_length=16*1024*1024+1)
 if len(plain)>16*1024*1024 or not decoder.eof:raise ValueError('package-index-over-limit')
 staging_phase(progress,'package-record')
 found=[]
 for stanza in plain.decode('utf8').split('\n\n'):
  fields={line.split(': ',1)[0]:line.split(': ',1)[1]for line in stanza.splitlines()if ': 'in line and not line.startswith(' ')}
  if fields.get('Package')=='strace'and fields.get('Version')==record['version']and fields.get('Architecture')==record['architecture']:found.append(fields)
 if len(found)!=1 or found[0].get('Filename')!=record['packageURL'].removeprefix('https://archive.ubuntu.com/ubuntu/')or found[0].get('SHA256')!=record['packageSHA256']or found[0].get('Size')!=str(len(package)):raise ValueError('signed-package-record-refused')
 staging_phase(progress,'archive-list')
 members=subprocess.check_output(['ar','t',directory/'strace.deb'],timeout=5,text=True,stderr=subprocess.PIPE).splitlines()
 staging_phase(progress,'archive-layout')
 if members!=['debian-binary','control.tar.zst','data.tar.zst']:raise ValueError('reviewed-deb-layout-refused')
 staging_phase(progress,'archive-member-write')
 fd=os.open(directory/'data.tar.zst',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as out:
  staging_phase(progress,'archive-member-extract')
  subprocess.run(['ar','p',directory/'strace.deb','data.tar.zst'],stdout=out,stderr=subprocess.PIPE,check=True,timeout=5)
 # Only a reviewed checksum-pinned archive is given to tar. Never extract its tree.
 staging_phase(progress,'archive-decode')
 contents=subprocess.check_output(['zstd','-dc',directory/'data.tar.zst'],timeout=5,stderr=subprocess.PIPE)
 if len(contents)>8*1024*1024:raise ValueError('reviewed-archive-over-limit')
 with tarfile.open(fileobj=io.BytesIO(contents),mode='r:')as archive:
  items=[member for member in archive if member.name=='./usr/bin/strace']
  if len(items)!=1 or not items[0].isreg()or items[0].size!=record['binaryBytes']:raise ValueError('reviewed-regular-member-required')
  binary=archive.extractfile(items[0]).read(record['binaryBytes']+1)
 staging_phase(progress,'binary-record')
 if digest(binary)!=record['binarySHA256']or len(binary)!=record['binaryBytes']:raise ValueError('reviewed-executable-refused')
 staging_phase(progress,'executable-write')
 write(directory/'strace',binary,0o755)
 return {'signature':'verified-trusted-archive-key','dependency':'exact-reviewed-noble-amd64','binarySHA256':record['binarySHA256']}

def main(*,progress=None):
 staging_phase(progress,'source-check')
 repo=HERE.parents[2];sha=os.environ.get('PROBE_SOURCE_SHA','')
 if not re.fullmatch('[0-9a-f]{40}',sha)or subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True,timeout=10,stderr=subprocess.PIPE).strip()!=sha:raise ValueError('exact-reviewed-source-required')
 staging_phase(progress,'fork-check')
 if os.environ.get('GITHUB_REPOSITORY')!='noah-be/overte':raise ValueError('authorized-fork-required')
 staging_phase(progress,'temporary-root')
 parent=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
 staging_phase(progress,'private-directories')
 base=Path(tempfile.mkdtemp(prefix='owned-atomic-settings-',dir=parent));base.chmod(0o700)
 for name in('probe','lab','output'):(base/name).mkdir(mode=0o700)
 staging_phase(progress,'helper-copy')
 for name in FILES:write(base/'probe'/name,regular((HERE.parent if name=='native_launch.py'else HERE)/name))
 keyring='/usr/share/keyrings/ubuntu-archive-keyring.gpg'
 reviewed=os.environ.get('ATOMIC_REVIEWED_KEYRING')
 if reviewed:
  staging_phase(progress,'keyring-bounded-regular')
  # Never repair/copy the writable host input: accept only exact reviewed bytes
  # in a newly owned0600 single-link file, then snapshot them in our own root.
  data=regular(Path(reviewed),1024*1024,private=True)
  record=json.loads(regular(HERE/'dependency.json'))
  if len(data)!=3607 or digest(data)!=record['keyringSHA256']:raise ValueError('reviewed-keyring-input-refused')
  keyring=base/'probe'/'archive-keyring.gpg';write(keyring,data)
 proof=signed_dependency(base/'probe',keyring,progress=progress)
 staging_phase(progress,'dependency-proof')
 write(base/'dependency-proof.private.json',(json.dumps(proof)+'\n').encode())
 staging_phase(progress,'workflow-env-open')
 env=Path(os.environ['GITHUB_ENV']);lines={'ATOMIC_PROBE_DIRECTORY':base/'probe','OVERTE_LAB_ROOT':base/'lab','ATOMIC_PROBE_OUTPUT':base/'output'}
 fd=os.open(env,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('owned-workflow-env-refused')
  staging_phase(progress,'workflow-env-write')
  payload=''.join(str(key)+'='+str(value)+'\n'for key,value in lines.items())
  if any('\n'in str(value)or'\r'in str(value)for value in lines.values()):raise ValueError('workflow-path-refused')
  os.write(fd,payload.encode())
 finally:os.close(fd)
def run():
 phase='preparation'
 def progress(value):
  nonlocal phase
  if type(value)is not str or value not in STAGING_PHASES:raise ValueError('fixed-staging-phase-required')
  phase=value
 try:main(progress=progress)
 except Exception as error:
  summary=staging_failure(error,phase)
  # HTTPError owns a response/file even for an unsuccessful fetch. Close it
  # before exception cleanup can emit a repr-bearing ResourceWarning.
  if isinstance(error,urllib.error.HTTPError):
   try:error.close()
   except Exception:pass
  print(json.dumps(summary,sort_keys=True,separators=(',',':')),flush=True)
  print('owned-atomic-dependency-staging-refused',file=sys.stderr)
  return 1
 print(json.dumps({'schemaVersion':1,'scope':'owned-atomic-dependency-staging','completed':True,'phase':'complete'},sort_keys=True,separators=(',',':')),flush=True)
 return 0

if __name__=='__main__':raise SystemExit(run())
