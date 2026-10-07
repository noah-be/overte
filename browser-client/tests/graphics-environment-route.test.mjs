// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {BrowserGraphicsController} from '../src/browser-graphics-controller.ts';
import {BrowserGraphicsIntent} from '../src/browser-graphics-intent.ts';
import {TabletSession,validateTabletInput} from '../gateway/tablet.mjs';
import {parseTabletMessage} from '../src/tablet-protocol.ts';
import {validateGraphicsLocalChange,validateGraphicsApplied} from '../shared/browser-graphics-local.mjs';
const defaults={version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true};
const plain=value=>JSON.parse(JSON.stringify(value));
async function fixture(){
 let revision=7,active=true,now=0,settings={...defaults},sequence=0,applies=0,fail=false;
 const nativeQueue=[],browserQueue=[],ui=[],persisted=[];let handler;
 const context=vm.createContext({Messages:{subscribe(){},unsubscribe(){},messageReceived:{connect(fn){handler=fn;},disconnect(){handler=undefined;}},sendLocalMessage(channel,text){ui.push(JSON.parse(text));}}});
 vm.runInContext(await readFile(new URL('../gateway/native-browser-graphics.js',import.meta.url),'utf8'),context);
 const native=context.createBrowserGraphics({channel:'private-owned-channel',send:value=>nativeQueue.push(plain(value)),now:()=>now});
 const tablet=new TabletSession({framePath:'/nonexistent-owned-test/tablet.png',getRevision:()=>revision,isActive:()=>active,sendNative:value=>native.receive(value),sendBrowser:value=>browserQueue.push(value)});
 const target={snapshot:()=>({...settings}),apply(value){applies++;if(fail){settings={...settings,fieldOfView:value.fieldOfView};throw Error('Private driver failure');}settings={...value};}};
 const controller=new BrowserGraphicsController(target,value=>active&&value===revision,value=>persisted.push({...value}));
 const intent=new BrowserGraphicsIntent({current:()=>active,snapshot:target.snapshot,send:value=>tablet.receive({type:'tablet',sequence:++sequence,revision,...value})});
 function authority(next,allowed){intent.cancel();revision=next;active=allowed;controller.setAuthority(next,allowed);native.setAuthority(next,allowed);tablet.resetRevision();}
 async function flushNative(){while(nativeQueue.length){const value=nativeQueue.shift();await tablet.receiveNative({type:'tablet',revision,...value});}}
 function deliverBrowser(){while(browserQueue.length){const packet=parseTabletMessage(browserQueue.shift());assert(packet);if(packet.kind==='graphics'){if(packet.browserRequestId===undefined||intent.permits(packet)){const ack=controller.receive(packet,packet.revision);if(ack)tablet.receive({...ack,sequence:++sequence});}}else if(packet.kind==='graphicsApplied')intent.complete(packet);}}
 async function flush(){await flushNative();deliverBrowser();await flushNative();deliverBrowser();}
 function ready(){handler('private-owned-channel',JSON.stringify({kind:'ready'}),'own',true);}
 function close(){intent.dispose();controller.close();native.close();tablet.close();}
 authority(7,true);ready();await flush();
 return {intent,native,tablet,controller,ui,persisted,nativeQueue,browserQueue,target,flush,flushNative,deliverBrowser,authority,close,
  get settings(){return {...settings};},get applies(){return applies;},get revision(){return revision;},set fail(value){fail=value;},advance(ms){now+=ms;native.poll();},ready,
  emit(value){handler('private-owned-channel',JSON.stringify(value),'own',true);},send(value){tablet.receive({type:'tablet',sequence:++sequence,revision,...value});}};
}
test('suggestion uses genuine native request, ordinary browser target/persistence ACK, then fresh native state before completion',async()=>{
 const f=await fixture();try{
  assert.equal(f.ui.at(-1).ready,true);const result=f.intent.changeResolution(90);let completed=false;void result.then(()=>completed=true);
  assert.equal(f.applies,0);assert.equal(f.persisted.length,0);assert.equal(f.ui.at(-1).settings.resolutionPercent,100);
  await f.flushNative();assert.equal(f.browserQueue.length,1);assert.equal(f.browserQueue[0].browserRequestId,1);
  f.deliverBrowser();assert.equal(f.applies,1);assert.equal(f.settings.resolutionPercent,90);assert.equal(f.persisted[0].resolutionPercent,90);
  assert.equal(completed,false);assert.equal(f.ui.at(-1).settings.resolutionPercent,90);assert.equal(f.ui.at(-1).ready,true);
  await f.flushNative();f.deliverBrowser();assert.equal((await result).resolutionPercent,90);
  assert.equal(f.nativeQueue.length,0);assert.equal(f.browserQueue.length,0);
 }finally{f.close();}
});
test('cancelled tagged request never applies or persists; new intent uses monotonic ID and fresh ACK',async()=>{
 const f=await fixture();try{const first=f.intent.changeResolution(90);const rejected=assert.rejects(first,/cancelled/);await f.flushNative();f.intent.cancel();f.deliverBrowser();await rejected;
  assert.equal(f.applies,0);assert.equal(f.persisted.length,0);const next=f.intent.changeResolution(80);await f.flush();assert.equal((await next).resolutionPercent,80);assert.equal(f.applies,1);
 }finally{f.close();}
});
test('permission revision change prevents queued old request and cached native completion from applying',async()=>{
 const f=await fixture();try{const pending=f.intent.changeResolution(90);const rejected=assert.rejects(pending,/cancelled/);await f.flushNative();f.authority(8,false);f.deliverBrowser();await rejected;assert.equal(f.applies,0);
  await f.tablet.receiveNative({type:'tablet',revision:7,kind:'graphicsApplied',schemaVersion:1,browserRequestId:1,accepted:true,settings:{...defaults,resolutionPercent:90}});assert.equal(f.browserQueue.length,0);
  f.authority(9,true);f.ready();await f.flush();const next=f.intent.changeResolution(80);await f.flush();assert.equal((await next).resolutionPercent,80);
 }finally{f.close();}
});
test('ordinary native pending request refuses suggestion without changing effective state',async()=>{
 const f=await fixture();try{f.emit({kind:'change',field:'fieldOfView',value:90});const pending=f.intent.changeResolution(90);const rejected=assert.rejects(pending,/did not confirm/);await f.flush();await rejected;
  assert.equal(f.settings.fieldOfView,90);assert.equal(f.settings.resolutionPercent,100);assert.equal(f.applies,1);assert.equal(f.ui.at(-1).settings.fieldOfView,90);
 }finally{f.close();}
});
test('ordinary native untagged controls remain valid after confirmed suggestion',async()=>{
 const f=await fixture();try{const p=f.intent.changeResolution(80);await f.flush();await p;f.emit({kind:'change',field:'localLights',value:false});await f.flush();assert.equal(f.settings.localLights,false);assert.equal(f.settings.resolutionPercent,80);assert.equal(f.ui.at(-1).settings.localLights,false);assert.equal(f.persisted.length,2);
 }finally{f.close();}
});
test('native deadline rejects late ordinary ACK and confirms failure only, never stale cached suggestion',async()=>{
 const f=await fixture();try{const p=f.intent.changeResolution(90);const rejected=assert.rejects(p,/did not confirm/);await f.flushNative();f.advance(8000);f.deliverBrowser();await f.flushNative();f.deliverBrowser();await rejected;
  // The ordinary request may have applied before timeout but cannot be reported as confirmed.
  assert.equal(f.ui.at(-1).settings.resolutionPercent,100);assert.match(f.ui.at(-1).message,/8 seconds/);
 }finally{f.close();}
});
test('driver refusal goes through existing effective target ACK without leaking driver exception',async()=>{
 const f=await fixture();try{f.fail=true;const p=f.intent.changeResolution(90);const rejected=assert.rejects(p,/did not confirm/);await f.flush();await rejected;assert.equal(f.settings.resolutionPercent,100);assert.equal(f.persisted.length,0);assert.equal(f.ui.at(-1).settings.resolutionPercent,100);assert(!JSON.stringify(f.ui).includes('Private driver failure'));
 }finally{f.close();}
});
test('gateway bounds, stale revision, intent replay, wrong tag and close remain fail closed',async()=>{
 const f=await fixture();try{
  for(const value of [{schemaVersion:1,browserRequestId:1,field:'fieldOfView',value:90},{schemaVersion:1,browserRequestId:1,field:'resolutionPercent',value:25},{schemaVersion:1,browserRequestId:0,field:'resolutionPercent',value:90}])assert.throws(()=>validateGraphicsLocalChange(value));
  assert.throws(()=>f.tablet.receive({type:'tablet',sequence:2,revision:6,action:'graphicsChange',schemaVersion:1,browserRequestId:1,field:'resolutionPercent',value:90}),/Stale/);
  const p=f.intent.changeResolution(90);const rejected=assert.rejects(p,/cancelled/);await f.flushNative();const count=f.browserQueue.length;
  await f.tablet.receiveNative({type:'tablet',revision:7,kind:'graphics',schemaVersion:1,requestId:99,operation:'change',field:'resolutionPercent',value:90,browserRequestId:99});assert.equal(f.browserQueue.length,count);
  assert.throws(()=>f.send({action:'graphicsChange',schemaVersion:1,browserRequestId:1,field:'resolutionPercent',value:90}),/Repeated graphics intent/);
  f.close();f.deliverBrowser();await rejected;assert.equal(f.applies,0);assert.equal(f.tablet.graphicsLocalRequest,0);
 }finally{f.close();}
});
test('completion mismatch, stale ID and source getter failure cannot falsely report native confirmation',async()=>{
 let settings={...defaults},current=true,sent=[];const intent=new BrowserGraphicsIntent({current:()=>current,snapshot:()=>settings,send:value=>sent.push(value)});
 try{const p=intent.changeResolution(90);const rejected=assert.rejects(p,/did not confirm/);intent.complete({schemaVersion:1,browserRequestId:2,accepted:true,settings:{...defaults,resolutionPercent:90}});assert.equal(sent.length,1);intent.complete({schemaVersion:1,browserRequestId:1,accepted:true,settings:{...defaults,resolutionPercent:90}});await rejected;
  const next=intent.changeResolution(80);const cancelled=assert.rejects(next,/cancelled/);current=false;intent.complete({schemaVersion:1,browserRequestId:2,accepted:false});await cancelled;
 }finally{intent.dispose();}
});
test('completion and command validators retain only bounded schema values, never native envelope extras',()=>{
 const input={schemaVersion:1,browserRequestId:1,field:'resolutionPercent',value:90,privateValue:'do-not-forward'};
 assert(!('privateValue'in validateGraphicsLocalChange(input)));assert(!('privateValue'in validateTabletInput({type:'tablet',sequence:1,revision:1,action:'graphicsChange',...input})));
 assert.throws(()=>validateGraphicsApplied({schemaVersion:1,browserRequestId:1,accepted:true}));assert.throws(()=>validateGraphicsApplied({schemaVersion:1,browserRequestId:1,accepted:false,message:'x'.repeat(513)}));
 assert(!('privateValue'in validateGraphicsApplied({schemaVersion:1,browserRequestId:1,accepted:true,settings:defaults,privateValue:'do-not-forward'})));
});

