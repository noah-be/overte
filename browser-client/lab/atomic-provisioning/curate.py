#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Project only fixed reviewed summary enums; no raw file copy or log artifact."""
import json,os,stat
from pathlib import Path
from stage import regular,write
GROUPS={'anonymous','localhost','logged-in','friends'}
FLAGS={'id_can_connect','id_can_rez_avatar_entities','id_can_adjust_locks','id_can_rez','id_can_rez_tmp','id_can_write_to_asset_server','id_can_connect_past_max_capacity','id_can_kick','id_can_replace_content','id_can_get_and_set_private_user_data','id_can_view_asset_urls'}
CALLS={'linkat','rename','renameat','renameat2','fsync','fdatasync'}
ERRNO={'EPERM','EACCES','ENOENT','EEXIST','ENOTDIR','EISDIR','EXDEV','EROFS','ENOSPC','EDQUOT','EIO','EINVAL','EBADF','ENOMEM','EMFILE','ENFILE','EINTR','ENOSYS','EOPNOTSUPP','unrecognized-errno'}
def enum(v,values):
 if type(v)is not str or v not in values:raise ValueError('fixed-enum-refused')
 return v
def boolean(v):
 if type(v)is not bool:raise ValueError('fixed-boolean-refused')
 return v
def count(v):
 if type(v)is not int or not 0<=v<=2**53-1:raise ValueError('fixed-count-refused')
 return v
def rows(value):
 if type(value)is not dict or set(value)-CALLS:raise ValueError('fixed-syscalls-refused')
 result={}
 for call,row in value.items():
  if type(row)is not dict or set(row)!={'success','failure','unclassifiedResult','errno'}or type(row['errno'])is not dict or set(row['errno'])-ERRNO:raise ValueError('fixed-syscall-shape-refused')
  result[call]={key:count(row[key])for key in('success','failure','unclassifiedResult')};result[call]['errno']={key:count(number)for key,number in row['errno'].items()}
 return result
