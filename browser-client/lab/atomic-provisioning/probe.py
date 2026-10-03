#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Standalone owned DomainServer persistence probe; never attach or run CI gates."""
import argparse,ast,base64,hashlib,importlib.util,json,os,signal,socket,stat,subprocess,sys,time
from pathlib import Path
from observer import checked_regular,validated_launch,MAX_CAPTURE,MAX_ENV_ENTRIES,child_death_guard
from target_projection import summarize

def persistence_markers(data):
 # Full retained capture may include startup messages. No POST-only timestamp
 # is inferred; this avoids claiming success from an asynchronously lagged FD.
 phrases={
  'parent-create-failed':b'Could not create the settings file parent directory. Unable to persist settings.',
  'open-failed':b'Could not open the JSON settings file. Unable to persist settings.',
  'write-failed':b'Could not write to JSON settings file. Unable to persist settings.',
  'commit-failed':b'Could not commit writes to JSON settings file. Unable to persist settings.'}
 return {key:data.count(value)for key,value in phrases.items()}

HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
FIXED_FAILURES=frozenset(('probe-path-not-canonical','fresh-probe-directory-required',
 'probe-directory-not-private-owned','probe-reviewed-source-changed',
 'fresh-probe-registry-required','fresh-probe-config-required','fresh-probe-admin-required',
 'original-initialization-boundary-changed','probe-runtime-directory-refused',
 'reviewed-packaged-native-input-changed','probe-output-refused','owned-endpoint-not-confirmed',
 'input-path-not-canonical','input-not-owned-regular','input-not-private',
 'input-size-or-executable-invalid','input-size-invalid','launch-schema-invalid',
 'launch-path-invalid','launch-executable-hash-mismatch','launch-executable-kind-invalid',
 'launch-environment-invalid','launch-environment-code-override','launch-inherited-home-changed',
 'launch-record-size-invalid'))

def failure_observation(error):
 # Fixed source-owned exception tags only; no exception prose or paths escape.
 category='unclassified'
 if type(error)is ValueError and len(error.args)==1 and type(error.args[0])is str and error.args[0]in FIXED_FAILURES:
  category=error.args[0]
 return {'scope':'owned-probe-failure-observation-not-causality','refusal':category}

def environment_shape(environment):
 # Observe existing schema bounds without publishing a variable name or value.
 if type(environment)is not dict:raise ValueError('launch-environment-invalid')
 strings=all(type(key)is str and type(value)is str for key,value in environment.items())
 return {'scope':'owned-native-environment-schema-observation','entries':len(environment),
  'entryBoundExceeded':len(environment)>MAX_ENV_ENTRIES,'typesValid':strings,
  'keyBoundExceeded':any(type(key)is str and (not key or len(key)>128)for key in environment),
  'valueBoundExceeded':any(type(value)is str and len(value)>8192 for value in environment.values()),
  'nulObserved':any(type(key)is str and type(value)is str and '\0'in key+value for key,value in environment.items())}

def sha(p,*,executable=False):return hashlib.sha256(checked_regular(p,64*1024*1024,executable=executable)).hexdigest()
def exclusive(path,data,mode=0o600):
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW|os.O_NONBLOCK,mode)
 with os.fdopen(fd,'wb')as f:f.write(data)

def canonical(value):
 p=Path(value)
 if not p.is_absolute()or p.resolve()!=p:raise ValueError('probe-path-not-canonical')
 return p

def free_ports():
 for kind,address,port in [(socket.SOCK_STREAM,'127.0.0.1',45100),(socket.SOCK_STREAM,'127.0.0.1',45110),(socket.SOCK_DGRAM,'127.0.0.2',45102),(socket.SOCK_DGRAM,'127.0.0.2',45103)]:
  with socket.socket(socket.AF_INET,kind)as s:s.bind((address,port))