test('tab hiding cancels a pending native request immediately and releases the visibility listener on dispose',async()=>{
 const listeners=new Set();let visibilityState='visible',applies=0;const sent=[];
 const doc={get visibilityState(){return visibilityState;},addEventListener(name,fn){assert.equal(name,'visibilitychange');listeners.add(fn);},removeEventListener(name,fn){listeners.delete(fn);}};
 const intent=new BrowserGraphicsIntent({document:doc,current:()=>true,snapshot:()=>({...defaults}),send:value=>sent.push(value)});
 const p=intent.changeResolution(90),rejected=assert.rejects(p,/cancelled/);visibilityState='hidden';for(const fn of listeners)fn();await rejected;
 assert.equal(sent.at(-1).action,'graphicsCancel');assert.equal(intent.permits({operation:'change',browserRequestId:1,field:'resolutionPercent',value:90}),false);
 await assert.rejects(intent.changeResolution(80),/unavailable/);intent.dispose();intent.dispose();assert.equal(listeners.size,0);assert.equal(applies,0);
});
test('current or effective target getter exceptions cancel completion and never leak exception messages',async()=>{
 for(const failing of ['current','snapshot']){let broken=false;const sent=[];
  const intent=new BrowserGraphicsIntent({current:()=>{if(broken&&failing==='current')throw Error('Private exception');return true;},snapshot:()=>{if(broken&&failing==='snapshot')throw Error('Private exception');return {...defaults};},send:value=>sent.push(value)});
  try{const p=intent.changeResolution(90),rejected=assert.rejects(p,/cancelled/);broken=true;intent.complete({schemaVersion:1,browserRequestId:1,accepted:true,settings:{...defaults,resolutionPercent:90}});await rejected;assert.equal(sent.at(-1).action,'graphicsCancel');}finally{intent.dispose();}
 }
});
