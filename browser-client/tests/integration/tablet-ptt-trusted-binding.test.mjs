// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFileSync} from 'node:fs';
import {pttProofQueueInstallerSource} from './tablet-ptt-proof-queue.mjs';
import {samplePttDisplayedControl,freshPttClickCoordinates} from './tablet-ptt-frame-sample.mjs';
import {assertPaintedPttControl,pttAuditBrowserBindingsSource,encodeValidatedPttRecords,parsePttAudit} from './tablet-ptt-audit.mjs';
import {createPeopleTrustedEventOracle} from './tablet-people-trusted-event-oracle.mjs';
import {pttTrustedBindingInstallerSource} from './tablet-ptt-trusted-binding.mjs';
const plain=v=>JSON.parse(JSON.stringify(v));
const makeFrame=n=>({sequence:n,revision:2,navigationSequence:3,width:480,height:706,surface:'tablet',tabletRect:{x:0,y:0,width:480,height:706},data:Buffer.from('owned PNG').toString('base64')});
function record(seq,{home=false,change=()=>{}}={}){const r={version:1,sequence:seq,revision:2,navigationSequence:3,scope:'native-desktop-ptt',nativeBuildVersion:'2026.04.1',nodes:80,truncated:false,audioRootCount:home?0:1,switchCount:home?0:1,audioButtonCount:home?1:0,native:{enabled:false,held:false,muted:true},audioButton:home?{enabled:true,rect:{x:100,y:150,width:129,height:129}}:null,control:home?null:{checked:false,enabled:true,rect:{x:100,y:150,width:40,height:16}}};change(r);return r;}
const tablet=readFileSync(new URL('../../src/tablet.ts',import.meta.url),'utf8');
function slice(a,b){assert.equal(tablet.split(a).length,2);return tablet.slice(tablet.indexOf(a),tablet.indexOf(b,tablet.indexOf(a)));}
let methods=slice('    private coordinates(','    get worldInputReady(')+slice('    private send(','    private show(')+slice('    private modifiers(','    private fit(');
// Exact signature-only erasure, supported without a new Node/TypeScript runtime requirement.
for(const [from,to] of [["private coordinates(event:MouseEvent):{x:number;y:number}","coordinates(event)"],["private clearPointer():void","clearPointer()"],["private pointer(event:'press'|'release'|'cancel'|'move',pointer:PointerEvent):void","pointer(event,pointer)"],["private send(value:Record<string,unknown>):void","send(value)"],["private modifiers(event:KeyboardEvent|MouseEvent):number","modifiers(event)"]]){assert.equal(methods.split(from).length,2);methods=methods.replace(from,to);}
const Actual=vm.runInNewContext('class Actual {\n'+methods+'\n};Actual;');
const downBody=slice("        this.canvas.addEventListener('pointerdown',event=>{","        this.canvas.addEventListener('pointerup'").split('event=>{')[1].split('},{signal});')[0],onDown=Function('event',downBody);
function fixture(createOracle=createPeopleTrustedEventOracle){
 const listeners=[],sent=[];let pixels=0,focus=0;
 const captures=new Set(),canvas={width:480,height:706,getBoundingClientRect:()=>({left:10,top:20,x:10,y:20,width:240,height:353}),setPointerCapture:id=>captures.add(id),hasPointerCapture:id=>captures.has(id),releasePointerCapture:id=>captures.delete(id),getContext:()=>({getImageData(x,y,w,h){pixels++;const data=new Uint8ClampedArray(w*h*4);for(let i=0;i<data.length;i+=4)data.set(i<data.length/2?[20,20,20,255]:[230,230,230,255],i);return {data};}})};
 const audit={navigation:3,frame:makeFrame(5),tabletState:{visible:true}},ctx={window:{__pttAudit:audit,__overte:{connected:true,tabletVisible:true}},AbortController,TextEncoder,atob:v=>Buffer.from(v,'base64').toString('binary'),document:{querySelector(selector){assert.equal(selector,'canvas[aria-label="Native tablet apps and dialogs"]');return canvas;},addEventListener(type,fn,options){assert.equal(options.capture,true);listeners.push({type,fn,options});}}};
 vm.runInNewContext(pttProofQueueInstallerSource(samplePttDisplayedControl,assertPaintedPttControl),ctx);audit.proofs=ctx.window.__pttProofFactory();
 vm.runInNewContext(pttTrustedBindingInstallerSource(pttAuditBrowserBindingsSource(),createOracle),ctx);audit.trusted=ctx.window.__pttTrustedFactory();
 const actual=new Actual();Object.assign(actual,{canvas,keyboard:{focus:()=>focus++},revision:2,displayedFrameSequence:5,navigationSequence:3,sequence:50,connected:true,visible:true,disposed:false,options:{send:m=>{sent.push(m);audit.trusted.wire(m);}}});
 const event=(up=false)=>({target:canvas,isTrusted:true,pointerId:7,button:0,buttons:up?0:1,clientX:66,clientY:98,shiftKey:false,ctrlKey:false,altKey:false,metaKey:false,preventDefault(){}});
 function dispatch(type,e){for(const row of listeners)if(row.type===type&&!row.options.signal.aborted)row.fn(e);}
 function setFrame(frame){audit.frame=frame;actual.displayedFrameSequence=frame.sequence;actual.revision=frame.revision;}
 const value={kind:'desktop-ptt',expected:false},records=rows=>encodeValidatedPttRecords(rows);
 function prepare(rows=[record(5)],v=value){const r=audit.trusted.prepare(v,records(rows));return {value:v,expected:{...r.point},result:r,text:records(rows)};}
 function arm(prepared){return audit.trusted.arm(prepared.value,prepared.text,prepared.expected);}
 function click(e=event()){dispatch('pointerdown',e);onDown.call(actual,e);const up={...e,buttons:0};dispatch('pointerup',up);actual.pointer('release',up);}
 return {ctx,audit,canvas,actual,listeners,sent,event,dispatch,setFrame,prepare,arm,click,records,pixels:()=>pixels,focus:()=>focus};
}

