// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {readFileSync} from 'node:fs';import {createHash} from 'node:crypto';import {runInNewContext} from 'node:vm';import test from 'node:test';import assert from 'node:assert/strict';
import {readCaptureV6History} from './integration/capture-lookahead-source-fixture.mjs';
const before=(await readCaptureV6History()).files['src/world.ts'].source;
const hunk=JSON.parse(readFileSync(new URL('./fixtures/world-owned-escape-hunk.json',import.meta.url)));
assert.equal(before.split(hunk.before).length,2);const after=before.replace(hunk.before,hunk.after);
const current=readFileSync(new URL('../src/world.ts',import.meta.url),'utf8');
const controls=s=>s.slice(s.indexOf('  private installControls(): void {'),s.indexOf('\n  private look',s.indexOf('  private installControls(): void {')));
assert.equal(controls(current),controls(after),'Actual current installControls must equal the qualified one-hunk method');
const hash=s=>createHash('sha256').update(s).digest('hex');
function setup(source=after) {
 const abort=new AbortController();
 class Target { listeners=new Map(); addEventListener(kind,fn,options){const rows=this.listeners.get(kind)||[];rows.push({fn,signal:options?.signal});this.listeners.set(kind,rows);} dispatch(kind,event){for(const row of this.listeners.get(kind)||[])if(!row.signal?.aborted)row.fn(event);} }
 class Input{};class TextArea{};class Select{};class Button{};class Pointer{};
 const window=new Target(),document=new Target(),canvas=new Target();
 let exits=0,resets=0,interactions=0,prevented=0;
 Object.assign(document,{activeElement:canvas,pointerLockElement:canvas,hidden:false,hasFocus:()=>true,exitPointerLock:()=>{exits++;document.pointerLockElement=null;}});
 const touchMove={x:.8,y:.2,set(x,y){this.x=x;this.y=y;return this;}};
 const world={abort,canvas,enabled:true,inputEnabled:true,disposed:false,keys:new Set(['KeyW','ShiftLeft']),touchMove,touchOrigin:{x:1},touchLast:{x:2},simulationClock:{reset(){resets++;}},thirdPerson:false,self:{visible:false,userData:{shadersReady:true}},interact(){interactions++;}};
 const start=source.indexOf('  private installControls(): void {')+'  private installControls(): void {'.length;
 const end=source.indexOf('\n  private look',start);
 const body=source.slice(start,end).replace(/\n  }\s*$/,'');
 const fn=runInNewContext('(function(){'+body+'})',{window,document,HTMLInputElement:Input,HTMLTextAreaElement:TextArea,HTMLSelectElement:Select,HTMLButtonElement:Button,PointerEvent:Pointer,THREE:{}});
 fn.call(world);
 const event={code:'Escape',key:'Escape',isTrusted:true,repeat:false,isComposing:false,defaultPrevented:false,ctrlKey:false,metaKey:false,altKey:false,shiftKey:false,target:canvas,preventDefault(){prevented++;this.defaultPrevented=true;}};
 return {abort,window,document,canvas,world,event,Input,dispatch(){window.dispatch('keydown',event);},counts:()=>({exits,resets,interactions,prevented})};
}
test('original actual controls do not release on Escape; candidate clears all input and uses normal product API',()=>{const old=setup(before);old.dispatch();assert.equal(old.counts().exits,0);const s=setup();s.dispatch();assert.deepEqual(s.counts(),{exits:1,resets:1,interactions:0,prevented:1});assert.equal(s.world.keys.size,0);assert.deepEqual([s.world.touchMove.x,s.world.touchMove.y],[0,0]);assert.equal(s.world.touchOrigin,undefined);assert.equal(s.world.touchLast,undefined);s.dispatch();assert.equal(s.counts().exits,1);});
for(const field of ['repeat','isComposing','defaultPrevented','ctrlKey','metaKey','altKey','shiftKey'])test('refuses '+field,()=>{const s=setup();s.event[field]=true;s.dispatch();assert.equal(s.counts().exits,0);assert.equal(s.world.keys.size,2);});
for(const [name,change] of [
 ['untrusted',s=>s.event.isTrusted=false],['wrong-key',s=>s.event.key='x'],['wrong-code',s=>s.event.code='KeyX'],['foreign-target',s=>s.event.target={}],['editable-target',s=>s.event.target=new s.Input()],['foreign-active',s=>s.document.activeElement={}],['hidden',s=>s.document.hidden=true],['unfocused',s=>s.document.hasFocus=()=>false],['disabled-world',s=>s.world.enabled=false],['disabled-input',s=>s.world.inputEnabled=false],['disposed',s=>s.world.disposed=true],['aborted',s=>s.abort.abort()],['foreign-pointer',s=>s.document.pointerLockElement={}],['no-pointer',s=>s.document.pointerLockElement=null]
])test('refuses '+name,()=>{const s=setup();change(s);s.dispatch();assert.equal(s.counts().exits,0);});
test('original movement, interaction and camera keys remain handled by the same actual method',()=>{const s=setup();s.world.keys.clear();Object.assign(s.event,{code:'KeyW',key:'w'});s.dispatch();assert(s.world.keys.has('KeyW'));Object.assign(s.event,{code:'KeyE',key:'e',defaultPrevented:false});s.dispatch();assert.equal(s.counts().interactions,1);Object.assign(s.event,{code:'KeyV',key:'v',defaultPrevented:false});s.dispatch();assert.equal(s.world.thirdPerson,true);assert.equal(s.world.self.visible,true);});
test('abort retires original listeners and owned Escape listener together',()=>{const s=setup();s.abort.abort();s.dispatch();s.window.dispatch('blur',{});assert.deepEqual(s.counts(),{exits:0,resets:0,interactions:0,prevented:0});});
test('exit failure is not swallowed or retried',()=>{const s=setup();const failure=new Error('owned API failure');s.document.exitPointerLock=()=>{throw failure;};assert.throws(()=>s.dispatch(),error=>error===failure);assert.equal(s.counts().resets,1);});
test('exactly one hunk strips to reviewed original source',()=>{assert.equal(hash(before),'c02931412d89d91650cf9bf185e8aaaa9ad3c120fc07a159d770761c84839fa7');assert.equal(after.split(hunk.after).length,2);assert.equal(after.replace(hunk.after,hunk.before),before);});
