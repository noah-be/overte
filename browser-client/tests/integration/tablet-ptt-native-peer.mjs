// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Only the already owned isolated lab author; no native launch, entity operation or permission provisioning.
import assert from 'node:assert/strict';import {constants} from 'node:fs';import {open,readFile,realpath,readlink,unlink} from 'node:fs/promises';import path from 'node:path';import {createHash} from 'node:crypto';
export const AUTHOR_SOURCE_SHA256='735a5ee9b4327963ea7fb2ebec5e2159c1196aa99d8b6e7fd996809f521b7ede';
export const AUTHOR_DIAGNOSTICS_SHA256='d59ff56f281fe91c19a16ff36686dcb29767405943023b11a76daa2c5a6a651e';
const MAX_TAIL=1024*1024,sha=b=>createHash('sha256').update(b).digest('hex'),flags=constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK;

export const HISTORICAL_AUTHOR_SOURCE_SHA256='6f9460727f45e954ba576a642e9711b5fa734fa634b724c14cad7da6dbb38af8';
export const HISTORICAL_AUTHOR_DIAGNOSTICS_SHA256='5fa16f3effc4036817351ed20a2fc87d793ebf9fab139b1dfdf57ef639ad0f99';
export const HISTORICAL_SERVED_SHA256='6edf4ce0147b9ad0118b8118fb56fef70b7064bb03b453225bed84b8baa752e1';
export function admitServedAuthor(served,{source,diagnostics}){
 if(!Buffer.isBuffer(served)||served.length>131072||sha(source)!==AUTHOR_SOURCE_SHA256||sha(diagnostics)!==AUTHOR_DIAGNOSTICS_SHA256)throw fail();
 const approved=[{bytes:source,registration:'current-plain'},...['full','passive'].map(mode=>({bytes:Buffer.concat([Buffer.from('var BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS = true;\nvar BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE = '+JSON.stringify(mode)+';\n'),diagnostics,Buffer.from('\n'),source]),registration:'current-'+mode}))];
 const current=approved.find(x=>x.bytes.equals(served));if(current)return{sourceSHA256:AUTHOR_SOURCE_SHA256,diagnosticsSHA256:AUTHOR_DIAGNOSTICS_SHA256,servedSourceSHA256:sha(served),registration:current.registration};
 // Whole byte identity is mandatory, not a permissive prefix/suffix fallback.
 // Both historical components are exact fork4fafa698 source objects.
 if(sha(served)!==HISTORICAL_SERVED_SHA256)throw fail();
 const prefix=Buffer.from('var BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS = true;\n'),oldAuthor=served.subarray(served.length-7533),oldDiagnostics=served.subarray(prefix.length,prefix.length+6277);
 if(served.length!==13861||!served.subarray(0,prefix.length).equals(prefix)||served[prefix.length+6277]!==10||sha(oldAuthor)!==HISTORICAL_AUTHOR_SOURCE_SHA256||sha(oldDiagnostics)!==HISTORICAL_AUTHOR_DIAGNOSTICS_SHA256)throw fail();
 return{sourceSHA256:HISTORICAL_AUTHOR_SOURCE_SHA256,diagnosticsSHA256:HISTORICAL_AUTHOR_DIAGNOSTICS_SHA256,servedSourceSHA256:HISTORICAL_SERVED_SHA256,registration:'historical-full-no-mode'};
}