test('exact original parser and native PTT predicate serialize without broadening schema',()=>{const src=pttAuditBrowserBindingsSource();assert(src.includes(parsePttAudit.toString()));const f=fixture(),r=f.prepare();assert.equal(r.result.refusal,null);assert.equal(f.listeners.length,3);assert.equal(f.focus(),0);assert(r.expected.tabletRect);assert.equal(r.expected.surface,'tablet');});
test('old5/current6 physical event qualifies fresh6 only; original production sends exact6 press+release',()=>{const f=fixture(),p=f.prepare([record(5),record(6)]),armed=f.arm(p);f.setFrame(makeFrame(6));assert.equal(vm.runInNewContext('('+freshPttClickCoordinates.toString()+')',f.ctx)(f.canvas,p.expected).refusal,'frame-sequence-changed');f.click();const proof=f.audit.trusted.complete(armed.intentOrdinal);assert(proof.press.accepted&&proof.release.accepted);assert.equal(proof.press.frame.sequence,6);assert.equal(f.sent[0].frameSequence,6);assert.equal(f.sent[1].frameSequence,6);assert.equal(f.pixels(),2);});
test('current6 missing its original native record refuses same-looking controls',()=>{const f=fixture(),arm=f.arm(f.prepare());f.setFrame(makeFrame(6));f.click();assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));assert.equal(f.audit.trusted.readProofMetadata().length,0);});
test('same-navigation changed control/layout refuses despite genuine physical input',()=>{for(const change of [r=>r.control.rect.x++,r=>r.control.rect.width++]){const f=fixture(),arm=f.arm(f.prepare([record(5),record(6,{change})]));f.setFrame(makeFrame(6));f.click();assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));assert.equal(f.pixels(),1);}});
test('native enabled/held/muted/checkbox/rights contradictions do not become fresh PTT admission',()=>{for(const change of [r=>r.control.enabled=false,r=>r.control.checked=true,r=>r.native.enabled=true,r=>r.native.held=true,r=>r.native.muted=false,r=>r.truncated=true,r=>r.audioRootCount=2,r=>r.switchCount=2,r=>r.nativeBuildVersion=null]){const f=fixture(),arm=f.arm(f.prepare([record(5),record(6,{change})]));f.setFrame(makeFrame(6));f.click();assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));assert.equal(f.pixels(),1);}});
test('original AUDIO Home requires unique enabled native button and fresh original record',()=>{const f=fixture(),p=f.prepare([record(5,{home:true}),record(6,{home:true})],{kind:'audio-app'}),arm=f.arm(p);f.setFrame(makeFrame(6));f.click();assert.equal(f.audit.trusted.complete(arm.intentOrdinal).kind,'audio-app');for(const change of [r=>r.audioButton.enabled=false,r=>r.audioButtonCount=2,r=>r.audioRootCount=1]){const g=fixture();assert.equal(g.prepare([record(5,{home:true,change})],{kind:'audio-app'}).result.refusal,'native-control-not-qualified');}});
test('synthetic/foreign/cancelled physical inputs cannot certify unchanged outgoing application packets',()=>{for(const change of [e=>e.isTrusted=false,e=>e.target={}]){const f=fixture(),arm=f.arm(f.prepare()),e=f.event();change(e);f.click(e);assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));}const f=fixture(),arm=f.arm(f.prepare());f.dispatch('pointercancel',f.event());assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));});
test('navigation, connection, revision and hidden Tablet revoke prepared PTT click',()=>{for(const change of [f=>f.audit.navigation++,f=>f.setFrame({...makeFrame(6),revision:3}),f=>f.ctx.window.__overte.connected=false,f=>f.audit.tabletState.visible=false]){const f=fixture(),arm=f.arm(f.prepare());change(f);f.click();assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));assert.equal(f.audit.trusted.readProofMetadata().length,0);}});
test('actual press without release and mismatched release never prove native toggle',()=>{const f=fixture(),arm=f.arm(f.prepare()),e=f.event();f.dispatch('pointerdown',e);onDown.call(f.actual,e);assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));f.dispatch('pointerup',f.event(true));f.audit.trusted.wire({...f.sent[0],event:'release',sequence:52,buttons:0,frameSequence:4});assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));});
test('periodic new frame during held release retains original application gesture owner without requalifying another control',()=>{const f=fixture(),arm=f.arm(f.prepare()),e=f.event();f.dispatch('pointerdown',e);onDown.call(f.actual,e);f.setFrame(makeFrame(6));const up=f.event(true);f.dispatch('pointerup',up);f.actual.pointer('release',up);const proof=f.audit.trusted.complete(arm.intentOrdinal);assert.equal(proof.press.frame.sequence,5);assert.equal(proof.release.frame.sequence,5);assert.equal(f.sent[1].frameSequence,5);});
test('reentrant focus revocation never changes production input but prevents proof',()=>{const f=fixture(),arm=f.arm(f.prepare());f.actual.keyboard.focus=()=>f.audit.trusted.invalidate();f.click();assert.equal(f.sent.length,2);assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));});
test('bounded projection rejects private schema/count/UTF8 payload and preserves exact native records',()=>{assert.throws(()=>encodeValidatedPttRecords([record(5,{change:r=>r.private='forbidden'})]));assert.throws(()=>encodeValidatedPttRecords(Array.from({length:33},()=>record(5))));const f=fixture();assert.throws(()=>f.audit.trusted.prepare({kind:'audio-app'},'x'.repeat(32*(4096+256)+1)));assert.equal(parsePttAudit(f.records([record(5)])).length,1);});
test('retirement releases listeners/records/gesture and permits no stale new-session admission',()=>{const f=fixture(),arm=f.arm(f.prepare());f.click();assert(f.audit.trusted.complete(arm.intentOrdinal));f.audit.trusted.retire();f.audit.trusted.retire();assert(f.listeners.every(l=>l.options.signal.aborted));assert.equal(f.audit.trusted.diagnostics().recordCount,0);assert.throws(()=>f.arm(f.prepare()));});
const runner=readFileSync(new URL('./tablet-push-to-talk.mjs',import.meta.url),'utf8');
test('source retains original PTT trusted keys, native state, reciprocal tones, mute/blur, grant and owned cleanup predicates',()=>{for(const exact of ["e.code==='KeyT'&&e.isTrusted","Native released ACK cannot permit further browser PCM","Browser actual output must contain the native peer 997Hz synthetic input","Released PTT must silence synthetic input at real native output","document.hidden&&window.__pttAudit.events.blur>blur&&window.__pttAudit.events.hidden>hidden","getUserMediaCalls===1","'Current acknowledged painted native '+kind,30000","'Exact owned native profiles removed',12000","nativeAuthor.restore()"]){assert(runner.includes(exact),exact);}assert(runner.includes('await page.mouse.click(sampled.x,sampled.y)'));assert(runner.includes('trusted.complete(id)'));assert(!runner.includes('freshPttClickCoordinates'));assert(tablet.includes('frameSequence:held?.sequence??this.displayedFrameSequence'));});
test('passive binding and serialization cannot dispatch input, mutate focus/DOM/ACK or replace ordinary viewport/context ownership',()=>{const source=readFileSync(new URL('./tablet-ptt-trusted-binding.mjs',import.meta.url),'utf8');for(const bad of ['dispatchEvent(','preventDefault(','stopPropagation(','setPointerCapture(','.focus(','.send(','.click(','.value='])assert(!source.includes(bad));assert(source.includes('capture:true'));assert(runner.includes('openActualPttChromium('));assert(runner.includes('a.trusted?.wire(m)'));assert(runner.includes('a.navigation=m.sequence'));assert(runner.includes('a.trusted?.retire()'));});
test('actual post-effect flush adopts event witnesses in exact sorted ownership order and releases only after0600 exclusive writes',async()=>{
 const f=fixture(),prepared=f.prepare([record(5),record(6)]),arm=f.arm(prepared);f.setFrame(makeFrame(6));f.click();f.audit.trusted.complete(arm.intentOrdinal);
 const later=f.audit.proofs.sample(f.canvas,{...makeFrame(6),rect:{x:100,y:150,width:40,height:16}}),ledger=new Map();
 const metadata=p=>({file:'owned-'+p.proofOrdinal+'.png',frame:plain(p.frame),canvas:plain(p.canvas),image:plain(p.image)});
 ledger.set(prepared.result.sample.proofOrdinal,metadata(prepared.result.sample));ledger.set(later.proofOrdinal,metadata(later));
 const body=runner.slice(runner.indexOf('async function flushControlProofs'),runner.indexOf('async function checkpoint'));
 const page={async evaluate(fn,arg){const value=vm.runInNewContext('('+fn.toString()+')',f.ctx)(arg);return value===undefined?undefined:plain(value);}},writes=[];
 const flush=Function('assert','page','privateControlProofs','assertPaintedPttControl','Buffer','writeFile','path','directory',body+'\nreturn flushControlProofs;')(assert,page,ledger,assertPaintedPttControl,Buffer,async(file,png,options)=>{assert.equal(ledger.size>0,true);writes.push({file,png,options});},{join:(...p)=>p.join('/')},'owned-evidence');
 await flush();assert.equal(writes.length,3);assert(writes.every(w=>w.options.flag==='wx'&&w.options.mode===0o600));assert.equal(ledger.size,0);assert.equal(f.audit.proofs.metadata().bytes,0);assert.equal(f.audit.trusted.readProofMetadata().length,0);
});
test('application mismatched coordinates/buttons/modifiers cannot turn an observed press into a valid click',()=>{for(const change of [m=>m.x+=.1,m=>m.buttons=0,m=>m.modifiers=1]){const f=fixture(),arm=f.arm(f.prepare()),e=f.event();f.dispatch('pointerdown',e);const fake={type:'tablet',action:'input',event:'press',sequence:51,revision:2,frameSequence:5,x:(e.clientX-10)/240,y:(e.clientY-20)/353,button:0,buttons:1,modifiers:0};change(fake);f.audit.trusted.wire(fake);assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));}});
test('unchanged opaque/contrast pixel oracle refuses blank current event and records no retained event witness',()=>{const f=fixture(),arm=f.arm(f.prepare());f.canvas.getContext=()=>({getImageData:(x,y,w,h)=>({data:new Uint8ClampedArray(w*h*4).fill(255)})});f.click();assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));assert.equal(f.audit.trusted.readProofMetadata().length,0);});