def project(doc):
 allowed={'schemaVersion','scope','completed','phase','endpointOwnership','provisioning','postWindowClockMonotonic','guestReadback','observerStopped','observer','observerSummary','targetSyscalls','nativeCommitFailureCorrelatedWithExactDestinationFailure','fullCapturePersistenceMarkers','persistenceLogWindowLimit','failureCategory','diagnosticLaunch','nativeConfinement'}
 if type(doc)is not dict or set(doc)-allowed or doc.get('schemaVersion')!=1:raise ValueError('fixed-summary-shape-refused')
 enum(doc['scope'],{'standalone-fresh-domain-provisioning-probe-not-nineteen-stage-world-lifecycle'})
 for key in('postWindowClockMonotonic','nativeCommitFailureCorrelatedWithExactDestinationFailure'):
  if key in doc:boolean(doc[key])
 if 'observerSummary'in doc:enum(doc['observerSummary'],{'unavailable-or-unclassified'})
 if 'persistenceLogWindowLimit'in doc:enum(doc['persistenceLogWindowLimit'],{'includes-startup-and-post; pipe-drain-can-lag-post-return'})
 out={'schemaVersion':1,'scope':'standalone-owned-settings-probe-not-nineteen-stage-ci','completed':boolean(doc['completed']),'phase':enum(doc['phase'],{'preparation','observer-launch','native-readiness','endpoint-ownership','settings-provisioning','stored-readback'}),'endpointOwnership':enum(doc['endpointOwnership'],{'not-observed','exact-owned-native-fixed-port'}),'settingsCommitCause':'not-established'}
 if 'failureCategory'in doc:out['failureCategory']=enum(doc['failureCategory'],{'fixed-probe-refusal','owned-process-or-source-readback-refused'})
 if 'observerStopped'in doc:out['observerStopped']=boolean(doc['observerStopped'])
 if 'diagnosticLaunch'in doc:
  out['diagnosticLaunch']=enum(doc['diagnosticLaunch'],{'signed-bwrap-fixed-tmpfile-denial','managed-domain-fixed-tmpfile-denial'})
 if 'nativeConfinement'in doc:
  confinement=doc['nativeConfinement']
  keys={'zeroCapabilities','noNewPrivileges','userIsolated','ipcIsolated','profile','identityStable','seccompFiltered','allThreadsConfined'}
  if type(confinement)is not dict or set(confinement)!=keys or 'diagnosticLaunch'not in out:raise ValueError('confinement-shape-refused')
  out['nativeConfinement']={key:boolean(confinement[key])for key in keys-{'profile'}}
  out['nativeConfinement']['profile']=enum(confinement['profile'],{'signed-bwrap-child-enforce','preserved-enforcing-selinux-context','unqualified'})
 provision=doc['provisioning']
 if type(provision)is str:out['provisioning']=enum(provision,{'not-requested'})
 elif type(provision)is dict:
  if set(provision)-{'kind','schema','response','configurationChanged','persistence','oauthBefore','oauthAfter'}:raise ValueError('provisioning-unknown-fields')
  enum(provision['kind'],{'settings-provisioning'})
  schema=provision['schema']
  if set(schema)!={'version','postingKeys'}:raise ValueError('schema-fields-refused')
  enum(schema['version'],{'2.7','unrecognized','unavailable'});enum(schema['postingKeys'],{'unrecognized','recognized-domain-settings'})
  if provision['configurationChanged']is not None:boolean(provision['configurationChanged'])
  out['provisioning']={}
  for key in('oauthBefore','oauthAfter'):out['provisioning'][key]=enum(provision[key],{'unvalidated','disabled','not-observed'})
  persistence=provision['persistence']
  if set(persistence)-{'outcome','observedBytes','truncated'}:raise ValueError('persistence-fields-refused')
  if 'observedBytes'in persistence:count(persistence['observedBytes'])
  if 'truncated'in persistence:boolean(persistence['truncated'])
  out['provisioning']['persistence']=enum(persistence['outcome'],{'not-observed','log-unavailable','log-truncated-during-post','no-reported-failure','parent-create-failed','open-failed','write-failed','commit-failed'})
  response=provision['response'];out['provisioning']['response']={}
  fields={'status':{'not-requested','200','unexpected','http-error','transport-or-redirect-refused'},'endpoint':{'unvalidated','unexpected','expected-settings-endpoint'},'contentType':{'unvalidated','unexpected','application/json'},'body':{'unvalidated','over-limit','success','unexpected-json','invalid-json'}}
  if set(response)-fields.keys():raise ValueError('response-unknown-fields')
  for key,value in response.items():out['provisioning']['response'][key]=enum(value,fields[key])
 else:raise ValueError('provisioning-shape-refused')
 if 'guestReadback'in doc:
  guest=doc['guestReadback']
  if set(guest)!={'kind','passed','shape','unknownRows','duplicateRows','missingRows','differences'}:raise ValueError('guest-fields-refused')
  enum(guest['kind'],{'guest-permission-readback'})
  out['guestReadback']={'passed':boolean(guest['passed']),'shape':enum(guest['shape'],{'valid','invalid-or-over-limit'}),'unknownRows':count(guest['unknownRows']),'duplicateRows':count(guest['duplicateRows'])}
  if type(guest['missingRows'])is not list or len(guest['missingRows'])>4 or type(guest['differences'])is not list or len(guest['differences'])>44:raise ValueError('guest-bound-refused')
  out['guestReadback']['missingRows']=[enum(v,GROUPS)for v in guest['missingRows']];out['guestReadback']['differences']=[]
  for row in guest['differences']:
   if set(row)!={'group','flag','expected','actual'}:raise ValueError('guest-row-shape-refused')
   actual=row['actual'];actual=boolean(actual)if type(actual)is bool else enum(actual,{'missing-or-non-boolean'})
   out['guestReadback']['differences'].append({'group':enum(row['group'],GROUPS),'flag':enum(row['flag'],FLAGS),'expected':boolean(row['expected']),'actual':actual})
 if 'targetSyscalls'in doc:
  target=doc['targetSyscalls']
  if set(target)!={'scope','calls','unmatchedDestination','syncDescriptorUnattributed','unparsedLines','oversizedLines','windowExcluded','captureTruncated','settingsCommitCause'}:raise ValueError('target-fields-refused')
  enum(target['scope'],{'exact-private-settings-destination-within-single-provisioning-window'})
  out['targetSyscalls']={'calls':rows(target['calls']),'settingsCommitCause':enum(target['settingsCommitCause'],{'not-established'}),'captureTruncated':boolean(target['captureTruncated'])}
  for key in('unmatchedDestination','syncDescriptorUnattributed','unparsedLines','oversizedLines','windowExcluded'):out['targetSyscalls'][key]=count(target[key])
 if 'fullCapturePersistenceMarkers'in doc:
  markers=doc['fullCapturePersistenceMarkers'];keys={'parent-create-failed','open-failed','write-failed','commit-failed'}
  if type(markers)is not dict or set(markers)!=keys:raise ValueError('marker-shape-refused')
  out['fullCapturePersistenceMarkers']={key:count(value)for key,value in markers.items()}
 if 'observer'in doc:
  observer=doc['observer']
  if set(observer)!={'schemaVersion','terminal','exitCode','trace','nativeOutputTruncated','tracerOutputTruncated','projection','tracerFailure','limits'}or observer['schemaVersion']!=1:raise ValueError('observer-fields-refused')
  if type(observer['exitCode'])is not int or not -128<=observer['exitCode']<=255:raise ValueError('observer-exit-refused')
  if set(observer['trace'])!={'retainedBytes','observedBytes','truncated'}or observer['trace']['retainedBytes']>262144:raise ValueError('trace-fields-refused')
  projection=observer['projection']
  if set(projection)!={'calls','unparsedLines','oversizedLines','incompleteLines','scope'}:raise ValueError('projection-fields-refused')
  fixed_projection={'scope':enum(projection['scope'],{'owned-process-atomic-syscalls-not-settings-causality'}),'calls':rows(projection['calls'])}
  for key in('unparsedLines','oversizedLines','incompleteLines'):fixed_projection[key]=count(projection[key])
  if observer['limits']!=['ptrace-may-affect-timing','no-settings-target-causality-from-sync-fd','unknown-or-split-trace-lines-explicit','no-shipping-or-CI-pass-claim']:raise ValueError('observer-limits-refused')
  out['observer']={'terminal':enum(observer['terminal'],{'native-terminal','cancelled','original-observer-deadline'}),'tracerFailure':enum(observer['tracerFailure'],{'unobserved-or-unclassified','ptrace-operation-not-permitted','ptrace-permission-denied','ptrace-unclassified-error'}),'trace':{'retainedBytes':count(observer['trace']['retainedBytes']),'observedBytes':count(observer['trace']['observedBytes']),'truncated':boolean(observer['trace']['truncated'])},'nativeOutputTruncated':boolean(observer['nativeOutputTruncated']),'tracerOutputTruncated':boolean(observer['tracerOutputTruncated']),'projection':fixed_projection}
 if out['completed']:
  valid=(out['phase']=='stored-readback'and out['endpointOwnership']=='exact-owned-native-fixed-port'and out.get('observerStopped')is True and out.get('guestReadback',{}).get('passed')is True and out.get('provisioning',{}).get('oauthBefore')=='disabled'and out['provisioning'].get('oauthAfter')=='disabled'and out['provisioning'].get('persistence')=='no-reported-failure'and out['provisioning'].get('response')=={'status':'200','endpoint':'expected-settings-endpoint','contentType':'application/json','body':'success'}and doc.get('postWindowClockMonotonic')is True and not any(out.get('fullCapturePersistenceMarkers',{}).values())and not out.get('observer',{}).get('nativeOutputTruncated',True))
  if not valid:raise ValueError('completed-without-strict-proof-refused')
  if 'diagnosticLaunch'in out:
   confinement=out.get('nativeConfinement',{})
   if out['diagnosticLaunch']=='signed-bwrap-fixed-tmpfile-denial'and confinement.get('profile')!='signed-bwrap-child-enforce':raise ValueError('diagnostic-profile-mismatch-refused')
   if confinement.get('profile')not in('signed-bwrap-child-enforce','preserved-enforcing-selinux-context')or any(confinement.get(key)is not True for key in('zeroCapabilities','noNewPrivileges','userIsolated','ipcIsolated','identityStable','seccompFiltered','allThreadsConfined')):raise ValueError('completed-without-native-confinement-refused')
 return out

def main():
 parent=Path(os.environ['RUNNER_TEMP']).resolve(strict=True);destination=parent/'atomic-settings-safe-summary.json'
 try:
  directory=Path(os.environ['ATOMIC_PROBE_OUTPUT']);st=directory.stat()
  if directory.resolve()!=directory or directory.parent.parent!=parent or directory.is_symlink()or st.st_uid!=os.getuid()or stat.S_IMODE(st.st_mode)!=0o700:raise ValueError('private-output-refused')
  def unique(pairs):
   out={}
   for key,value in pairs:
    if key in out:raise ValueError('duplicate-summary-key')
    out[key]=value
   return out
  doc=json.loads(regular(directory/'probe-summary.json',65536,private=True),object_pairs_hook=unique);safe=project(doc)
 except (KeyError,OSError,ValueError,TypeError,RecursionError):
  write(destination,b'{"schemaVersion":1,"completed":false,"failureCategory":"summary-unavailable-or-unvalidated"}\n');return 1
 write(destination,(json.dumps(safe,indent=2)+'\n').encode());return 0 if safe['completed']else 1
if __name__=='__main__':raise SystemExit(main())
