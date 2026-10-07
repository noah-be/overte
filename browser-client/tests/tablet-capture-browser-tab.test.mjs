// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {captureRecordMatches} from './integration/tablet-capture-phase.mjs';
const frame={sequence:18,revision:1,navigationSequence:25};
const record=()=>({...frame,rootCount:1,uiEpoch:9,truncated:false,ready:true,awaiting:false,state:{active:true,controls:{echoCancellation:false},settings:{echoCancellation:false}},controls:[{kind:'native-tab',checked:true,enabled:true},{kind:'browser-tab',checked:false,enabled:true},{kind:'echoCancellation',checked:true,enabled:true}]});
const browser=()=>{const r=record();r.controls[0].checked=false;r.controls[1].checked=true;r.controls[2].checked=false;r.controls[2].enabled=false;return r;};
const original=await readFile(new URL('./fixtures/capture-before-browser-region-20261002.mjs.txt',import.meta.url),'utf8');
assert.equal(createHash('sha256').update(original).digest('hex'),'ef95eb1ce18f6cb450f1bb24b797775e18bdfd041b02223739df4c7f04f60dff');
const begin='return r.findLast(v=>',end="));},'Fresh displayed native capture readback',15000);}";
const predicate=original.slice(original.indexOf(begin)+begin.length,original.indexOf(end)+1);
assert(predicate.startsWith('v.sequence===f?.sequence'));
// Execute the exact old actual helper predicate, not a hand-written imitation.
const oldPredicate=new Function('v','f','expected','return '+predicate);
test('retained Native-tab/current-frame counterexample qualifies old helper but refuses Browser region',()=>{const r=record();assert(oldPredicate(r,frame,{}));assert.equal(r.controls[2].enabled,true);assert.equal(r.state.controls.echoCancellation,false);assert.equal(captureRecordMatches(r,frame),false);});
test('selected Browser region retains unsupported false controls and inactive permission evidence',()=>{const r=browser();assert(captureRecordMatches(r,frame));assert.equal(r.controls[2].enabled,r.state.controls.echoCancellation);r.state.active=false;assert(captureRecordMatches(r,frame));});
test('later Browser paint cannot qualify before that exact frame is displayed',()=>{const r=browser();r.sequence=19;assert.equal(captureRecordMatches(r,frame),false);assert(captureRecordMatches(r,{...frame,sequence:19}));assert.equal(captureRecordMatches(record(),{...frame,sequence:19}),false);});
test('revision/navigation/undrawn/ambiguous/wrong-region readiness refuses',()=>{for(const changes of [{revision:2},{navigationSequence:26},{uiEpoch:0},{rootCount:2},{truncated:true},{ready:false},{awaiting:true},{controls:[...browser().controls,{kind:'browser-tab',checked:true}]}])assert.equal(captureRecordMatches({...browser(),...changes},frame),false);for(const tab of ['native',null,'other'])assert.equal(captureRecordMatches(browser(),frame,{},tab),false);assert.equal(captureRecordMatches(browser(),null),false);});
test('explicit native departure still requires genuine selected Native region',()=>{assert(captureRecordMatches(record(),frame,{},'native'));assert.equal(captureRecordMatches(browser(),frame,{},'native'),false);assert.equal(captureRecordMatches(browser(),frame,{echoCancellation:true}),false);});
test('original painted/input/permissions/gain assertions and deadline remain intact',async()=>{const s=await readFile(new URL('./integration/tablet-capture-phase.mjs',import.meta.url),'utf8');assert(s.includes("},'Fresh displayed native capture readback',15000)"));assert(s.includes('assert.equal(control[0].enabled,r.state.controls[field])'));assert(s.includes("ledger.push({field,outcome:'unsupported-disabled'})"));assert(s.includes('await page.mouse.click(armed.x,armed.y)'));assert(s.includes('ratio>=.45&&ratio<=.55'));});
