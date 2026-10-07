// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Authored adapter contracts for genuine UI ordering; no native/audio execution claim.
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {setPeopleSyntheticMicrophone,reopenPeopleSyntheticTablet,runPeopleSyntheticAudioSuppression,projectPeopleAudioCheckpoint} from './integration/tablet-people-audio.mjs';
function pageFixture(index,{muteFailure=false,releaseFailure=false,partial=false}={}){
 const calls=[],state={visible:index===0,enabled:false,connected:true,app:'People',phase:null,generation:0,closed:false};
 const probe={begin(phase){state.phase=phase;state.generation++;return state.generation;},read(){return{phase:state.phase,generation:state.generation,samples:state.closed?0:partial?12000:48000,rate:48000,
  tone440:state.phase==='ignored'?0:index===1?.03:0,tone659:state.phase==='ignored'?0:index===0?.03:0,
  activeTracks:state.closed?0:state.enabled?1:0,openContexts:state.closed?0:state.enabled?1:0,phaseOutgoingNonzeroFrames:10,cleanupFailed:releaseFailure&&state.closed};},close(){calls.push('release');state.closed=true;}};
 const overte={get tabletVisible(){return state.visible;},get connected(){return state.connected;}};
 const context=vm.createContext({window:{__overte:overte,__peopleAudit:{frame:{tabletRect:{}}},__peopleSyntheticAudio:probe},document:{querySelector(selector){assert.equal(selector,'#microphone');return{getAttribute:()=>String(state.enabled)};}}});
 const run=(fn,arg)=>{context.__argument=arg;return vm.runInContext('('+fn.toString()+')(__argument)',context);};
 const page={state,calls,
  async bringToFront(){calls.push('foreground');},async evaluate(fn,arg){return run(fn,arg);},
  async waitForFunction(fn,arg){calls.push('wait');assert(run(fn,arg),'Authored observed UI state');},
  getByRole(role,options){assert.equal(role,'button');assert.deepEqual(options,{name:'Close tablet',exact:true});return{async click(){calls.push('close-tablet');assert(state.visible);state.visible=false;}};},
  locator(selector){assert(['#microphone','#tablet'].includes(selector));return{
   // The actual stock-Firefox adapter exposes evaluate, not locator.getAttribute.
   async evaluate(fn){assert.equal(selector,'#microphone');return fn({getAttribute(name){assert.equal(name,'aria-pressed');return String(state.enabled);}});},
   async click(){if(selector==='#tablet'){calls.push('open-tablet');assert(!state.visible);state.visible=true;state.app='Home';return;}
    calls.push(state.enabled?'mute':'enable');assert(!state.visible,'Modal Tablet must close before ordinary microphone click');
    if(state.enabled&&muteFailure)throw Error('Authored microphone mute refused');state.enabled=!state.enabled;}
  };}};
 return page;
}
const enterPeople=page=>async()=>{assert.equal(page.state.app,'Home');page.calls.push('enter-people');page.state.app='People';};
const waitFor=async read=>{const value=await read();if(value)return value;throw Error('Authored observed phase deadline');};
test('normal controls close the modal Tablet before microphone, re-enter People from real Home before action, then close again for mute',async()=>{
 const page=pageFixture(0);await setPeopleSyntheticMicrophone(page,true);
 assert.equal(page.state.visible,false);assert.equal(page.state.enabled,true);
 assert(page.calls.indexOf('close-tablet')<page.calls.indexOf('enable'));
 await reopenPeopleSyntheticTablet(page,enterPeople(page));assert.equal(page.state.app,'People');assert.equal(page.state.visible,true);
 await setPeopleSyntheticMicrophone(page,false);assert.equal(page.state.enabled,false);assert.equal(page.state.visible,false);
 assert.equal(page.calls.filter(v=>v==='close-tablet').length,2);
 assert.equal(page.calls.filter(v=>v==='enter-people').length,1);assert(!page.calls.includes('force'));
});
test('full authored cycle has genuine control order, both opposite tones and bounded scalar checkpoints, with original cleanup',async()=>{
 const pages=[pageFixture(0),pageFixture(1)],checkpoints=[];let ignored=false;
 const result=await runPeopleSyntheticAudioSuppression({pages,waitFor,onCheckpoint:r=>checkpoints.push(r),
  ignore:async()=>{await reopenPeopleSyntheticTablet(pages[0],enterPeople(pages[0]));assert.equal(pages[0].state.app,'People');ignored=true;},
  unignore:async()=>{await reopenPeopleSyntheticTablet(pages[0],enterPeople(pages[0]));assert(ignored);ignored=false;}});
 assert(result.completed);assert(result.cleanup.completed);assert.deepEqual(result.windows.map(row=>row.phase),['baseline','ignored','restored']);
 assert(checkpoints.some(row=>row.phase==='baseline'&&row.event==='accepted'&&row.visitorOrdinal===1&&row.tone659===.03));
 assert(checkpoints.some(row=>row.phase==='ignored'&&row.event==='accepted'&&row.visitorOrdinal===2&&row.tone440===0));
 assert(checkpoints.some(row=>row.phase==='cleanup'&&row.event==='complete'));assert(checkpoints.length<=128);
 for(const page of pages){assert.equal(page.state.enabled,false);assert.equal(page.state.visible,false);assert(page.state.closed);}
});
test('latest partial numeric window and separate cleanup failure survive while the primary exception remains identical',async()=>{
 const pages=[pageFixture(0,{partial:true,muteFailure:true}),pageFixture(1)],rows=[];
 const primary=Error('Authored baseline phase deadline');
 await assert.rejects(runPeopleSyntheticAudioSuppression({pages,onCheckpoint:row=>rows.push(row),ignore:async()=>{},unignore:async()=>{},
  waitFor:async(read,label)=>{const row=await read();if(row)return row;assert(label.includes('baseline'));throw primary;}}),error=>error===primary);
 assert(rows.some(row=>row.phase==='baseline'&&row.event==='failed'&&row.samples===12000&&row.category==='timeout'));
 assert(rows.some(row=>row.phase==='cleanup'&&row.event==='failed'&&row.category==='operation-refused'));
 assert(pages.every(page=>page.state.closed),'Fixture release must execute even when mute click fails');
});
test('ignore remains restored during failure cleanup and cleanup-only resource failure cannot silently pass',async()=>{
 const pages=[pageFixture(0,{releaseFailure:true}),pageFixture(1)],rows=[];let calls=0;
 const primary=Error('Authored ignore refused');
 await assert.rejects(runPeopleSyntheticAudioSuppression({pages,waitFor,onCheckpoint:row=>rows.push(row),
  ignore:async()=>{throw primary;},unignore:async()=>{calls++;}}),error=>error===primary);
 assert.equal(calls,1);assert(rows.some(row=>row.phase==='cleanup'&&row.category==='probe-cleanup-failed'));
 const cleanFail=[pageFixture(0,{releaseFailure:true}),pageFixture(1)];
 await assert.rejects(runPeopleSyntheticAudioSuppression({pages:cleanFail,waitFor,ignore:async()=>{},unignore:async()=>{}}),/cleanup failed/);
});
test('checkpoint projection rejects arbitrary phase/error text and exposes only fixed bounded scalar fields',()=>{
 const row=projectPeopleAudioCheckpoint('baseline','sample',1,{samples:1,tone440:NaN,tone659:Infinity,openContexts:3,participant:'private-id',url:'private-url',password:'private-text',connected:true});
 assert.equal(row.tone440,null);assert.equal(row.tone659,null);assert.equal(row.openContexts,null);assert(!JSON.stringify(row).includes('private'));
 assert.throws(()=>projectPeopleAudioCheckpoint('private-url','sample',1));assert.throws(()=>projectPeopleAudioCheckpoint('baseline','sample',1,null,'private-error'));
});
test('slow phase sampling stops at twelve partial rows per visitor but preserves the final sample when the original wait fails',async()=>{
 const pages=[pageFixture(0,{partial:true}),pageFixture(1)],rows=[];let reads=0;
 const primary=Error('Authored existing wait deadline');
 await assert.rejects(runPeopleSyntheticAudioSuppression({pages,onCheckpoint:row=>rows.push(row),ignore:async()=>{},unignore:async()=>{},
  waitFor:async(read,label)=>{if(label.includes('resources'))return read();for(let i=0;i<100;i++){reads++;await read();}throw primary;}}),error=>error===primary);
 assert.equal(reads,100);assert.equal(rows.filter(row=>row.phase==='baseline'&&row.event==='sample').length,12);
 assert(rows.some(row=>row.phase==='baseline'&&row.event==='failed'&&row.samples===12000));assert(rows.length<=128);
});
