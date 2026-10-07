// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {runInNewContext} from 'node:vm';import {readFileSync} from 'node:fs';
import {collectHubLoadedModelCohortCensus} from './integration/hub-loaded-model-cohort-census.mjs';
function report(){return{version:2,partial:false,elapsedMs:10,
 modelCohort:{scope:'captured-static-loaded-Model-cohort',maximumSelectedOwners:64,selectedOwners:2,eligibleAtCapture:293,modelOwnersAtCapture:294,selectionPartial:true,wholeWorldCoverage:false,sourcePreparationMs:2},
 bounds:{maximumOwners:1024,maximumNodes:16384,maximumParts:8192,maximumBytes:67108864,maximumMetadataBytes:2097152},
 counts:{owners:2,nodes:2,meshes:2,drawParts:2,candidateParts:2,triangles:2,geometryBytesRead:72,metadataBytes:1000,textureBindings:1},
 resources:{geometryIdentities:2,geometryByteClasses:1,materialIdentities:1,textureIdentities:1,sourceIdentities:1,sharedSources:0,samplerSourceBindings:1},
 scheduling:{taskSlices:3,totalCpuMs:4,maximumTaskSliceMs:2,wallMs:10,requestedSliceMs:4,maximumTotalCpuMs:1500,maximumWallMs:5000},
 reasons:{},hooks:{default:1},alphaFlags:{'private-avatar-url-token':1},
 exactGeometryAndMaterialIdentity:{groups:1,members:2,sourceOnlyDrawReductionUpperBound:1,independentlyLoadedGeometryGroups:1,independentMaterialGroups:0},
 exactGeometryAndAuditedMaterialValues:{groups:1,members:2,sourceOnlyDrawReductionUpperBound:1,independentlyLoadedGeometryGroups:1,independentMaterialGroups:0}};}
