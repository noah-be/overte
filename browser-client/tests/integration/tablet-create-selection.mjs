// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {readdir,open} from 'node:fs/promises';import {constants} from 'node:fs';import path from 'node:path';
export async function workerProfiles(root){return(await readdir(root,{withFileTypes:true})).filter(e=>e.isDirectory()&&/^overte-browser-[A-Za-z0-9]+$/.test(e.name)).map(e=>path.join(root,e.name));}
export function freshWorkerProfile(before,after){const fresh=after.filter(p=>!before.includes(p));assert.equal(fresh.length,1,'Exactly one fresh native worker profile is required; concurrent joins refuse this mutation probe');return fresh[0];}
export function nativeSelectionTrace(text){
 assert(typeof text==='string'&&text.length<=4*1024*1024,'Native selection log must be bounded');let count=0,last=null;
 for(const line of text.split('\n')){const start=line.indexOf('setSelections: ');if(start<0)continue;count++;const value=JSON.parse(line.slice(start+'setSelections: '.length));assert(Array.isArray(value)&&value.length<=64&&value.every(id=>typeof id==='string'&&/^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(id)),'Malformed native selection record refuses List deletion');last=value;}
 return {count,ids:last};
}
export function assertOwnNativeSelection(trace,previousCount,ownID){assert(trace.count>previousCount,'The genuine List row must produce a new native selection event');assert.deepEqual(trace.ids,[ownID],'List deletion only admits the exact single own native selection');}
export async function readNativeSelection(profile){
 // Fixed pinned-release QStandardPaths location; walk held directory FDs so
 // native Script Console cannot redirect an intermediate component by rename.
 const handles=[];
 try{
  let directory=await open(profile,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);handles.push(directory);
  for(const component of ['data','Overte','Interface','Logs']){directory=await open(`/proc/self/fd/${directory.fd}/${component}`,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);handles.push(directory);}
  const handle=await open(`/proc/self/fd/${directory.fd}/overte-log.txt`,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);handles.push(handle);
  const info=await handle.stat();assert(info.isFile()&&info.size<=4*1024*1024,'Owned native current log must be regular and bounded');const bytes=Buffer.alloc(info.size),{bytesRead}=await handle.read(bytes,0,bytes.length,0);return nativeSelectionTrace(bytes.subarray(0,bytesRead).toString('utf8'));
 }finally{for(const handle of handles.reverse())await handle.close();}
}