const fail=()=>Error('The owned native audio author identity or command readback was refused');
export function processStat(text){const end=text.lastIndexOf(') '),p=end>=0?text.slice(end+2).trim().split(/\s+/):[];if(p.length<20||!/^\d+$/.test(p[2])||!/^\d+$/.test(p[19])||p[0]==='Z')throw fail();return{group:Number(p[2]),startTicks:p[19]};}
export function authorIdentity(entry,actual,{cwd,kind,executable,httpDirectory}){
 if(!entry||!Number.isSafeInteger(entry.pid)||entry.pid<1||typeof entry.startTicks!=='string'||!/^\d+$/.test(entry.startTicks)||!Array.isArray(entry.arguments)||entry.arguments.length>32||!entry.arguments.every(x=>typeof x==='string'&&x.length<4096))throw fail();
 if(actual.startTicks!==entry.startTicks||actual.group!==entry.pid||actual.cwd!==cwd||actual.executable!==executable||!Array.isArray(actual.arguments))throw fail();
 const expected=entry.arguments.slice(1);if(JSON.stringify(actual.arguments.slice(1))!==JSON.stringify(expected))throw fail();
 const option=k=>{const ids=expected.reduce((a,v,i)=>(v===k&&a.push(i),a),[]);if(ids.length!==1||ids[0]+1>=expected.length)throw fail();return expected[ids[0]+1];};
 if(kind==='native'){if(entry.arguments[0]!==cwd+'/build/browser-lab/appimage/squashfs-root/AppRun')throw fail();if(option('--defaultScriptsOverride')!=='http://127.0.0.1:45110/native-participant.js'||option('--url')!=='hifi://127.0.0.2:45102/3,1.8,3/0,0,0,1'||!entry.arguments[0].endsWith('/AppRun'))throw fail();}
 else if(kind==='http'){if(JSON.stringify(expected)!==JSON.stringify(['-m','http.server','45110','--bind','127.0.0.1','--directory',httpDirectory]))throw fail();}
 else throw fail();return true;
}
export function projectAuthorAudio(text,{sequence,muted,now=Date.now(),since=0}={}){
 if(typeof text!=='string'||Buffer.byteLength(text)>MAX_TAIL||!Number.isSafeInteger(now)||now<0)throw fail();let applied=null,observation=null,lastSequence=0;
 for(const line of text.split('\n')){const i=line.indexOf('BROWSER_LAB ');if(i<0)continue;let r;try{r=JSON.parse(line.slice(i+12));}catch{continue;}if(!r||typeof r.at!=='number'||!Number.isFinite(r.at)||r.at<0||r.at>now+1000)continue;
  if(r.kind==='command-applied'&&Number.isSafeInteger(r.data?.sequence)&&r.data.sequence>0){lastSequence=Math.max(lastSequence,r.data.sequence);if(r.data.sequence===sequence&&r.at>=since&&r.data.muted===muted&&Object.keys(r.data).length===2)applied=r.at;}
  if(r.kind==='observation'&&typeof r.data?.muted==='boolean')observation={at:r.at,muted:r.data.muted};
 }
 return{lastSequence,commandApplied:applied!==null,observationPresent:!!observation,observationMuted:observation?.muted??null,observationAfterCommand:applied!==null&&!!observation&&observation.at>=applied,observationFresh:!!observation&&now>=observation.at&&now-observation.at<=5000};
}
export function nextAuthorSequence(previous,observed,now=Date.now()){if(!Number.isSafeInteger(previous)||previous<0||!Number.isSafeInteger(observed)||observed<0||!Number.isSafeInteger(now)||now<0||Math.max(previous,observed,now)>=Number.MAX_SAFE_INTEGER)throw fail();return Math.max(previous,observed,now)+1;}