function fixture(raw=report()){
 let calls=0,at=100;const timers=[];const api={connected:true,drawModelCohortAsync:()=>{calls++;return Promise.resolve(raw);}};
 const context={window:{__overte:api},Date:{now:()=>++at},setTimeout(callback,milliseconds){const timer={callback,milliseconds,cleared:false};timers.push(timer);return timer;},clearTimeout(timer){if(timer)timer.cleared=true;}};
 const collect=runInNewContext('('+collectHubLoadedModelCohortCensus.toString()+')',context);
 return{collect,api,context,timers,calls:()=>calls};
}
test('exact page-serialized collector preserves bounded groups and strips all identity/string payload extras',async()=>{
 const raw=report();raw.modelCohort.extra='private-owner';raw.scope='private-domain';raw.extra='private-credentials';raw.counts.avatarID='private-uuid';raw.resources.address='private-url';raw.unresolved=['private-path'];
 const f=fixture(raw),out=await f.collect(1);assert.equal(out.admissionOrdinal,1);assert.equal(out.data.exactGeometryAndAuditedMaterialValues.members,2);assert.equal(out.data.counts.owners,2);assert.equal(out.data.alphaFlagClasses,1);assert.equal(out.data.alphaFlagMaterials,1);assert(!JSON.stringify(out).includes('private'));assert.equal(out.data.partial,false);assert.equal(out.data.modelCohort.wholeWorldCoverage,false);assert.equal(out.data.modelCohort.selectionPartial,true);assert.equal(out.data.modelCohort.selectedOwners,2);assert.equal(f.calls(),1);assert(f.timers.every(value=>value.cleared));
});
test('one explicit call per admitted ordinal and no duplicate retry, including failed attempts',async()=>{
 const f=fixture();await f.collect(1);await assert.rejects(f.collect(1),/already attempted/);await f.collect(2);assert.equal(f.calls(),2);await assert.rejects(f.collect(3),/Invalid async census admission ordinal/);assert.equal(f.calls(),2);
 const failed=fixture();failed.api.drawModelCohortAsync=()=>Promise.reject(Error('private-native-path'));await assert.rejects(failed.collect(1),error=>error.message==='Connected async draw census did not produce a valid bounded diagnostic');await assert.rejects(failed.collect(1),/already attempted/);assert(failed.timers.every(value=>value.cleared));
});
test('a valid partial coverage report stays partial with its actual counts and fixed refusal reason',async()=>{
 const raw=report();raw.partial=true;raw.reasons={'metadata-byte-budget':1};for(const key of ['exactGeometryAndMaterialIdentity','exactGeometryAndAuditedMaterialValues'])for(const field of Object.keys(raw[key]))raw[key][field]=0;
 const f=fixture(raw),out=await f.collect(1);assert.equal(out.data.partial,true);assert.equal(out.data.counts.owners,2);assert.equal(out.data.reasons['metadata-byte-budget'],1);assert.equal(out.data.exactGeometryAndMaterialIdentity.groups,0);
});
test('malformed enums/counts/groups and foreign reason strings are refused without reflected text',async()=>{
 const changes=[r=>r.version=1,r=>r.modelCohort.wholeWorldCoverage=true,r=>r.modelCohort.scope='private',r=>r.modelCohort.selectedOwners=65,r=>r.modelCohort.selectionPartial=false,r=>r.modelCohort.sourcePreparationMs=Infinity,r=>r.scheduling.maximumWallMs=5001,r=>r.reasons={'private-domain-address':1},r=>r.hooks={'private-user':1},r=>r.scheduling.maximumTotalCpuMs=2001,r=>r.counts.metadataBytes=2097153,r=>r.counts.geometryBytesRead=67108865,r=>r.counts.owners=1025,r=>r.exactGeometryAndMaterialIdentity.members=3,r=>r.exactGeometryAndAuditedMaterialValues.sourceOnlyDrawReductionUpperBound=2,r=>r.alphaFlags={secret:'private-path'}];
 for(const change of changes){const raw=report();change(raw);const f=fixture(raw);await assert.rejects(f.collect(1),error=>error.message==='Connected async draw census did not produce a valid bounded diagnostic');assert(f.timers.every(value=>value.cleared));}
});
test('slice-budget terminal censorship allows its counted cleanup turn, not a complete1025-turn claim',async()=>{
 const raw=report();raw.scheduling.taskSlices=1025;raw.partial=true;raw.reasons={'slice-count-budget':1};for(const key of ['exactGeometryAndMaterialIdentity','exactGeometryAndAuditedMaterialValues'])for(const field of Object.keys(raw[key]))raw[key][field]=0;
 assert.equal((await fixture(raw).collect(1)).data.scheduling.taskSlices,1025);
 raw.partial=false;await assert.rejects(fixture(raw).collect(1),/valid bounded diagnostic/);
});
test('missing bundle hook or disconnected generation never invokes a census',async()=>{
 const f=fixture();f.api.connected=false;await assert.rejects(f.collect(1),/unavailable/);assert.equal(f.calls(),0);f.api.connected=true;f.api.drawModelCohortAsync=undefined;await assert.rejects(f.collect(1),/unavailable/);assert.equal(f.calls(),0);
});
test('disconnection during the one call and a genuinely hung hook fail with fixed errors and clear owned deadlines',async()=>{
 const disconnected=fixture();disconnected.api.drawModelCohortAsync=async()=>{disconnected.api.connected=false;return report();};await assert.rejects(disconnected.collect(1),/valid bounded diagnostic/);assert(disconnected.timers.every(value=>value.cleared));
 const hung=fixture();let lateReject;hung.api.drawModelCohortAsync=()=>new Promise((_,reject)=>lateReject=reject);const pending=hung.collect(1);await Promise.resolve();assert.equal(hung.timers[0].milliseconds,6000);hung.timers[0].callback();await assert.rejects(pending,/valid bounded diagnostic/);assert(hung.timers.every(value=>value.cleared));lateReject(Error('private-late-error'));await Promise.resolve();
});
test('Hub harness invokes each diagnostic only after stored performance/native/movement gates and before its leave',()=>{
 const source=readFileSync(new URL('./integration/public-hub.mjs',import.meta.url),'utf8');
 const first=source.indexOf('page.evaluate(collectHubLoadedModelCohortCensus,1)'),second=source.indexOf('page.evaluate(collectHubLoadedModelCohortCensus,2)');
 assert(first>source.indexOf('report.walkFluidPerformance=assessFluidPerformance'));assert(first>source.indexOf("assert(report.nativePoseDifferenceMeters<0.5"));assert(first>source.indexOf("await screenshot('public-hub.png')"));assert(first<source.indexOf("await page.locator('#leave').click()"));
 assert(second>source.indexOf('report.reconnectedWalkFluidPerformance=assessFluidPerformance'));assert(second>source.indexOf("assert(report.reconnectedNativeDifferenceMeters<0.5"));assert(second<source.lastIndexOf("await page.locator('#leave').click()"));
 assert.equal(source.match(/page\.evaluate\(collectHubLoadedModelCohortCensus,[12]\)/g)?.length,2);
 assert(source.includes("process.env.OVERTE_LAB_LOADED_MODEL_COHORT_CENSUS==='1'"));assert(source.includes("if(report.loadedModelCohortCensusRequested)report.loadedModelCohortCensus=["));assert(source.includes("if(report.loadedModelCohortCensusRequested)report.loadedModelCohortCensus.push("));
 assert(source.includes("'browser-client/src/loaded-model-cohort.ts'"));assert(source.includes("'browser-client/tests/integration/hub-loaded-model-cohort-census.mjs'"));
 assert.equal(source.match(/timeout:60000/g)?.length,2);assert.equal(source.match(/timeout:90000/g)?.length,1);assert(source.includes("Number(process.env.OVERTE_LAB_LOADING_TIMEOUT||90)"));assert(source.includes('assert(report.movementMeters>0.5'));assert(source.includes('assert(report.reconnectedMovementMeters>0.5'));assert(source.includes('30FPS, p95<=66.7ms and no steady stall>250ms'));
});

test('censored subset cannot leak tentative groups or a whole-world coverage claim',async()=>{
 const r=report();r.partial=true;await assert.rejects(fixture(r).collect(1),/valid bounded diagnostic/);
 for(const key of ['exactGeometryAndMaterialIdentity','exactGeometryAndAuditedMaterialValues'])for(const field of Object.keys(r[key]))r[key][field]=0;
 const out=await fixture(r).collect(1);assert.equal(out.data.partial,true);assert.equal(out.data.modelCohort.wholeWorldCoverage,false);
});
