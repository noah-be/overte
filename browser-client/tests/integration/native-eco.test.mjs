// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual runner contracts; controlled proc/native I/O. No native execution.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('./native-eco.mjs', import.meta.url), 'utf8');
function functionSource(start, end) { const a = source.indexOf(start), b = source.indexOf(end, a); assert(a >= 0 && b > a); return source.slice(a, b); }
const validationContext = vm.createContext({ assert });
vm.runInContext(functionSource('function validateRecord(', 'function consume('), validationContext);
function validate(value) { validationContext.inputJSON = JSON.stringify(value); return vm.runInContext('validateRecord(JSON.parse(inputJSON))', validationContext); }
const safeFailure = vm.runInNewContext(functionSource('function safeFailure(', 'async function hashes(') + '\nsafeFailure;');
const valid=()=>({phase:'baseline',at:1780300000000,nativeVersion:'2026.04.1',connected:true,domainMatched:true,refreshRateProfile:2,regime:2,targetHz:60,
 quality:{performancePreset:3,renderMethod:0,shadowsEnabled:false,hazeEnabled:true,bloomEnabled:true,ambientOcclusionEnabled:false,localLightingEnabled:true,proceduralMaterialsEnabled:true,antialiasingMode:1,viewportResolutionScale:1,verticalFieldOfView:45,cameraClippingEnabled:true,worldDetailQuality:1,automaticLODAdjust:true},dynamicLOD:{angleDeg:.04,targetFPS:40}});
test('actual runner validates only reviewed bounded ECO records; opaque names paths and fields never escape',()=>{
 const value=validate(valid());assert.equal(value.quality.performancePreset,3);assert.equal(value.connected,true);
 for(const change of [{deviceLabel:'private'},{path:'/private'},{connected:false},{regime:4},{refreshRateProfile:3},{domainMatched:false},{dynamicLOD:{angleDeg:.04,targetFPS:40,path:'/private'}}])assert.throws(()=>validate({...valid(),...change}));
 assert.throws(()=>validate({...valid(),quality:{...valid().quality,performancePreset:5}}));
 assert.throws(()=>validate({...valid(),quality:{...valid().quality,hazeEnabled:'true'}}));
 assert.throws(()=>validate({...valid(),phase:'eco',refreshRateProfile:0,targetHz:60}));
 assert.equal(validate({...valid(),phase:'eco',refreshRateProfile:0,targetHz:5}).phase,'eco');
});
test('actual proc parser handles names containing spaces and parentheses and uses exact utime/stime/start indices', async () => {
  const fields=Array(50).fill('0');fields[0]='S';fields[11]='1234';fields[12]='456';fields[19]='900';
  const cpu=vm.runInNewContext(functionSource('function parseProc(', 'function sameLeader(') + '\ncpu;', {assert,readFile:async(file,encoding)=>{assert.equal(file,'/proc/123/stat');assert.equal(encoding,'utf8');return '123 (owned native (worker)) '+fields.join(' ');}});
  assert.deepEqual(JSON.parse(JSON.stringify(await cpu(123))),{ticks:1690,start:900});
});
function ownership() {
  const calls=[],table=new Map(),counts=new Map();let onRead;
  function row(pid,start,group=123,session=123) { const fields=Array(50).fill('0');fields[0]='S';fields[2]=String(group);fields[3]=String(session);fields[19]=String(start);return `${pid} (owned) `+fields.join(' '); }
  table.set(123,row(123,100));table.set(124,row(124,110));table.set(900,row(900,999,900,900));
  const context=vm.createContext({assert,ownedLeader:{pid:123,start:100,group:123,session:123},ownedMembers:new Map([[123,100]]),
    readdir:async(directory)=>{assert.equal(directory,'/proc');return [...table.keys()].map(String);},
    readFile:async(file)=>{const pid=Number(/\/proc\/(\d+)\/stat/.exec(file)?.[1]);counts.set(pid,(counts.get(pid)||0)+1);onRead?.(pid,counts.get(pid));if(!table.has(pid))throw Object.assign(Error('gone'),{code:'ENOENT'});return table.get(pid);},
    process:{kill:(pid,signal)=>calls.push([pid,signal])},});
  vm.runInContext(functionSource('function parseProc(', 'async function stopOwned('),context);
  return {table,row,calls,inspect:()=>vm.runInContext('inspectOwnedGroup()',context),signal:()=>vm.runInContext("signalOwned('SIGTERM')",context),onRead(callback){onRead=callback;}};
}
test('actual runner signals only the original live leader group and records members of its private session',async()=>{
  const f=ownership();assert.equal(await f.signal(),true);assert.deepEqual(f.calls,[[-123,'SIGTERM']]);
  assert.equal((await f.inspect()).length,2);
});
test('actual runner refuses a replaced leader before signaling even at the final pre-syscall identity check',async()=>{
  for(const boundary of [1,4]){const f=ownership();f.onRead((pid,count)=>{if(pid===123&&count===boundary)f.table.set(123,f.row(123,222));});
    await assert.rejects(f.signal(),/identity changed/);assert.equal(f.calls.length,0);}
});
test('actual runner permits an exited leader only with recorded same-starttime group members',async()=>{
  const f=ownership();await f.inspect();f.table.delete(123);assert.equal(await f.signal(),true);assert.deepEqual(f.calls,[[-123,'SIGTERM']]);
  const absent=ownership();await absent.inspect();absent.table.delete(123);absent.table.delete(124);assert.equal(await absent.signal(),false);assert.equal(absent.calls.length,0);
});
test('actual runner refuses reused or unrecorded remaining members and never signals an unrelated session',async()=>{
  for(const kind of ['reused','new','session']){const f=ownership();await f.inspect();f.table.delete(123);
    if(kind==='reused')f.table.set(124,f.row(124,222));
    if(kind==='new')f.table.set(125,f.row(125,111));
    if(kind==='session')f.table.set(124,f.row(124,110,123,900));
    await assert.rejects(f.signal(),/Unverified native group member/);assert.equal(f.calls.length,0);}
});
test('actual ECO runner never publishes raw paths or unknown exception text', () => {
  for(const error of [Error('/host/private/worker'),{message:'secret@example.invalid'},{message:'arbitrary '.repeat(50)}])assert.equal(safeFailure(error),'Owned native refresh proof failed');
  assert.equal(safeFailure({code:'ENOENT',message:'/private/file'}),'Owned proof operation failed: ENOENT');
  assert.equal(safeFailure({code:'ERR_ASSERTION',message:'device labels in operands'}),'A native ECO proof assertion failed');
  assert.equal(safeFailure(Error('The owned native process exited before the native ECO proof completed')),'The owned native process exited before the native ECO proof completed');
});
