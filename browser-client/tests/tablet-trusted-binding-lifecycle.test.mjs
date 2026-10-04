import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';

const ptt=await readFile(new URL('./integration/tablet-push-to-talk.mjs',import.meta.url),'utf8');
const people=await readFile(new URL('./integration/tablet-people-session.mjs',import.meta.url),'utf8');
const pttBody=ptt.slice(ptt.indexOf(' async function join(){'),ptt.indexOf('\n const first=await join();'));
const peopleBody=people.slice(people.indexOf('  await page.goto(base);'),people.indexOf('\n  const after=await workerProfiles',people.indexOf('  await page.goto(base);')));
assert(pttBody.startsWith(' async function join(){')&&peopleBody.startsWith('  await page.goto(base);'));

function fixture(kind,{index=0,refuseWait=false}={}){
 const events=[],bindings=[];let canvas=null,profileIndex=0;
 const audit={proofs:null,trusted:null,entities:new Map(),commands:[],getUserMediaCalls:0,state:null,peerCount:0,selfId:''};
 const window={__overte:{connected:false},[kind==='ptt'?'__pttAudit':'__peopleAudit']:audit};
 window[kind==='ptt'?'__pttProofFactory':'__peopleProofFactory']=()=>({metadata:()=>({count:0}),retire(){events.push('retire-proof');}});
 window[kind==='ptt'?'__pttTrustedFactory':'__peopleTrustedFactory']=()=>{
  events.push('bind');if(!canvas)throw Error('Owned event binding unavailable');
  const binding={canvas,retired:false,retire(){this.retired=true;events.push('retire-binding');}};bindings.push(binding);return binding;
 };
 const context=vm.createContext({window});
 const invoke=(fn,...args)=>vm.runInContext('('+fn.toString()+')',context)(...args);
 const page={async goto(){events.push('goto');canvas=null;window.__overte.connected=false;},async evaluate(fn){return invoke(fn);},locator(selector){return{async fill(){events.push('fill:'+selector);},async click(){assert.equal(selector,'#join');events.push('join');assert(!audit.trusted,'No retired/current binding before a new join');canvas={generation:bindings.length+1};window.__overte.connected=true;audit.entities=new Map(Array.from({length:7},(_,i)=>[i,{id:i}]));audit.peerCount=1;audit.selfId='owned';audit.state={enabled:false,held:false,muted:true};}};},async waitForFunction(fn,arg,options){events.push('gate');assert.equal(options.timeout,90000);assert.equal(arg,undefined);if(refuseWait)throw Error('original-gate-refusal');assert(invoke(fn));}};
 const sandbox={assert,page,index,base:'owned',domain:'owned',names:['one','two'],privateControlProofs:new Map(),workerProfiles:async()=>[++profileIndex],tmpdir:()=>'',freshWorkerProfile:(before,after)=>after[0],profiles:[],runtimeCapture:async()=> 'exact-runtime-hash',qml:'pinned',baseline:null,baselineIdentity:x=>x};
 return{events,bindings,audit,sandbox,run:async(source=kind==='ptt'?pttBody:peopleBody)=>vm.runInNewContext(kind==='ptt'?source+';join()':'(async()=>{'+source+'})()',sandbox)};
}

for(const kind of ['ptt','people']){
 test(kind+' actual runner binds only after original connected/entity/state gate',async()=>{const f=fixture(kind);await f.run();assert.deepEqual(f.events.filter(e=>['join','gate','bind'].includes(e)),['join','gate','bind']);assert.equal(f.bindings.length,1);assert.equal(f.audit.getUserMediaCalls,0);assert.equal(f.audit.entities.size,7);});
 test(kind+' original prejoin factory negative control fails before physical join',async()=>{const f=fixture(kind);const init=kind==='ptt'?'a.proofs=window.__pttProofFactory();a.trusted=null;':'window.__peopleAudit.trusted=null;';const replacement=kind==='ptt'?'a.proofs=window.__pttProofFactory();a.trusted=window.__pttTrustedFactory();':'window.__peopleAudit.trusted=window.__peopleTrustedFactory();';const current=kind==='ptt'?pttBody:peopleBody;assert(current.includes(init));await assert.rejects(f.run(current.replace(init,replacement)),/Owned event binding unavailable/);assert(!f.events.includes('join'));assert.equal(f.audit.getUserMediaCalls,0);});
 test(kind+' failed original 90s gate never attaches control observers',async()=>{const f=fixture(kind,{refuseWait:true});await assert.rejects(f.run(),/original-gate-refusal/);assert.equal(f.bindings.length,0);assert.equal(f.audit.trusted,null);assert.equal(f.audit.getUserMediaCalls,0);});
}
test('PTT rejoin retires prior observer before joining and binds recreated production canvas',async()=>{const f=fixture('ptt');await f.run();const first=f.bindings[0];f.audit.entities.clear();await f.run();assert.equal(first.retired,true);assert.equal(f.bindings.length,2);assert.notEqual(first.canvas,f.bindings[1].canvas);assert.deepEqual(f.events.filter(e=>['join','gate','bind','retire-binding'].includes(e)),['join','gate','bind','retire-binding','join','gate','bind']);assert.equal(f.audit.getUserMediaCalls,0);});
test('People observer is attached only to controlling visitor, not reciprocal observer',async()=>{const f=fixture('people',{index:1});await f.run();assert.equal(f.bindings.length,0);assert.deepEqual(f.events.filter(e=>['join','gate','bind'].includes(e)),['join','gate']);assert.equal(f.audit.getUserMediaCalls,0);});