def owned_endpoint(wrapper,native):
 # Bound private ownership readback of the one fixed endpoint, not an attach API.
 raw=Path('/proc/net/tcp').read_bytes()
 if len(raw)>4*1024*1024:return False
 rows=raw.decode('ascii').splitlines()[1:]
 listeners={row.split()[9]for row in rows if row.split()[1].split(':')[1]=='B02C'and row.split()[3]=='0A'}
 if len(listeners)!=1:return False
 descendants={wrapper};processes=[]
 for index,p in enumerate(Path('/proc').iterdir()):
  if index>=32768:return False
  if not p.name.isdecimal():continue
  try:
   fields=(p/'stat').read_text().split(') ',1)[1].split();processes.append((int(p.name),int(fields[1])))
  except (OSError,ValueError,IndexError):continue
 for _ in range(8):
  previous=len(descendants)
  for pid,parent in processes:
   if parent in descendants:descendants.add(pid)
  if len(descendants)>128:return False
  if len(descendants)==previous:break
 for pid in descendants:
  try:
   exe=Path(f'/proc/{pid}/exe')
   if not os.path.samefile(exe,native):continue
   before=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
   links=set()
   for index,f in enumerate(Path(f'/proc/{pid}/fd').iterdir()):
    if index>=1024:return False
    links.add(os.readlink(f))
   after=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
   if before==after and any('socket:['+i+']'in links for i in listeners):return True
  except (OSError,ValueError,IndexError):continue
 return False

def prepare(repo,lab,output):
 repo,lab,output=map(canonical,(repo,lab,output))
 if repo==lab or lab in (Path('/'),Path('/tmp'),Path.home())or output in (lab,repo,Path('/'),Path('/tmp'),Path.home()):raise ValueError('fresh-probe-directory-required')
 for directory in(lab,output):
  st=directory.stat()
  if st.st_uid!=os.getuid()or stat.S_IMODE(st.st_mode)!=0o700:raise ValueError('probe-directory-not-private-owned')
 source=repo/'browser-client/lab'
 pins=json.loads((HERE/'source-pins.json').read_text())
 for name,value in pins.items():
  if sha(source/name)!=value:raise ValueError('probe-reviewed-source-changed')
 sys.path.insert(0,str(source));os.environ['OVERTE_LAB_ROOT']=str(lab)
 spec=importlib.util.spec_from_file_location('owned_atomic_probe_manage',source/'manage.py');manage=importlib.util.module_from_spec(spec);spec.loader.exec_module(manage)
 from native_admin import native_admin_credential
 from provisioning_diagnostics import post_guest_settings,ProvisioningDiagnosticError
 from guest_permissions import guest_permission_diagnostics
 if manage.load_state():raise ValueError('fresh-probe-registry-required')
 for name in ('domain.json',):
  if (lab/'config'/name).exists()or(lab/'config'/name).is_symlink():raise ValueError('fresh-probe-config-required')
 if (lab/'runtime/admin.json').exists():raise ValueError('fresh-probe-admin-required')
 free_ports()
 # Extract only the two reviewed initial assignments, retaining the exact
 # native defaults. No arbitrary source/snippet path or eval input is accepted.
 tree=ast.parse(checked_regular(source/'manage.py',1024*1024))
 fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='start')
 init=[n for n in fn.body if isinstance(n,ast.Assign)and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)and n.targets[0].id in ('permissions','config')]
 if len(init)!=2:raise ValueError('original-initialization-boundary-changed')
 cred=native_admin_credential();context={'PERMISSION_KEYS':manage.PERMISSION_KEYS,'admin_credential':cred}
 exec(compile(ast.Module(body=init,type_ignores=[]),'<reviewed-managed-initial-config>','exec'),context)
 config=context['config']
 for directory in ('config','runtime','logs','data'):
  p=lab/directory;p.mkdir(mode=0o700,exist_ok=True)
  if p.is_symlink()or p.stat().st_uid!=os.getuid():raise ValueError('probe-runtime-directory-refused')
 # Same initial write mode/umask as manage.py, exclusively into a fresh root.
 exclusive(lab/'config/domain.json',(json.dumps(config,indent=2)+'\n').encode(),0o666)
 app=lab/'appimage/squashfs-root';server=lab/'server/opt/overte'
 env={**os.environ,'OVERTE_LAB_ROOT':str(lab),'QT_QPA_PLATFORM':'xcb','QT_SCALE_FACTOR':'1','QT_AUTO_SCREEN_SCALE_FACTOR':'0',
 'LD_LIBRARY_PATH':f'{server}/lib:{app}/usr/lib','QT_PLUGIN_PATH':str(app/'usr/plugins'),'XDG_CONFIG_HOME':str(lab/'config'),'XDG_DATA_HOME':str(lab/'data'),
 'HIFI_DOMAIN_SERVER_HTTP_PORT':'45100','HIFI_DOMAIN_SERVER_HTTPS_PORT':'45101','HIFI_DOMAIN_SERVER_PORT':'45102','HIFI_DOMAIN_SERVER_DTLS_PORT':'45103'}
 native_pins=json.loads((HERE/'native-pins.json').read_text())
 for name,relative in [('domain-server','domain-server'),('describe-settings.json','resources/describe-settings.json')]:
  if sha(server/relative)!=native_pins[name]:raise ValueError('reviewed-packaged-native-input-changed')
 dep=json.loads((HERE/'dependency.json').read_text())
 document={'version':1,'strace':str(HERE/'strace'),'straceSHA256':dep['binarySHA256'],'native':str(server/'domain-server'),'unshare':'/usr/bin/unshare',
 'settings':str(lab/'config/domain.json'),'cwd':str(repo),'output':str(output),'environment':env}
 for name in ('native','unshare'):document[name+'SHA256']=sha(document[name],executable=True)
 try:validated_launch(document)
 except ValueError as error:
  if type(error)is ValueError and error.args==('launch-environment-invalid',):
   print('ATOMIC_PROBE_ENVIRONMENT:'+json.dumps(environment_shape(env),sort_keys=True,separators=(',',':')),file=sys.stderr)
  raise
 exclusive(output/'launch.private.json',(json.dumps(document,indent=2)+'\n').encode())
 payload={'security':{'standard_permissions':[{'permissions_id':name,**{flag:flag in('id_can_connect','id_can_rez','id_can_rez_avatar_entities','id_can_view_asset_urls')for flag in manage.PERMISSION_KEYS}}for name in('anonymous','localhost','logged-in','friends')],'ip_permissions':[],'machine_fingerprint_permissions':[]}}
 authorization='Basic '+base64.b64encode(('browser-lab-admin:'+cred['token']).encode()).decode()
 return manage,document,payload,authorization,post_guest_settings,ProvisioningDiagnosticError,guest_permission_diagnostics