test('actual raw event metadata preserves exact retained frame key presence without JSON erasure',()=>{
 const f=fixture(),arm=f.arm(f.prepare());f.click();f.audit.trusted.complete(arm.intentOrdinal);
 const row=f.audit.trusted.readProofMetadata()[0],full=f.audit.proofs.read(row.proofOrdinal);
 assert.equal(Object.hasOwn(full.frame,'tabletRect'),false);assert.equal(Object.hasOwn(row.frame,'tabletRect'),false);
 assert.deepEqual(Reflect.ownKeys(row.frame),Reflect.ownKeys(full.frame));assert.deepEqual(row.frame,full.frame);
 const original={...full.frame,tabletRect:undefined};assert.equal(Object.hasOwn(original,'tabletRect'),true);
 assert.notDeepEqual(Reflect.ownKeys(original),Reflect.ownKeys(full.frame),'Original undefined insertion changes the full-frame witness');
});

test('passive actual event diagnostics retain only fixed bounded fields without accepting refused pointer',()=>{
 const f=fixture(),arm=f.arm(f.prepare()),e={...f.event(),pointerId:-1,isPrimary:true,pointerType:'mouse',secret:'private',clientX:66,clientY:98};f.click(e);
 assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));const d=f.audit.trusted.diagnostics(),row=d.pointerEvents[0];
 assert.deepEqual(Object.keys(row),['kind','targetSame','isTrusted','button','buttons','pointerId','isPrimary','pointerType']);
 assert.equal(row.pointerId,-1);assert.equal(row.isPrimary,true);assert.equal(row.pointerType,'mouse');assert.equal(row.targetSame,true);assert.equal(row.isTrusted,true);
 assert.equal(d.failures['trusted-primary-event-required'],1);assert(!JSON.stringify(d).includes('private'));
 row.pointerId=99;assert.equal(f.audit.trusted.diagnostics().pointerEvents[0].pointerId,-1);
 for(let n=0;n<40;n++)f.dispatch('pointerdown',{...e,target:{},pointerType:'private'});
 assert.equal(f.audit.trusted.diagnostics().pointerEvents.length,32);assert.equal(f.audit.trusted.diagnostics().pointerEvents.at(-1).pointerType,'unknown');
 f.audit.trusted.retire();assert.equal(f.audit.trusted.diagnostics().pointerEvents.length,0);
});

