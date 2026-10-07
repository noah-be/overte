// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {lstat,readdir,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';import path from 'node:path';import assert from 'node:assert/strict';
export const SIT_COPIED_HELPERS=Object.freeze(['tablet-sit-audit.mjs','tablet-sit-proof-queue.mjs','tablet-sit-lifecycle.mjs','tablet-sit-source.mjs']);
/** Fixed own public source directories only. Never traverse operator profiles. */
export async function sitCopiedSourceHashes(client){
 const hashes={};let bytes=0;
 async function file(relative){const absolute=path.join(client,relative),st=await lstat(absolute);assert(st.isFile()&&!st.isSymbolicLink()&&st.size<=4*1024*1024,'Sit source must be bounded regular bytes');assert(Object.keys(hashes).length<256&&bytes+st.size<=32*1024*1024,'Sit source census bound');const data=await readFile(absolute);assert.equal(data.length,st.size);bytes+=data.length;hashes[relative]=createHash('sha256').update(data).digest('hex');}
 async function directory(relative,depth=0){assert(depth<=8);const st=await lstat(path.join(client,relative));assert(st.isDirectory()&&!st.isSymbolicLink());const entries=await readdir(path.join(client,relative),{withFileTypes:true});assert(entries.length<=256);for(const entry of entries.sort((a,b)=>a.name.localeCompare(b.name))){const name=path.posix.join(relative,entry.name);if(entry.isDirectory())await directory(name,depth+1);else await file(name);}}
 for(const name of ['gateway','shared'])await directory(name);
 for(const name of SIT_COPIED_HELPERS)await file('tests/integration/'+name);
 return Object.fromEntries(Object.entries(hashes).sort(([a],[b])=>a.localeCompare(b)));
}