// Exact production command transaction, injectable I/O only for offline ownership/deadline contracts.
export function createAuthorConsent(io){let sequence=0,changed=false,restored=false,restoration,pending=null,closed=false;
 async function transact(muted){if(closed||typeof muted!=='boolean')throw fail();await io.identity();if(closed)throw fail();const old=await io.readCommand(),observed=await io.projection();sequence=nextAuthorSequence(old.sequence,Math.max(sequence,observed.lastSequence),io.now());const since=io.now(),deadline=since+15000;await io.identity();if(closed)throw fail();changed=true;restored=false;await io.writeCommand({sequence,muted});while(io.now()<deadline){if(closed)throw fail();await io.identity();const p=await io.projection({sequence,muted,since});if(p.commandApplied&&p.observationAfterCommand&&p.observationFresh&&p.observationMuted===muted){if(muted)restored=true;return{commandApplied:true,actualMuted:muted,observationAfterCommand:true,sourceSHA256:io.sourceSHA256??AUTHOR_SOURCE_SHA256};}await io.wait(100);}throw Error('The owned native audio command was not independently observed within fifteen seconds');}
 function setMuted(muted){if(closed||pending)return Promise.reject(fail());if(!muted)restoration=undefined;const p=transact(muted);pending=p;const done=()=>{if(pending===p)pending=null;};p.then(done,done);return p;}
 function restore(){if(restoration)return restoration;if(!changed||restored)return Promise.resolve();restoration=setMuted(true);return restoration;}
 return {setMuted,restore,async close(){if(closed)return;closed=true;const p=pending;if(p)await p.catch(()=>{});if(changed&&!restored)throw Error('The native peer was not confirmed muted before command cleanup');}};
}