test('actual permitted nonnegative WebIDL mouse IDs preserve painted proof and exact original production press/release',()=>{
 for(const pointerId of [0,1,2147483647]){const f=fixture(),arm=f.arm(f.prepare()),e={...f.event(),pointerId,isPrimary:true,pointerType:'mouse'};f.click(e);
  const proof=f.audit.trusted.complete(arm.intentOrdinal);assert.equal(proof.press.accepted,true);assert.equal(proof.release.accepted,true);
  assert.equal(proof.press.frame.sequence,5);assert.equal(f.sent.length,2);assert.equal(f.sent[0].frameSequence,5);assert.equal(f.sent[1].frameSequence,5);assert.equal(f.pixels(),2);
 }
});
test('actual original positive-only oracle counterfactual refuses the proven primary mouse zero',()=>{
 const now=createPeopleTrustedEventOracle.toString(),current='!(Number.isInteger(event.pointerId)&&event.pointerId>=0&&event.pointerId<=2147483647)';
 assert.equal(now.split(current).length,2);const original=vm.runInNewContext('('+now.replace(current,'!integer(event.pointerId)')+')');
 const f=fixture(original),arm=f.arm(f.prepare());f.click({...f.event(),pointerId:0,isPrimary:true,pointerType:'mouse'});
 assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));assert.equal(f.audit.trusted.diagnostics().failures['trusted-primary-event-required'],1);assert.equal(f.audit.trusted.readProofMetadata().length,0);
});
test('reserved nonpointing and out-of-range/noninteger IDs cannot qualify unchanged native-control proof',()=>{
 for(const pointerId of [-1,-2,.5,NaN,Infinity,2147483648,Number.MAX_SAFE_INTEGER]){const f=fixture(),arm=f.arm(f.prepare());f.click({...f.event(),pointerId,isPrimary:true,pointerType:'mouse'});assert.throws(()=>f.audit.trusted.complete(arm.intentOrdinal));assert.equal(f.audit.trusted.readProofMetadata().length,0);}
});

