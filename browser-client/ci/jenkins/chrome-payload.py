#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Admit a complete explicitly reviewed Chrome payload; never download or launch."""
import hashlib,json,os,re,shutil,stat,sys
from pathlib import Path
MAX_BYTES=512*1024*1024
MAX_FILES=512

def refused():raise RuntimeError('reviewed-google-chrome-payload-refused')
def private_directory(path):
 info=path.lstat()
 if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:refused()

def read_file(root,name,limit):
 # Relative descriptor walks refuse symlink ancestors and final components.
 pieces=name.split('/')
 if not pieces or len(pieces)>16 or any(not piece or piece in ('.','..') or len(piece.encode())>255 for piece in pieces):refused()
 fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  for piece in pieces[:-1]:
   nextfd=os.open(piece,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd);os.close(fd);fd=nextfd
  file=os.open(pieces[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
  try:
   initial=os.fstat(file)
   if not stat.S_ISREG(initial.st_mode) or initial.st_size>limit or initial.st_size<0:refused()
   data=bytearray()
   while True:
    chunk=os.read(file,min(1024*1024,limit+1-len(data)))
    if not chunk:break
    data.extend(chunk)
    if len(data)>limit:refused()
   final=os.fstat(file)
   if (initial.st_dev,initial.st_ino,initial.st_size,initial.st_mtime_ns,initial.st_ctime_ns)!=(final.st_dev,final.st_ino,final.st_size,final.st_mtime_ns,final.st_ctime_ns):refused()
   return bytes(data),initial
  finally:os.close(file)
 finally:os.close(fd)

def manifest_bytes(path,expected):
 if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):refused()
 data,_=read_file(path.parent,path.name,1024*1024)
 if hashlib.sha256(data).hexdigest()!=expected:refused()
 def unique(pairs):
  result={}
  for key,value in pairs:
   if key in result:refused()
   result[key]=value
  return result
 try:document=json.loads(data,object_pairs_hook=unique)
 except (ValueError,UnicodeError):refused()
 if not isinstance(document,dict) or set(document)!= {'version','executable','files'} or type(document['version']) is not int or document['version']!=1 or document['executable']!='chrome':refused()
 rows=document['files']
 if not isinstance(rows,list) or not 1<=len(rows)<=MAX_FILES:refused()
 names=set();total=0
 for row in rows:
  if not isinstance(row,dict) or set(row)!= {'path','bytes','sha256','executable'}:refused()
  name=row['path'];size=row['bytes']
  if not isinstance(name,str) or name.startswith('/') or '\0' in name or len(name)>4096 or name in names or name in ('admission.json','manifest.sha256'):refused()
  if type(size) is not int or size<0 or size>MAX_BYTES or type(row['executable']) is not bool or not isinstance(row['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']):refused()
  # Validate even zero-byte path components without touching the filesystem.
  if len(name.split('/'))>16 or any(not part or part in ('.','..') or len(part.encode())>255 for part in name.split('/')):refused()
  names.add(name);total+=size
 if total>MAX_BYTES or not any(row['path']=='chrome' and row['executable'] for row in rows):refused()
 return data,document

def check_rows(root,document,copy_to=None):
 wanted={row['path'] for row in document['files']}
 found=set();directory_count=0
 def inventory(directory,prefix='',depth=0):
  nonlocal directory_count
  if copy_to is None:private_directory(Path(directory))
  if depth>16:refused()
  directory_count+=1
  if directory_count>MAX_FILES:refused()
  with os.scandir(directory) as entries:
   for entry in entries:
    name=prefix+entry.name
    if entry.is_symlink():refused()
    if entry.is_dir(follow_symlinks=False):inventory(Path(entry.path),name+'/',depth+1)
    elif entry.is_file(follow_symlinks=False):
     found.add(name)
     if len(found)>MAX_FILES+2:refused()
    else:refused()
 inventory(root)
 if found!=(wanted if copy_to is not None else wanted|{'admission.json','manifest.sha256'}):refused()
 for row in document['files']:
  data,info=read_file(root,row['path'],row['bytes'])
  if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256'] or (row['executable'] and not info.st_mode&0o111):refused()
  if copy_to is None and (info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=(0o500 if row['executable'] else 0o400)):refused()
  if row['path']=='chrome' and data[:4]!=b'\x7fELF':refused()
  if copy_to is not None:
   path=copy_to/row['path'];path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
   fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o500 if row['executable'] else 0o400)
   with os.fdopen(fd,'wb') as file:file.write(data)

def stage(runtime,manifest_path,expected):
 private_directory(runtime)
 if not manifest_path.is_absolute():refused()
 data,document=manifest_bytes(manifest_path,expected)
 target=runtime/'google-chrome';pending=runtime/'google-chrome-pending'
 if target.exists() or target.is_symlink() or pending.exists() or pending.is_symlink():refused()
 pending.mkdir(mode=0o700)
 try:
  check_rows(manifest_path.parent/'payload',document,pending)
  with (pending/'admission.json').open('xb') as file:file.write(data)
  (pending/'admission.json').chmod(0o400)
  with (pending/'manifest.sha256').open('x') as file:file.write(expected+'\n')
  (pending/'manifest.sha256').chmod(0o400)
  target.mkdir(mode=0o700)
  target_identity=target.stat()
  try:
   for entry in pending.iterdir():entry.rename(target/entry.name)
   pending.rmdir()
  except BaseException:
   current=target.lstat()
   if (current.st_dev,current.st_ino)==(target_identity.st_dev,target_identity.st_ino):shutil.rmtree(target)
   raise
 except BaseException:
  if pending.exists():shutil.rmtree(pending)
  raise
 return str(target/'chrome')

def admission_identity(runtime):
 private_directory(runtime);private_directory(runtime/'google-chrome')
 data,info=read_file(runtime/'google-chrome','manifest.sha256',65)
 if info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o400:refused()
 try:value=data.decode().strip()
 except UnicodeError:refused()
 if not re.fullmatch('[0-9a-f]{64}',value):refused()
 return value

def admitted_executable(runtime, expected_identity=None):
 private_directory(runtime);target=runtime/'google-chrome';private_directory(target)
 expected=admission_identity(runtime)
 if expected_identity is not None and expected!=expected_identity:refused()
 data,document=manifest_bytes(target/'admission.json',expected)
 check_rows(target,document)
 return str(target/'chrome')

if __name__=='__main__':
 try:
  if len(sys.argv)!=4:refused()
  stage(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
 except (RuntimeError,OSError,ValueError):
  print('{"passed":false,"category":"reviewed-google-chrome-payload-refused"}',file=sys.stderr);raise SystemExit(1)
