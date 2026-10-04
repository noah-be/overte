// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Existing renderer observer only; no replacement hooks, GPU reads or native calls. */
export function configureHubDispatchAttribution(url,value){
 const requested=value==='1';
 if(requested){url.searchParams.set('renderCpuTiming','1');url.searchParams.set('renderDispatchAttribution','1');}
 return requested;
}
/** Page-serialized one-shot fixed-scalar snapshot for each admitted World. */
export function collectHubDispatchAttribution(admissionOrdinal){
 if(admissionOrdinal!==1&&admissionOrdinal!==2)throw Error('Invalid dispatch diagnostic admission ordinal');
 const api=window.__overte;
 if(!api?.connected)throw Error('Dispatch attribution requires a connected browser');
 const used=window.__hubDispatchAttributionUsed??new Set();
 if(!(used instanceof Set)||used.size>2||used.has(admissionOrdinal))throw Error('Dispatch diagnostic already attempted');
 window.__hubDispatchAttributionUsed=used;used.add(admissionOrdinal);
 try{
  const raw=api.performance?.renderCpuTiming,a=raw?.dispatchAttribution;
  if(window.__overte!==api||!api.connected||!raw||raw.enabled!==true||raw.active!==false||raw.status!=='sampling'||!a||a.enabled!==true)throw Error('Unavailable current sampling owner');
  const integer=n=>Number.isSafeInteger(n)&&n>=0;
  const scalar=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=Number.MAX_SAFE_INTEGER;
  const limits={maximumSamples:512,maximumDrawsPerSample:4096,maximumOwnersPerSample:512,maximumMaterialsPerSample:512,maximumGeometriesPerSample:512,maximumSourcesPerSample:1024,maximumSamplerTuplesPerSample:2048,maximumProgramsPerSample:128,maximumProgramCallsPerSample:4096,maximumSamplerKeyBytesPerSample:262144,maximumCpuMsPerSample:2,maximumAggregateCpuMs:500,maximumElapsedMsPerSample:5000};
  if(!a.limits||Object.keys(limits).some(key=>a.limits[key]!==limits[key]))throw Error('Changed observer protocol');
  if(a.scope!=='sampled-renderBufferDirect-call-entries'||a.entryEvidence!=='call-entries-not-confirmed-GL-draws'||a.programEvidence!=='actual-useProgram-calls'||a.materialEvidence!=='identity-only-not-value-equivalence')throw Error('Changed observer semantics');
  if(!integer(a.samples)||a.samples>512||!integer(a.capacitySkippedSamples)||!scalar(a.cpuMs)||raw.sampleEveryFrames!==8||raw.maximumSamples!==2048||raw.maximumObservedFrames!==16384||raw.maximumBoundaryCallsPerSample!==4096||raw.maximumFrameMs!==5000)throw Error('Changed observer bounds');
  const counts=['observedFrames','scheduledFrames','completedFrames','failedRenders','invalidFrames','capacitySkippedFrames','reentrantFrames','installationRefusals','foreignHookChanges'],observerCounts={};
  for(const key of counts){if(!integer(raw[key]))throw Error('Invalid observer counter');observerCounts[key]=raw[key];}
  if(observerCounts.observedFrames>16384||observerCounts.scheduledFrames>2048||observerCounts.completedFrames>observerCounts.scheduledFrames||a.samples>observerCounts.scheduledFrames)throw Error('Invalid observer coverage');
  const fields=['drawsObserved','owners','materials','geometries','materialTransitions','geometryTransitions','geometryVariantTransitions','geometryVariants','programCalls','programTransitions','drawsWithObservedProgram','drawsWithoutObservedProgram','programs','textureBindings','sources','sourceSamplerTuples','samplerKeyBytes','cpuMs','elapsedMs'];
  const reasons=['draw-limit','owner-limit','material-limit','geometry-limit','source-limit','sampler-limit','sampler-key-limit','program-call-limit','program-limit','cpu-limit','wall-limit','invalid-clock','unsupported-input','context-lost','aborted','foreign-hook','installation-refused','render-failed','timing-invalid'];
  const populations={};let samples=0,complete=0,censored=0,measuredCpuMs=0;
  for(const name of ['emptyScene','loading','modelJobsIdle']){
   const p=a.populations?.[name];
   if(!p||!integer(p.samples)||!integer(p.completeSamples)||!integer(p.censoredSamples)||p.samples>512||p.completeSamples+p.censoredSamples!==p.samples)throw Error('Invalid population coverage');
   const why={};if(!p.reasons||typeof p.reasons!=='object'||Array.isArray(p.reasons)||Object.keys(p.reasons).length>reasons.length)throw Error('Invalid censor record');
   let reasonCount=0;for(const [reason,value]of Object.entries(p.reasons)){if(!reasons.includes(reason)||!integer(value)||value<1||value>p.censoredSamples)throw Error('Invalid censor reason');why[reason]=value;reasonCount+=value;}
   if(reasonCount!==p.censoredSamples)throw Error('Unaccounted partial samples');
   function totals(value,n){
    if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!fields.includes(key)))throw Error('Invalid scalar totals');
    const out={};for(const key of fields){const number=value[key]??(n===0?0:undefined);if(!(key.endsWith('Ms')?scalar(number):integer(number)))throw Error('Invalid scalar total');out[key]=number;}
    if(n===0&&Object.values(out).some(value=>value!==0))throw Error('Empty population cannot contain dispatch counts');
    const maximum={drawsObserved:4096,owners:512,materials:512,geometries:512,geometryVariants:128,programCalls:4096,programs:128,sources:1024,sourceSamplerTuples:2048,samplerKeyBytes:262144};
    for(const [key,limit]of Object.entries(maximum))if(out[key]>limit*n)throw Error('Invalid counter bound');
    // Measured CPU/wall overruns are preserved, never clipped to admission caps.
    return out;
   }
   const all=totals(p.totals,p.samples),exact=totals(p.completeTotals,p.completeSamples),partial=totals(p.partialTotals,p.censoredSamples);
   for(const key of fields)if(!key.endsWith('Ms')&&all[key]!==exact[key]+partial[key])throw Error('Invalid complete/partial partition');
   if(exact.drawsWithObservedProgram+exact.drawsWithoutObservedProgram!==exact.drawsObserved)throw Error('Incomplete complete-sample boundary counts');
   populations[name]={samples:p.samples,completeSamples:p.completeSamples,censoredSamples:p.censoredSamples,reasons:why,completeTotals:exact,partialTotals:partial,totals:all};
   samples+=p.samples;complete+=p.completeSamples;censored+=p.censoredSamples;measuredCpuMs+=all.cpuMs;
  }
  if(samples!==a.samples||Math.abs(measuredCpuMs-a.cpuMs)>1e-8*Math.max(1,a.cpuMs))throw Error('Invalid aggregate observer accounting');
  return {schemaVersion:1,admissionOrdinal,scope:'Sampled public renderer call entries in this admission; not whole-scene or GPU-draw census',
   entryEvidence:a.entryEvidence,programEvidence:a.programEvidence,materialEvidence:a.materialEvidence,
   measurementIncludesObserverOverhead:true,causalLagAttribution:false,wholeWorldCoverage:false,
   enabled:true,partial:censored>0||a.capacitySkippedSamples>0,samples,completeSamples:complete,censoredSamples:censored,
   capacitySkippedSamples:a.capacitySkippedSamples,observerCpuMs:a.cpuMs,sampleEveryFrames:8,limits,
   observerCounts,populations};
 }catch{throw Error('Connected dispatch observer did not produce a valid bounded scalar diagnostic');}
}
/** Additional opt-in attestation; original default harness behavior is unchanged. */
export function hubDispatchSourceCoherence(files,start,end,startDistribution,endDistribution){
 const hash=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
 const names=Array.isArray(files)&&files.length>0&&files.length<=256&&new Set(files).size===files.length&&files.every(file=>typeof file==='string'&&file.startsWith('browser-client/')&&file.length<=256);
 const sourceCoherent=!!(names&&start&&end&&files.every(file=>hash(start[file])&&start[file]===end[file]));
 function distribution(value){
  if(!value||typeof value!=='object'||Array.isArray(value))return null;const keys=Object.keys(value).sort();if(keys.length===0||keys.length>4096)return null;
  const records=[];for(const key of keys){const item=value[key];if(key.length>1024||!item||!hash(item.sha256)||!Number.isSafeInteger(item.bytes)||item.bytes<0)return null;records.push([key,item.sha256,item.bytes]);}return records;
 }
 const first=distribution(startDistribution),last=distribution(endDistribution),distributionCoherent=!!first&&!!last&&JSON.stringify(first)===JSON.stringify(last);
 return {sourceCoherent,distributionCoherent,sourceFileCount:names?files.length:0};
}
