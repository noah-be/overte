# SPDX-License-Identifier: Apache-2.0
"""Immutable, capability-free admission; no workspace imports or shell commands."""
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import stat

LIMIT=131072
SEALS=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
PREFIX=['--unshare-user','--uid','{uid}','--gid','{gid}','--unshare-pid','--unshare-ipc',
        '--unshare-uts','--die-with-parent','--new-session','--cap-drop','ALL','--clearenv','--ro-bind','/usr','/usr']
REQUIRED={'/usr':('--ro-bind','/usr'),'/proc':('--proc',None),'/dev':('--dev',None),
          '/tmp':('--tmpfs',None),'/tmp/.X11-unix':('--dir',None),'/etc':('--dir',None)}
SYSTEM={'/lib','/lib64','/bin','/etc/ld.so.cache','/etc/hosts','/etc/nsswitch.conf','/etc/ssl',
        '/etc/pki','/etc/fonts','/etc/ca-certificates','/etc/alternatives/libnssckbi.so.x86_64',
        '/etc/alternatives/libnssckbi.so'}
KEYS={'PATH','LANG','HOME','USER','LOGNAME','TMPDIR','XDG_CONFIG_HOME','XDG_DATA_HOME',
      'XDG_CACHE_HOME','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','LD_LIBRARY_PATH','QT_PLUGIN_PATH',
      'QML2_IMPORT_PATH','QTWEBENGINEPROCESS_PATH','QT_SCALE_FACTOR','QT_AUTO_SCREEN_SCALE_FACTOR',
      'QT_ENABLE_HIGHDPI_SCALING','OVERTE_PUBLIC_NATIVE_ROOT','LIBGL_ALWAYS_SOFTWARE','QT_QUICK_BACKEND',
      'PULSE_SERVER','PULSE_SOURCE','PULSE_SINK','DISPLAY','XAUTHORITY'}
OVERRIDES={'browser-snapshot.js':'/scripts/system/snapshot.js',
 'browser-places.js':'/scripts/system/places/places.js','browser-places-ui.js':'/scripts/system/places/placesHtml.js',
 'browser-create-properties.html':'/scripts/system/create/entityProperties/html/entityProperties.html',
 'browser-graphics-override-1.js':'/scripts/system/settings/settings.js',
 'browser-graphics-override-2.qml':'/scripts/system/settings/Settings.qml',
 'browser-graphics-override-3.qml':'/scripts/system/settings/qml/pages/GraphicsSettings.qml',
 'browser-graphics-override-4.qml':'/scripts/system/settings/qml/SettingSlider.qml',
 'browser-graphics-override-5.qml':'/scripts/system/settings/qml/SettingBoolean.qml',
 'browser-graphics-override-6.qml':'/scripts/system/settings/qml/SettingComboBox.qml'}
class Refusal(ValueError): pass

def unique_object(pairs):
 result={}
 for key,value in pairs:
  if key in result: raise Refusal('duplicate-key')
  result[key]=value
 return result

def read_sealed_json(fd):
 info=os.fstat(fd)
 if not stat.S_ISREG(info.st_mode) or not 1<=info.st_size<=LIMIT \
    or fcntl.fcntl(fd,fcntl.F_GET_SEALS)&SEALS!=SEALS:raise Refusal('unsealed-or-unbounded-record')
 data=os.pread(fd,info.st_size+1,0)
 if len(data)!=info.st_size:raise Refusal('record-size-changed')
 try:return json.loads(data,object_pairs_hook=unique_object)
 except (UnicodeError,json.JSONDecodeError) as error:raise Refusal('invalid-record') from error

def exact_int(value,low,high):return type(value) is int and low<=value<=high

def text(value,limit=8192):
 if type(value) is not str or len(value.encode())>limit or '\0' in value:raise Refusal('invalid-string')
 return value

def beneath(value,root):return value==root or value.startswith(root+'/')

def canonical(value):
 value=text(value)
 if not value.startswith('/') or str(Path(value).resolve(strict=True))!=value:raise Refusal('noncanonical-path')
 return value