// The added world-input methods are genuine production source, not pointer
// fixture methods. Select each bounded pointer/send region without erasing
// unrelated TypeScript or changing any selected production method body.
test('old broad fixture slice reproduces the typed World-X getter import failure',()=>{
 const world=slice('    get worldInputReady(','    private send(');assert.equal(methods.split('    send(value)').length,2);
 const original=methods.replace('    send(value)',world+'    send(value)');
 assert(original.includes('get worldInputReady():boolean'));
 assert.throws(()=>vm.runInNewContext('class Original {\n'+original+'\n};Original;'),{name:'SyntaxError',message:/Unexpected token ':'/});
});
test('bounded selected methods exclude only the exact intervening World-X source region',()=>{
 const world=slice('    get worldInputReady(','    private send(');
 const old=slice('    private coordinates(','    private show(')+slice('    private modifiers(','    private fit(');
 const selected=slice('    private coordinates(','    get worldInputReady(')+slice('    private send(','    private show(')+slice('    private modifiers(','    private fit(');
 assert.equal(old.split(world).length,2);assert.equal(old.replace(world,''),selected);
 assert(!methods.includes('get worldInputReady('));assert(!methods.includes('worldInputFocus('));assert(!methods.includes('worldKey(event:'));
 assert(world.includes('event.isComposing||event.defaultPrevented'));assert(world.includes("key:'x'"));
 assert.equal(typeof Actual.prototype.pointer,'function');assert.equal(typeof Actual.prototype.send,'function');assert.equal(typeof Actual.prototype.coordinates,'function');
});
