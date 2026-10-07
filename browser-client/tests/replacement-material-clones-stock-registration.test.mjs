// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Driver assertion wiring only; no browser, renderer, server, native or pixel claim.
import {test} from 'node:test';import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';import{readFile,writeFile,mkdtemp,rm}from'node:fs/promises';import{tmpdir}from'node:os';import path from'node:path';
import{registeredCloneBodies,cloneVariants}from'./integration/replacement-material-clones-registration.mjs';
const fixture=fileURLToPath(new URL('./replacement-material-clones.browser.spec.ts',import.meta.url));
function report(enabled,variant){return {webgl2:true,cleanup:true,warnings:[],pixels:Array.from({length:5},()=>({visibleChannels:12,surfaceColors:[[1,2,3,255],[4,5,6,255]],background:[0,0,0,255]})),counter:enabled?{enabled:true,applications:4,created:4,reused:2,refused:variant==='foreign'?1:0}:{enabled:false,applications:0,created:0,reused:0,refused:0},initial:{unique:enabled?1:2,slots:2}};}
async function run(entry,modify=()=>{}){let evaluations=0,attachments=0;const patterns=[],bodies=[];
 const page={on:()=>{},route:async(pattern,handler)=>{patterns.push(pattern);if(typeof pattern==='string'){await handler({request:()=>({url:()=>`http://127.0.0.1:5194/replacement-clone-assets/baseline/model.fbx`}),fulfill:async value=>bodies.push(value.body)});await handler({request:()=>({url:()=>`http://127.0.0.1:5194/replacement-clone-assets/candidate/model.fbx`}),fulfill:async value=>bodies.push(value.body)});}},goto:async()=>{},context:()=>({browser:()=>({version:()=> 'authored-no-browser'})}),evaluate:async(_callback,{enabled,variant})=>{evaluations++;const value=report(enabled,variant);modify(value,enabled);return value;}};
 await entry.callback({page},{project:{name:'authored-registration-only'},attach:async(name,value)=>{attachments++;assert.equal(name,'replacement-clone-strict-source-proof');assert.equal(value.contentType,'application/json');assert.equal(JSON.parse(value.body).reports.length,2);}});
 assert.equal(evaluations,2);assert.equal(attachments,1);assert.equal(patterns.length,2);assert.equal(patterns[0].source,'^http:\\/\\/127\\.0\\.0\\.1:\\d+\\/$');assert.equal(patterns[0].flags,'');assert.equal(patterns[1],'**/replacement-clone-assets/**');assert.equal(bodies.length,2);assert(Buffer.isBuffer(bodies[0]));assert.deepEqual(bodies[0],bodies[1]);}
test('Exact six unchanged registered bodies use actual expect, routes and attachments',async()=>{const entries=await registeredCloneBodies(fixture);assert.deepEqual(entries.map(entry=>entry.variant),cloneVariants);for(const entry of entries)await run(entry);assert(Object.isFrozen(entries));});
for(const [name,modify]of[
 ['full disabled counter',(value,enabled)=>{if(!enabled)value.counter.created=1;}],
 ['positive visible channels',value=>{value.pixels[0].visibleChannels=0;}],
 ['initial slot positive',(value,enabled)=>{if(enabled)value.initial.slots=0;}],
 ['initial unique ordering',(value,enabled)=>{if(enabled)value.initial.unique=3;}],
 ['projected mesh center positive',value=>{value.pixels[0].surfaceColors[0]=value.pixels[0].background;}],
 ['exact pixel equality',(value,enabled)=>{if(enabled)value.pixels[0].surfaceColors[0]=[7,8,9,255];}],
 ['foreign rejection positive',(value,enabled)=>{if(enabled)value.counter.refused=0;}],
])test(`Registered assertion remains active: ${name}`,async()=>{const entries=await registeredCloneBodies(fixture);await assert.rejects(()=>run(entries[name.startsWith('foreign')?5:0],modify),error=>typeof error.message==='string'&&error.message.includes('expect(')&&!error.message.includes('not defined'));});
test('Registration/import mutation refuses before executing arbitrary additional body',async()=>{const directory=await mkdtemp(path.join(tmpdir(),'owned-clone-registration-'));try{const file=path.join(directory,'wrong.spec.ts'),source=await readFile(fixture,'utf8');await writeFile(file,source.replace('strict ${variant} pixels','altered ${variant} pixels'));await assert.rejects(()=>registeredCloneBodies(file));await writeFile(file,source.replace("import {test,expect} from '@playwright/test';",'const test=unreviewed;'));await assert.rejects(()=>registeredCloneBodies(file));}finally{await rm(directory,{recursive:true,force:true});}});
