// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual production functions; only transport, filesystem and timer boundaries are controlled.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {EventEmitter,getEventListeners} from 'node:events';
import vm from 'node:vm';
import path from 'node:path';
const source=await readFile(new URL('./worker-sandbox.mjs',import.meta.url),'utf8');
const fixture=await readFile(new URL('./worker-sandbox.test.mjs',import.meta.url),'utf8');
const helperBody=source.slice(source.indexOf('function privateX11Ready('),source.indexOf('\nconst runtimeVariables')).trim();
const wrapperBody=source.slice(source.indexOf('export async function prepareWorker(')).replace(/^export /,'').trim();
const projectionBody=fixture.slice(fixture.indexOf('function workerX11FailureDiagnostic('),fixture.indexOf("\ntest('native worker environment")).trim();
const project=vm.runInNewContext('('+projectionBody+')');
const cookie=Buffer.alloc(16,7);
function transport(scenario) {
 let timer,cleared=0,destroyed=0,writes=0,connections=0,diagnostic,requestedMs;
 const signal=new AbortController();
 class Socket extends EventEmitter {write(request){writes++;assert.equal(request.length,48);assert(request.subarray(32).equals(cookie));}destroy(){destroyed++;this.emit('close');}}
 const socket=new Socket();
 const env={Buffer,createConnection(){connections++;queueMicrotask(()=>{
  if(scenario==='preconnect'){timer();return;}
  socket.emit('connect');
  const response=Buffer.alloc(40);response[0]=1;response.writeUInt16LE(11,2);response.writeUInt16LE(8,6);
  if(scenario==='accepted'){socket.emit('data',response.subarray(0,8));socket.emit('data',response.subarray(8));}
  else if(scenario==='partialheader'){socket.emit('data',response.subarray(0,7));timer();}
  else if(scenario==='partialbody'){socket.emit('data',response.subarray(0,12));timer();}
  else if(scenario==='malformed'){response.writeUInt16LE(12,2);socket.emit('data',response);}
  else if(scenario==='oversized')socket.emit('data',Buffer.alloc(65537));
  else if(scenario==='abort')signal.abort();
  else if(scenario==='closed')socket.emit('close');
  else timer();
 });return socket;},setTimeout(fn,ms){timer=fn;requestedMs=ms;return 1;},clearTimeout(){cleared++;}};
 return {env,signal,observe(value){diagnostic=value;},get state(){return {timer,socket,cleared,destroyed,writes,connections,diagnostic,requestedMs};}};
}
const scenarios=[
 ['preconnect','timeout',false,false,0,null],['noresponse','timeout',true,true,0,null],
 ['partialheader','timeout',true,true,7,null],['partialbody','timeout',true,true,12,40],
 ['accepted','authenticated',true,true,40,40],['malformed','invalid-setup',true,true,40,null],
 ['oversized','invalid-setup',true,true,0,null],['abort','cancelled',true,true,0,null],['closed','closed',true,true,0,null]
];
for(const [scenario,result,connectReached,writeInvoked,responseBytes,validatedExpectedBytes] of scenarios) {
 test('actual X11 fixed stage: '+scenario,async()=>{
  const t=transport(scenario);const ready=vm.runInNewContext('('+helperBody+')',t.env);
  assert.equal(await ready(1234,cookie,t.signal.signal,5000,t.observe),result);
  assert.deepEqual(JSON.parse(JSON.stringify(t.state.diagnostic)),{connectReached,writeInvoked,responseBytes,validatedExpectedBytes});
  assert(Object.isFrozen(t.state.diagnostic));assert.equal(t.state.cleared,1);assert.equal(t.state.destroyed,1);assert.equal(getEventListeners(t.signal.signal,'abort').length,0);
  t.state.timer();t.state.socket.emit('data',Buffer.alloc(40));t.state.socket.emit('close');assert.equal(t.state.destroyed,1);assert.equal(t.state.cleared,1);
 });
}
test('actual helper pre-abort performs no transport/timer or observation',async()=>{
 const t=transport('preconnect');t.signal.abort();const ready=vm.runInNewContext('('+helperBody+')',t.env);
 assert.equal(await ready(1234,cookie,t.signal.signal,5000,t.observe),'cancelled');assert.equal(t.state.connections,0);assert.equal(t.state.diagnostic,undefined);assert.equal(t.state.requestedMs,undefined);
});
function wrapper(scenario,clock=[0,10,37.4]) {
 const t=transport(scenario);let spawned=0,queries=0,sandboxed=0,displayChecks=0;
 const env={...t.env,path,workerEnvironment(){return{};},mkdir:async()=>{},reviewedRoot:x=>x,writeFile:async()=>{},randomBytes:n=>Buffer.alloc(n,7),randomInt:()=>1234,displays:new Set(),process:{env:{}},run:async()=>{},
  access:async filename=>{if(filename.includes('.X11-unix/')){displayChecks++;if(!spawned)throw Error('controlled absent');}else if(filename.includes('-lock'))throw Error('controlled absent');},
  performance:{now(){queries++;return clock.shift()??5000;}},sandboxCommand:async()=>{sandboxed++;return{command:'controlled'};}};
 const ready=vm.runInNewContext('('+helperBody+')',env);env.privateX11Ready=ready;
 const prepare=vm.runInNewContext('('+wrapperBody+')',env);
 const config={directory:'/owned',executable:'/installed/client',sourceEnvironment:{},nativeRoot:'/installed',signal:t.signal.signal,spawnOwned(){spawned++;return{exitCode:null,signalCode:null};}};
 return {t,prepare,config,env,get state(){return{spawned,queries,sandboxed,displayChecks};}};
}
test('actual prepareWorker preserves original failure text and attaches fixed remaining-budget state',async()=>{
 const w=wrapper('partialbody');let original;
 try{await w.prepare(w.config);assert.fail('accepted timeout');}catch(error){original=error;}
 assert.equal(original.message,'The private Xvfb display did not authenticate: timeout');assert.equal(w.t.state.requestedMs,4962);assert.equal(w.state.sandboxed,0);assert.equal(w.env.displays.size,0);
 assert.deepEqual(JSON.parse(JSON.stringify(project(original,2))),{workerOrdinal:2,connectReached:true,writeInvoked:true,responseBytes:12,validatedExpectedBytes:40});
});
test('actual prepareWorker expired original deadline creates no setup transport',async()=>{
 const w=wrapper('accepted',[0,5000]);await assert.rejects(w.prepare(w.config),/The private Xvfb display could not start/);assert.equal(w.t.state.connections,0);assert.equal(w.state.sandboxed,0);assert.equal(w.env.displays.size,0);
});
test('actual prepareWorker accepted response keeps normal success and own authority',async()=>{
 const w=wrapper('accepted');const result=await w.prepare(w.config);assert.equal(result.command,'controlled');assert.equal(w.state.sandboxed,1);assert.equal(w.t.state.connections,1);assert.equal(w.t.state.requestedMs,4962);assert.equal(w.env.displays.size,1);result.release();assert.equal(w.env.displays.size,0);
});
test('failure projection refuses unknown, oversized, incoherent and private extra fields',()=>{
 const valid={connectReached:true,writeInvoked:true,responseBytes:12,validatedExpectedBytes:40};
 for(const bad of [null,{}, {...valid,secret:'private'}, {...valid,responseBytes:65537},{...valid,responseBytes:-1},{...valid,responseBytes:1.5},{...valid,connectReached:false},{...valid,validatedExpectedBytes:39},{...valid,validatedExpectedBytes:65537},{...valid,responseBytes:7}])assert.equal(project({x11ReadinessDiagnostic:bad},1),null);
 for(const ordinal of [0,3,true,'1'])assert.equal(project({x11ReadinessDiagnostic:valid},ordinal),null);
 assert.equal(JSON.stringify(project({x11ReadinessDiagnostic:valid},1)).includes('private'),false);
});
test('actual fixture catch genuinely prints only fixed projection and rethrows identical original error',()=>{
 const start=fixture.indexOf('                catch (error) {\n                    const diagnostic = workerX11FailureDiagnostic');
 assert(start>=0);const end=fixture.indexOf('\n            }',start);const body=fixture.slice(start,end).trim();const printed=[];
 const invoke=vm.runInNewContext('(error=>{try{throw error;}'+body+'})',{workerX11FailureDiagnostic:project,workers:[],console:{error:value=>printed.push(value)}});
 const original=Error('The private Xvfb display did not authenticate: timeout');original.x11ReadinessDiagnostic={connectReached:false,writeInvoked:false,responseBytes:0,validatedExpectedBytes:null};
 assert.throws(()=>invoke(original),error=>error===original);assert.equal(printed.length,1);assert.equal(printed[0],'BROWSER_X11_READINESS '+JSON.stringify({workerOrdinal:1,connectReached:false,writeInvoked:false,responseBytes:0,validatedExpectedBytes:null}));
 printed.length=0;const unknown=Error('unrelated failure');assert.throws(()=>invoke(unknown),error=>error===unknown);assert.equal(printed.length,0);
});
