// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {hubDispatchSourceCoherence} from './hub-render-dispatch-attribution.mjs';
/** Explicit authored comparison only. Existing default behavior stays off.
 * No renderer/device/native/image read is added by this adapter. */
export function configureHubBitmapCohort(value,env){
 if(value===undefined||value==='')return null;
 assert(value==='baseline'||value==='bitmap','Unknown authored bitmap cohort');
 assert(env.OVERTE_LAB_REQUIRE_FLUID==='1'&&env.OVERTE_LAB_RECONNECT==='1','Bitmap cohort retains all four original fluid/movement/rejoin gates');
 assert(typeof env.OVERTE_LAB_BROWSER_DISPLAY==='string'&&env.OVERTE_LAB_BROWSER_DISPLAY.length>0,'Bitmap cohort requires the owned headed browser');
 const executable=env.OVERTE_LAB_BROWSER==='system-firefox'?env.OVERTE_LAB_FIREFOX:env.OVERTE_LAB_CHROMIUM;
 assert(typeof executable==='string'&&executable.startsWith('/'),'Bitmap cohort requires the explicit stock browser executable');
 assert((env.OVERTE_LAB_BITMAP_UPLOAD==='1')===(value==='bitmap'),'Cohort label must match the existing explicit bitmap option');
 for(const key of ['OVERTE_LAB_RENDER_DISPATCH_ATTRIBUTION','OVERTE_LAB_ASYNC_DRAW_CENSUS','OVERTE_LAB_LOADED_MODEL_COHORT_CENSUS','OVERTE_LAB_UPLOAD_PROFILE','OVERTE_LAB_GPU_TIMING','OVERTE_LAB_CPU_FRAME_TIMING','OVERTE_LAB_RENDER_CPU_TIMING','OVERTE_LAB_STATIC_MODEL_MATRICES','OVERTE_LAB_MODEL_PARSE_TURN','OVERTE_LAB_SHADER_WARMUP','OVERTE_LAB_TEXTURE_PREPARATION','OVERTE_LAB_SWIFTSHADER'])assert(env[key]!=='1','Authored bitmap cohort keeps unrelated opt-in experiments and diagnostic workload off');
 return {schema:1,mode:value,defaultOff:true,quality:'Unchanged original renderer, density, textures, samplers and graphics profile',additionalSampling:false};
}
/** Reuse the existing original final samples: no extra performance/API call. */
export function projectHubBitmapCohort(performance,mode,admissionOrdinal){
 assert(mode==='baseline'||mode==='bitmap');assert(admissionOrdinal===1||admissionOrdinal===2);
 assert(performance&&performance.loadingModels===0&&performance.queuedModels===0&&performance.compilingGraphics===0,'Original loaded-world sample is required');
 const image=performance.bitmapUpload;assert(image&&image.enabled===(mode==='bitmap'),'Actual bitmap owner must match the explicit cohort');
 const counters=['roots','converted','fallbacks','unsupported','capacityFallbacks','activeRoots','peakRoots'],result={};
 for(const key of counters){assert(Number.isSafeInteger(image[key])&&image[key]>=0&&image[key]<=1e9,'Invalid bitmap binding counter');result[key]=image[key];}
 const integer=value=>Number.isSafeInteger(value)&&value>=0;
 assert(integer(performance.drawingBufferWidth)&&integer(performance.drawingBufferHeight)&&performance.drawingBufferWidth>0&&performance.drawingBufferHeight>0);
 let owner=null;
 if(mode==='bitmap'){
  const fields=['requests','hits','created','closed','evictions','cancelled','failed','closeFailures','peakActive','invalidations','active','pending','readers','retainedEntries','liveEntries','bytes','leases'];owner={};
  for(const key of fields){assert(integer(image[key])&&image[key]<=1e12,'Invalid bitmap resource counter');owner[key]=image[key];}
  assert(owner.active<=2&&owner.peakActive<=2&&owner.pending<=16&&owner.readers<=128&&owner.bytes<=128*1024*1024,'Actual bitmap resource limits must remain unchanged');
  assert(result.converted>0&&owner.created>0,'Candidate must actually prepare a qualifying decoded source');
 }else assert(Object.values(result).every(value=>value===0),'Baseline must not prepare decoded bitmap sources');
 return {admissionOrdinal,mode,bindingCounters:result,owner,drawingBuffer:{width:performance.drawingBufferWidth,height:performance.drawingBufferHeight},scope:'Existing loaded-world sample; live sampler bytes are not released-cache bytes or actual HTTP bytes'};
}
export function attestHubBitmapCohort(files,start,end,startDistribution,endDistribution){return hubDispatchSourceCoherence(files,start,end,startDistribution,endDistribution);}
/** Offline paired qualification: keep unsuccessful originals unsuccessful.
 * Comparing fixed metadata is not a whole-Hub pixel-equivalence proof. */
export function compareHubBitmapCohorts(baseline,candidate){
 assert(baseline?.bitmapUploadCohort?.mode==='baseline'&&candidate?.bitmapUploadCohort?.mode==='bitmap','Explicit original and prepared cohorts are required');
 for(const r of [baseline,candidate]){
  assert(r.bitmapUploadCohort.attestation?.sourceCoherent===true&&r.bitmapUploadCohort.attestation?.distributionCoherent===true,'Each actual cohort must attest its complete source and distribution');
  assert(Array.isArray(r.bitmapUploadCohort.samples)&&r.bitmapUploadCohort.samples.length===2,'Both original admissions must be recorded');
  assert([r.steadyFluidPerformance,r.walkFluidPerformance,r.reconnectedSteadyFluidPerformance,r.reconnectedWalkFluidPerformance].every(v=>v&&typeof v.passed==='boolean'),'All four ORIGINAL gates must remain recorded');
 }
 const a=baseline.startSourceSHA256,b=candidate.startSourceSHA256,files=Object.keys(a??{});
 assert(attestHubBitmapCohort(files,a,b,baseline.startDistributionManifest,candidate.startDistributionManifest).sourceCoherent,'Paired source changed');
 assert(attestHubBitmapCohort(files,a,b,baseline.startDistributionManifest,candidate.startDistributionManifest).distributionCoherent,'Paired distribution changed');
 assert(baseline.browserVersion===candidate.browserVersion&&typeof baseline.browserVersion==='string','Paired stock browser version changed');
 for(const key of ['width','height','devicePixelRatio'])assert(baseline.viewport?.[key]===candidate.viewport?.[key]&&typeof baseline.viewport?.[key]==='number','Paired viewport/density changed');
 for(let i=0;i<2;i++)assert.deepEqual(baseline.bitmapUploadCohort.samples[i].drawingBuffer,candidate.bitmapUploadCohort.samples[i].drawingBuffer,'Paired drawing-buffer resolution changed');
 const gates=r=>({steady:r.steadyFluidPerformance.passed,walk:r.walkFluidPerformance.passed,reconnectedSteady:r.reconnectedSteadyFluidPerformance.passed,reconnectedWalk:r.reconnectedWalkFluidPerformance.passed});
 return {schema:1,sourceMatched:true,distributionMatched:true,browserVersionMatched:true,viewportAndDensityMatched:true,drawingBuffersMatched:true,baselineGates:gates(baseline),candidateGates:gates(candidate),bothOriginalJourneysCompleted:baseline.completed===true&&candidate.completed===true,bothFluidAcceptance:baseline.fluidMovementAcceptancePassed===true&&candidate.fluidMovementAcceptancePassed===true,causalLoadingGain:false,wholeHubPixelEquivalence:false};
}