async function regular(handle,max){const st=await handle.stat();if(!st.isFile()||st.uid!==process.getuid()||st.mode&0o022||!Number.isSafeInteger(st.size)||st.size<0||st.size>max)throw fail();return st;}
async function readBounded(handle,max){await regular(handle,max);const b=Buffer.alloc(max+1);let n=0;while(n<b.length){const r=await handle.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}if(n>max)throw fail();return b.subarray(0,n);}
export async function openOwnedNativeAudioAuthor(root,{pulseServer}){
 if(typeof root!=='string'||!path.isAbsolute(root)||await realpath(root)!==root||pulseServer!==`unix:${root}/build/browser-lab/runtime/native-pulse.sock`)throw fail();
 const handles=[],directories=new Map();let lock,closed=false;const lockName='.browser-ptt-peer-command.lock';
 async function directory(parts){let held=directories.get('');if(!held){held=await open(root,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);handles.push(held);directories.set('',held);}let key='';for(const component of parts){key+=(key?'/':'')+component;if(directories.has(key)){held=directories.get(key);continue;}held=await open(`/proc/self/fd/${held.fd}/${component}`,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);const st=await held.stat();if(!st.isDirectory()||st.uid!==process.getuid()||st.mode&0o022)throw fail();handles.push(held);directories.set(key,held);}return held;}
 async function file(parts,mode=flags){const dir=await directory(parts.slice(0,-1)),f=await open(`/proc/self/fd/${dir.fd}/${parts.at(-1)}`,mode);handles.push(f);return f;}
 try{
  const registry=await file(['build','browser-lab','runtime','processes.json']),state=JSON.parse((await readBounded(registry,65536)).toString());
  const authorFile=await file(['browser-client','lab','native-participant.js']),source=await readBounded(authorFile,65536);if(sha(source)!==AUTHOR_SOURCE_SHA256)throw fail();
  const diagnosticsFile=await file(['browser-client','gateway','native-avatar-sample-diagnostics.js']),diagnostics=await readBounded(diagnosticsFile,65536);if(sha(diagnostics)!==AUTHOR_DIAGNOSTICS_SHA256)throw fail();
  const servedFile=await file(['build','browser-lab','http','native-participant.js']),served=await readBounded(servedFile,131072),accounted=admitServedAuthor(served,{source,diagnostics});
  const log=await file(['build','browser-lab','logs','native.log']),command=await file(['build','browser-lab','http','command.json'],constants.O_RDWR|constants.O_NOFOLLOW|constants.O_NONBLOCK);
  async function identity(){for(const kind of ['native','http']){const e=state[kind==='native'?'native':'assets-http'];if(!e||!Number.isSafeInteger(e.pid)||e.pid<1)throw fail();const proc='/proc/'+e.pid;const [stat,cwd,executable,args]=await Promise.all([readFile(proc+'/stat','utf8'),readlink(proc+'/cwd'),readlink(proc+'/exe'),readFile(proc+'/cmdline')]);const entryPath=e.arguments?.[0];if(typeof entryPath!=='string')throw fail();const expectedExecutable=kind==='native'?await realpath(path.join(path.dirname(entryPath),'usr/bin/interface')):await realpath(entryPath);authorIdentity(e,{...processStat(stat),cwd,executable,arguments:args.toString().split('\0').filter(Boolean)},{cwd:root,kind,executable:expectedExecutable,httpDirectory:root+'/build/browser-lab/http'});}}
  await identity();if(typeof state.native.startedAt!=='number'||!Number.isFinite(state.native.startedAt)||state.native.startedAt<0||state.native.startedAt>Date.now()/1000)throw fail();const http=await directory(['build','browser-lab','http']);lock=await open(`/proc/self/fd/${http.fd}/${lockName}`,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);handles.push(lock);const ownStat=processStat(await readFile('/proc/self/stat','utf8'));await lock.writeFile(JSON.stringify({version:1,pid:process.pid,startTicks:ownStat.startTicks})+'\n');
  async function projection(operation={}){const st=await log.stat();if(!st.isFile()||st.uid!==process.getuid()||st.mode&0o022||!Number.isSafeInteger(st.size)||st.size<0)throw fail();const start=Math.max(0,st.size-MAX_TAIL),b=Buffer.alloc(Math.min(st.size,MAX_TAIL));const {bytesRead}=await log.read(b,0,b.length,start);let text=b.subarray(0,bytesRead).toString();if(start){const nl=text.indexOf('\n');text=nl<0?'':text.slice(nl+1);}return projectAuthorAudio(text,operation);}
  if((await servedFile.stat()).mtimeMs>state.native.startedAt*1000+1)throw fail();
  async function commandIdentity(){const current=await open(`/proc/self/fd/${http.fd}/command.json`,flags);try{const [a,b]=await Promise.all([regular(current,4096),regular(command,4096)]);if(a.ino!==b.ino||a.dev!==b.dev)throw fail();}finally{await current.close();}}
  const initial=await projection();if(!initial.observationFresh||initial.observationMuted!==true)throw fail();
  const consent=createAuthorConsent({sourceSHA256:accounted.sourceSHA256,now:Date.now,wait:ms=>new Promise(r=>setTimeout(r,ms)),identity:async()=>{await identity();await commandIdentity();},readCommand:async()=>JSON.parse((await readBounded(command,4096)).toString()),projection,writeCommand:async value=>{const body=Buffer.from(JSON.stringify(value)+'\n');let n=0;while(n<body.length){const r=await command.write(body,n,body.length-n,n);if(!r.bytesWritten)throw fail();n+=r.bytesWritten;}await command.truncate(body.length);}});

  return {...accounted,currentSourceSHA256:AUTHOR_SOURCE_SHA256,currentDiagnosticsSHA256:AUTHOR_DIAGNOSTICS_SHA256,setMuted:consent.setMuted,restore:consent.restore,
   async close(){if(closed)return;closed=true;let failure;try{await consent.close();}catch(e){failure=e;}const http=directories.get('build/browser-lab/http');try{if(lock){const held=await lock.stat(),current=await open(`/proc/self/fd/${http.fd}/${lockName}`,flags);try{const st=await current.stat();if(st.dev!==held.dev||st.ino!==held.ino)throw fail();}finally{await current.close();}await unlink(`/proc/self/fd/${http.fd}/${lockName}`);}}catch(e){failure=e;}finally{for(const f of handles.reverse())try{await f.close();}catch(e){failure||=e;}}if(failure)throw failure;}}

 }catch(error){if(lock){const http=directories.get('build/browser-lab/http');try{const held=await lock.stat(),current=await open(`/proc/self/fd/${http.fd}/${lockName}`,flags);let own=false;try{const st=await current.stat();own=st.dev===held.dev&&st.ino===held.ino;}finally{await current.close();}if(own)await unlink(`/proc/self/fd/${http.fd}/${lockName}`);}catch{}}for(const f of handles.reverse())await f.close().catch(()=>{});throw error;}
}