def validate(config,policy,attestation,*,filesystem=True):
 allowed={'command','args','environment','bridgePort','bridgeSocket','managedUDP','managedUDPSocket','supervisorParentPID'}
 required={'command','args','environment','bridgePort','bridgeSocket','supervisorParentPID'}
 if type(config) is not dict or not required<=config.keys()<=allowed:raise Refusal('config-schema')
 if type(policy) is not dict or set(policy)!={'version','hostUID','hostGID','sessionParent','nativeExecutables','nativeReadRoots'} \
    or type(policy['version']) is not int or policy['version']!=1:raise Refusal('policy-schema')
 if type(attestation) is not dict or set(attestation)!={'version','hostUID','hostGID','parentPID','userNS','netNS','routes'} \
    or type(attestation['version']) is not int or attestation['version']!=1 or attestation['routes']!=12:raise Refusal('route-attestation')
 if policy['hostUID']!=attestation['hostUID'] or policy['hostGID']!=attestation['hostGID'] \
    or not exact_int(policy['hostUID'],1,2**32-2) or not exact_int(policy['hostGID'],1,2**32-2):raise Refusal('caller-policy')
 if not exact_int(config['supervisorParentPID'],1,2**31-1) or config['supervisorParentPID']!=attestation['parentPID']:raise Refusal('parent-mismatch')
 if not exact_int(config['bridgePort'],1,65535):raise Refusal('bridge-port')
 if config['command'] not in ('bwrap','/usr/bin/bwrap'):raise Refusal('worker-command')
 parent=text(policy['sessionParent']);directory=os.path.dirname(text(config['bridgeSocket']))
 if parent not in ('/tmp','/run/user/'+str(policy['hostUID'])) or os.path.dirname(directory)!=parent \
    or not re.fullmatch('overte-browser-[A-Za-z0-9_-]{6,64}',os.path.basename(directory)) \
    or config['bridgeSocket']!=directory+'/native-network.socket':raise Refusal('session-scope')
 roots=policy['nativeReadRoots'];executables=policy['nativeExecutables']
 if type(roots) is not list or not 1<=len(roots)<=32 or type(executables) is not list or not 1<=len(executables)<=8:raise Refusal('runtime-policy')
 for value in roots+executables:
  value=text(value)
  if not value.startswith('/') or value in ('/','/tmp','/home','/root','/etc','/run','/proc','/dev') \
      or re.search(r'/(?:\.ssh|\.gnupg|\.config|\.cache|\.local)(?:/|$)',value):raise Refusal('broad-runtime')
 args=config['args'];env=config['environment']
 if type(args) is not list or not 16<=len(args)<=512 or type(env) is not dict or not env.keys()<=KEYS:raise Refusal('worker-arguments')
 for value in args:text(value)
 for key,value in env.items():text(value)
 prefix=[v.replace('{uid}',str(policy['hostUID'])).replace('{gid}',str(policy['hostGID'])) for v in PREFIX]
 if args[:len(prefix)]!=prefix:raise Refusal('isolation-prefix')
 targets={'/usr':('--ro-bind','/usr')};assigned={};changed=False;i=len(prefix)
 def bind(flag,source,target):
  if target in targets:raise Refusal('duplicate-bind-target')
  if flag=='--bind':
   if source!=directory or target!=directory:raise Refusal('writable-host-bind')
  elif source==directory+'/machine-id' and target=='/etc/machine-id':pass
  elif source==directory+'/network-resolv.conf' and target=='/etc/resolv.conf':pass
  elif source==target and (source in SYSTEM or source in roots or source in executables):pass
  elif source.startswith('/tmp/.X11-unix/X') and source==target and source=='/tmp/.X11-unix/X'+env.get('DISPLAY','')[1:] \
       and re.fullmatch(r':[0-9]{4,5}',env.get('DISPLAY','')):pass
  elif os.path.dirname(source)==directory and os.path.basename(source) in OVERRIDES \
       and target.endswith(OVERRIDES[os.path.basename(source)]) and any(beneath(target,r) for r in roots):pass
  else:raise Refusal('unapproved-bind')
  if filesystem:
   # Exact system usr-merge aliases are already fixed policy sources. Every
   # session/generated/runtime source and destination is otherwise canonical.
   if source not in SYSTEM:canonical(source)
   if os.path.dirname(source)==directory:
    info=os.lstat(source)
    if not stat.S_ISREG(info.st_mode):raise Refusal('session-file-type')
  targets[target]=(flag,source)
 while i<len(args):
  flag=args[i];i+=1
  if flag=='--':break
  if flag in ('--ro-bind','--bind'):
   if i+2>len(args):raise Refusal('missing-bind-argument')
   bind(flag,args[i],args[i+1]);i+=2
  elif flag in ('--proc','--dev','--tmpfs','--dir'):
   if i>=len(args):raise Refusal('missing-filesystem-argument')
   target=args[i];i+=1
   if target not in REQUIRED or REQUIRED[target]!=(flag,None) or target in targets:raise Refusal('filesystem-target')
   targets[target]=(flag,None)
  elif flag=='--chdir':
   if changed or i>=len(args) or args[i]!=directory:raise Refusal('working-directory')
   changed=True;i+=1
  elif flag=='--setenv':
   if i+2>len(args) or args[i] not in env or args[i] in assigned or args[i+1]!=env[args[i]]:raise Refusal('environment-argument')
   assigned[args[i]]=args[i+1];i+=2
  else:raise Refusal('unknown-worker-option')
 else:raise Refusal('missing-worker-delimiter')
 if not changed or assigned!=env or args[i:i+1]==[] or args[i] not in executables:raise Refusal('worker-executable')
 headless=bool(re.fullmatch(r'/usr/bin/python3\.[0-9]{1,2}',args[i]))
 if any(targets.get(k)!=v for k,v in REQUIRED.items()) \
    or targets.get(directory)!=('--bind',directory) \
    or targets.get('/etc/machine-id')!=('--ro-bind',directory+'/machine-id') \
    or targets.get('/etc/resolv.conf')!=('--ro-bind',directory+'/network-resolv.conf'):raise Refusal('missing-required-boundary')
 if headless:
  # Only an explicitly operator-admitted canonical system interpreter can be a
  # displayless contract probe. It still traverses every original bwrap mount,
  # namespace and final zero-cap guard. No guest-controlled loader/GUI variables.
  if env not in ({'PATH':'/usr/bin:/bin'},{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}):raise Refusal('headless-probe-environment')
  if any(target.startswith('/tmp/.X11-unix/X') for target in targets):raise Refusal('headless-probe-display')
 else:
  expected={'HOME':directory,'TMPDIR':directory+'/tmp','XDG_CONFIG_HOME':directory+'/config',
   'XDG_DATA_HOME':directory+'/data','XDG_CACHE_HOME':directory+'/cache','XDG_RUNTIME_DIR':directory,
   'XAUTHORITY':directory+'/Xauthority','DBUS_SESSION_BUS_ADDRESS':'unix:path=/dev/null',
   'PULSE_SERVER':'unix:'+directory+'/pulse.socket',
   'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','USER':'browser','LOGNAME':'browser','LIBGL_ALWAYS_SOFTWARE':'1'}
  if any(env.get(k)!=v for k,v in expected.items()) or not re.fullmatch(r':[0-9]{4,5}',env.get('DISPLAY','')) \
     or targets.get('/tmp/.X11-unix/X'+env['DISPLAY'][1:])!=('--ro-bind','/tmp/.X11-unix/X'+env['DISPLAY'][1:]):raise Refusal('private-environment')
 for key in ('LD_LIBRARY_PATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):
  for value in env.get(key,'').split(':'):
   if value and not any(beneath(value,r) for r in roots):raise Refusal('runtime-environment-path')
 if 'QTWEBENGINEPROCESS_PATH' in env and not any(beneath(env['QTWEBENGINEPROCESS_PATH'],r) for r in roots):raise Refusal('webengine-path')
 if 'OVERTE_PUBLIC_NATIVE_ROOT' in env and env['OVERTE_PUBLIC_NATIVE_ROOT'] not in roots:raise Refusal('public-runtime-root')
 if config.get('managedUDP') is not None:
  value=config['managedUDP']
  if type(value) is not dict or set(value)!={'address','ports'}:raise Refusal('managed-scope')
  try:address=ipaddress.IPv4Address(value['address'])
  except (ValueError,TypeError):raise Refusal('managed-address')
  if not address.is_loopback or type(value['ports']) is not list or not 1<=len(value['ports'])<=32 \
     or any(not exact_int(port,1,65535) for port in value['ports']) \
     or config.get('managedUDPSocket')!=directory+'/managed-udp.socket':raise Refusal('managed-scope')
 elif 'managedUDPSocket' in config or 'managedUDP' in config:raise Refusal('unexpected-managed-record')
 if filesystem:
  canonical(directory)
  info=os.lstat(directory)
  if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise Refusal('session-directory-ownership')
  for path in roots+executables:canonical(path)
 return {**config,'command':'/usr/bin/bwrap','args':args[:i]+['/usr/libexec/overte-browser-network/native-boundary-exec']+args[i:]}

def admitted_config():
 config=read_sealed_json(3);policy=read_sealed_json(8);attestation=read_sealed_json(9)
 for kind,key in (('user','userNS'),('net','netNS')):
  info=os.stat('/proc/self/ns/'+kind)
  if attestation.get(key)!=[info.st_dev,info.st_ino]:raise Refusal('namespace-attestation-mismatch')
 status=Path('/proc/self/status').read_text()
 for field in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
  values=re.findall('^'+field+r':\s*([0-9a-fA-F]+)$',status,re.M)
  if len(values)!=1 or int(values[0],16)!=0:raise Refusal('owner-capability-retirement')
 label=Path('/proc/self/attr/apparmor/current').read_text().strip()
 if label!='overte-browser-network-owner (enforce)':raise Refusal('owner-profile')
 if os.getppid()!=attestation['parentPID']:raise Refusal('owner-parent')
 result=validate(config,policy,attestation)
 for fd in (3,8,9):os.close(fd)
 return result