def run(repo,lab,output,*,confined_diagnostic=False):
 process=None;safe_output=False;out={'schemaVersion':1,'scope':'standalone-fresh-domain-provisioning-probe-not-nineteen-stage-world-lifecycle','completed':False,'endpointOwnership':'not-observed','provisioning':'not-requested','phase':'preparation'}
 try:
  output=canonical(output);info=output.stat()
  if info.st_uid!=os.getuid()or stat.S_IMODE(info.st_mode)!=0o700:raise ValueError('probe-output-refused')
  safe_output=True
  manage,doc,payload,auth,post,post_error,guest_check=prepare(repo,lab,output)
  host={key:os.environ[key]for key in('HOME','PATH','LANG','LC_ALL','TMPDIR')if key in os.environ};host['PYTHONDONTWRITEBYTECODE']='1'
  out['phase']='observer-launch'
  expected=os.getpid()
  observer_command=[sys.executable,str(HERE/'observer.py'),'--configuration',str(Path(output)/'launch.private.json')]
  if confined_diagnostic:
   out['diagnosticLaunch']='signed-bwrap-fixed-tmpfile-denial'
   observer_command.append('--confined-diagnostic')
  process=subprocess.Popen(observer_command,env=host,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,preexec_fn=lambda:child_death_guard(expected))
  exclusive(output/'probe-process.private.json',(json.dumps({'pid':process.pid,'startTicks':manage.start_ticks(process.pid),'entrySHA256':sha(HERE/'observer.py')})+'\n').encode())
  out['phase']='native-readiness'
  manage.wait_port(45100) # Exact existing twenty-second readiness function.
  out['phase']='endpoint-ownership'
  if process.poll()is not None or not owned_endpoint(process.pid,doc['native']):raise ValueError('owned-endpoint-not-confirmed')
  out['endpointOwnership']='exact-owned-native-fixed-port'
  if confined_diagnostic:
   from confined_launch import owned_native_confinement,require_confinement
   out['nativeConfinement']=owned_native_confinement(process.pid,doc['native'])
   require_confinement(out['nativeConfinement'])
  out['phase']='settings-provisioning'
  start=time.time()
  try:
   out['provisioning']=post(payload,auth,Path(doc['native']).parent/'resources/describe-settings.json',doc['settings'],Path(output)/'native-output.private.log')
  except post_error as error:out['provisioning']=error.diagnostic
  end=time.time();out['postWindowClockMonotonic']=end>=start
  out['phase']='stored-readback'
  from provisioning_diagnostics import strict_json,read_regular,require_disabled_stored_oauth
  saved=strict_json(read_regular(doc['settings'],1024*1024));require_disabled_stored_oauth(doc['settings'])
  out['guestReadback']=guest_check(saved.get('security',{}).get('standard_permissions'),{flag:flag in('id_can_connect','id_can_rez','id_can_rez_avatar_entities','id_can_view_asset_urls')for flag in manage.PERMISSION_KEYS})
  out['completed']=out['guestReadback']['passed']and out['provisioning'].get('oauthAfter')=='disabled'and out['provisioning'].get('persistence',{}).get('outcome')=='no-reported-failure'
 except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,KeyError,TypeError,UnicodeError) as error:
  out['failureCategory']='fixed-probe-refusal' if isinstance(error,ValueError) else 'owned-process-or-source-readback-refused'
  raise
 finally:
  if process is not None:
   if process.poll()is None:process.send_signal(signal.SIGTERM)
   try:process.wait(timeout=2.5)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
   out['observerStopped']=process.poll()is not None
   out['completed']=out['completed']and out['observerStopped']
   try:
    trace_summary=json.loads(checked_regular(Path(output)/'summary.json',65536,private=True));out['observer']=trace_summary
    native_data=checked_regular(Path(output)/'native-output.private.log',MAX_CAPTURE,private=True)
    out['fullCapturePersistenceMarkers']=persistence_markers(native_data)
    out['persistenceLogWindowLimit']='includes-startup-and-post; pipe-drain-can-lag-post-return'
    if trace_summary['nativeOutputTruncated'] or any(out['fullCapturePersistenceMarkers'].values()):out['completed']=False
    if 'start'in locals()and 'end'in locals()and end>=start:
     data=checked_regular(Path(output)/'atomic-syscalls.private.log',MAX_CAPTURE,private=True)
     out['targetSyscalls']=summarize(data,doc['settings'],start,end,capture_truncated=trace_summary['trace']['truncated'])
     out['nativeCommitFailureCorrelatedWithExactDestinationFailure']=out['provisioning'].get('persistence',{}).get('outcome')=='commit-failed'and any(row['failure']for row in out['targetSyscalls']['calls'].values())
     # This is correlation; an intermediate recoverable link/rename failure is
     # not automatically the terminal Qt commit cause.
   except (OSError,ValueError,KeyError):out['observerSummary']='unavailable-or-unclassified'
  if safe_output:exclusive(Path(output)/'probe-summary.json',(json.dumps(out,indent=2)+'\n').encode())
 return out

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo-root',required=True);p.add_argument('--lab-root',required=True);p.add_argument('--private-output',required=True);p.add_argument('--confined-diagnostic',action='store_true');a=p.parse_args()
 try:r=run(a.repo_root,a.lab_root,a.private_output,confined_diagnostic=a.confined_diagnostic)
 except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,KeyError,TypeError,UnicodeError) as error:
  print('ATOMIC_PROBE_FAILURE:'+json.dumps(failure_observation(error),sort_keys=True,separators=(',',':')),file=sys.stderr)
  print('standalone-owned-probe-refused',file=sys.stderr);return 1
 print(json.dumps({'completed':r['completed'],'scope':r['scope']}));return 0 if r['completed']else 1
if __name__=='__main__':raise SystemExit(main())
