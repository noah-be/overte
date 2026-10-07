// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('./native-eco-probe.js',import.meta.url),'utf8');
function fixture(){
 let now=1780300000000,interval,ending;const timers=[],records=[],setters=[];
 const state={profile:2,preset:3,regime:2,connected:true,href:'hifi://127.0.0.2:45102/',haze:true,angle:.04,targetLOD:40};
 const Render={getRenderMethod:()=>0,getShadowsEnabled:()=>false,getHazeEnabled:()=>state.haze,getBloomEnabled:()=>true,getAmbientOcclusionEnabled:()=>false,getLocalLightingEnabled:()=>true,getProceduralMaterialsEnabled:()=>true,getAntialiasingMode:()=>1,getViewportResolutionScale:()=>1,getVerticalFieldOfView:()=>45,getCameraClippingEnabled:()=>true};
 const LODManager={worldDetailQuality:1,automaticLODAdjust:true,get lodAngleDeg(){return state.angle;},get lodTargetFPS(){return Math.min(state.targetLOD,state.profile===0?[10,10,5,2][state.regime]:60);}};
 const Performance={getPerformancePreset:()=>state.preset,getRefreshRateProfile:()=>state.profile,getRefreshRateRegime:()=>state.regime,getActiveRefreshRate:()=>state.profile===0?[20,10,5,2][state.regime]:60,
  setRefreshRateProfile(value){assert([0,1,2].includes(value));setters.push(value);state.profile=value;}};
 const context=vm.createContext({Date:{now:()=>now},About:{buildVersion:'2026.04.1'},Performance,Render,LODManager,
  location:{get isConnected(){return state.connected;},get href(){return state.href;}},
  print(line){assert(line.startsWith('OVERTE_BROWSER_NATIVE_ECO '));records.push(JSON.parse(line.slice('OVERTE_BROWSER_NATIVE_ECO '.length)));},
  Script:{setInterval(callback){interval=callback;return 1;},clearInterval(){interval=undefined;},setTimeout(callback,ms){assert.equal(ms,5000);timers.push(callback);return timers.length;},scriptEnding:{connect(callback){ending=callback;}}}});
 vm.runInContext(source,context);
 return {state,Render,records,setters,context,step(ms=250){now+=ms;interval?.();},warm(){this.step();this.step(10000);},timeout(){now+=5000;assert(timers.length);timers.shift()();},end(){ending();}};
}
test('actual native probe waits for ordinary startup then applies only valid ECO and restores the original profile',()=>{
 const f=fixture();f.step();assert.equal(f.records.length,0);assert.deepEqual(f.setters,[]);f.step(10000);
 assert.deepEqual(f.records.map(r=>r.phase),['baseline']);f.timeout();assert.deepEqual(f.setters,[0]);f.timeout();assert.deepEqual(f.setters,[0,2]);
 assert.deepEqual(f.records.map(r=>r.phase),['baseline','baselineEnd','eco','ecoEnd','restored']);
 for(const record of f.records)assert.deepEqual(record.quality,f.records[0].quality);
 assert.equal(f.records[0].dynamicLOD.targetFPS,40);assert.equal(f.records[2].dynamicLOD.targetFPS,5);
 assert.equal(f.records[2].targetHz,5);f.end();assert.deepEqual(f.setters,[0,2]);
});
test('startup disconnected and unknown preset cannot trigger ECO; wrong domain refuses rather than altering an unrelated participant',()=>{
 for(const field of ['connected','regime','preset']){const f=fixture();f.state[field]=field==='connected'?false:field==='regime'?4:0;f.step(30000);assert.equal(f.records.length,0);assert.deepEqual(f.setters,[]);f.end();}
 const wrong=fixture();wrong.state.href='hifi://unrelated.invalid/';wrong.warm();assert.equal(wrong.records[0].phase,'error');assert.deepEqual(wrong.setters,[]);assert.equal(JSON.stringify(wrong.records).includes('unrelated.invalid'),false);
});
test('native Render quality mutation is a real failed experiment; restore never calls any graphics or LOD setter',()=>{
 const f=fixture();f.warm();f.state.haze=false;f.timeout();assert.deepEqual(f.records.map(r=>r.phase),['baseline','error']);assert.deepEqual(f.setters,[]);
 const g=fixture();g.warm();g.timeout();g.state.haze=false;g.timeout();assert(g.records.some(r=>r.phase==='error'));assert(g.records.some(r=>r.phase==='restoreError'));assert.deepEqual(g.setters,[0,2]);
});
test('revocation or changing refresh regime prevents continuing the A B observation and restores valid original profile',()=>{
 for(const field of ['connected','regime']){const f=fixture();f.warm();f.timeout();f.state[field]=field==='connected'?false:1;f.timeout();assert(f.records.some(r=>r.phase==='error'));assert.deepEqual(f.setters,[0,2]);}
});
test('scriptEnding restores only the original valid profile after ECO and is idempotent',()=>{
 const f=fixture();f.warm();f.timeout();f.end();f.end();assert.deepEqual(f.setters,[0,2]);assert.equal(f.records.at(-1).phase,'restored');
 const never=fixture();never.end();assert.deepEqual(never.setters,[]);
});
test('missing or malformed native getter fails explicitly without publishing exception values',()=>{
 for(const getter of [()=>undefined,()=>{throw Error('/operator/private/device-name');}]){const f=fixture();f.Render.getHazeEnabled=getter;f.warm();assert.equal(f.records[0].phase,'error');assert.equal(JSON.stringify(f.records).includes('operator'),false);assert.deepEqual(f.setters,[]);}
 const custom=fixture();custom.state.preset=5;custom.warm();assert.equal(custom.records[0].phase,'error');assert.deepEqual(custom.setters,[]);
});
test('automatic LOD angle evolution is observed without falsely claiming frozen native detail',()=>{
 const f=fixture();f.warm();f.state.angle=.02;f.timeout();f.state.angle=.07;f.timeout();assert.equal(f.records.length,5);assert.equal(f.records[0].dynamicLOD.angleDeg,.04);assert.equal(f.records[3].dynamicLOD.angleDeg,.07);
});
