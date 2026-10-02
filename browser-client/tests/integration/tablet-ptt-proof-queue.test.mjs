// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {readFileSync} from 'node:fs';import {fileURLToPath} from 'node:url';
import {pttProofQueueInstallerSource} from './tablet-ptt-proof-queue.mjs';
import {samplePttDisplayedControl,freshPttClickCoordinates} from './tablet-ptt-frame-sample.mjs';
import {assertPaintedPttControl} from './tablet-ptt-audit.mjs';
const frame=()=>({sequence:8,revision:2,navigationSequence:5,width:480,height:706,tabletRect:{x:0,y:0,width:480,height:706},data:Buffer.from('owned PNG witness').toString('base64')});
const point=()=>({sequence:8,revision:2,navigationSequence:5,x:164.5,y:214.5,rect:{x:100,y:150,width:129,height:129}});
function fixture(){
 let reads=0;const ctx={window:{__pttAudit:{frame:frame()}},atob:input=>Buffer.from(input,'base64').toString('binary')};
 const el={width:480,height:706,getBoundingClientRect:()=>({x:10,y:20,width:240,height:353}),getContext:()=>({getImageData(x,y,w,h){reads++;const data=new Uint8ClampedArray(w*h*4);for(let i=0;i<data.length;i+=4){const value=i<data.length/2?20:230;data[i]=data[i+1]=data[i+2]=value;data[i+3]=255;}return {data};}})};
 vm.runInNewContext(pttProofQueueInstallerSource(samplePttDisplayedControl,assertPaintedPttControl),ctx);const queue=ctx.window.__pttProofFactory(),click=vm.runInNewContext('('+freshPttClickCoordinates.toString()+')',ctx);
 return {ctx,el,queue,click,reads:()=>reads};
}
const plain=value=>JSON.parse(JSON.stringify(value));
test('exact original painted assertion source is serialized with only equivalent tiny dependencies',()=>{
 const source=pttProofQueueInstallerSource(samplePttDisplayedControl,assertPaintedPttControl);assert(source.includes(assertPaintedPttControl.toString()));assert(source.includes(samplePttDisplayedControl.toString()));assert(!source.includes('requestAnimationFrame'));assert(!source.includes('setTimeout'));assert(!source.includes('mouse.click'));assert(!source.includes('frameAck'));
});
test('small calibration response retains exact original pixel/PNG proof privately for post-effect reassertion',()=>{
 const f=fixture(),sample=f.queue.sample(f.el,point());assert.equal(sample.refusal,null);assert(JSON.stringify(sample).length<512);assert(!('rgba'in sample.image));assert(!('nativePNG'in sample));const full=f.queue.read(sample.proofOrdinal);assertPaintedPttControl(full.image.rgba,full.image.width,full.image.height);assert.equal(full.nativePNG,frame().data);assert.equal(full.image.rgba.length,129*129*4);assert.equal(f.reads(),1);assert.deepEqual(plain(full.frame),plain(sample.frame));assert.equal(f.queue.metadata().count,1);f.queue.release(sample.proofOrdinal);assert.equal(f.queue.metadata().count,0);assert.equal(f.queue.metadata().bytes,0);
});
test('counterexample: bulk proof transport permits an ACK before the unchanged physical-click CAS',async()=>{
 const f=fixture(),sample=f.queue.sample(f.el,point());assert.equal(f.click(f.el,point()).refusal,null);
 // Authored transport interstitial, not a measured browser latency claim.
 const full=f.queue.read(sample.proofOrdinal);assert(JSON.stringify(full).length>65536);await Promise.resolve().then(()=>{f.ctx.window.__pttAudit.frame={...frame(),sequence:9};});assert.equal(f.click(f.el,point()).refusal,'frame-sequence-changed');
 // The queued old proof remains only evidence; it cannot authorize a new click.
 assertPaintedPttControl(f.queue.read(sample.proofOrdinal).image.rgba,129,129);
});
test('paint failures leave no proof or returned click handle and retain both original contrast/alpha thresholds',()=>{
 for(const rgba of [new Uint8ClampedArray(129*129*4),new Uint8ClampedArray(129*129*4).fill(255)]){
  const f=fixture();f.el.getContext=()=>({getImageData:()=>({data:rgba})});assert.throws(()=>f.queue.sample(f.el,point()));assert.equal(f.queue.metadata().count,0);assert.equal(f.queue.metadata().bytes,0);
 }
 const colors=new Uint8Array(8*8*4);for(let i=0;i<colors.length;i+=4)colors.set([i<128?20:40,20,20,255],i);assert.throws(()=>assertPaintedPttControl(colors,8,8));
});
test('all frame/revision/navigation mismatches still reject before pixel reads or proof insertion',()=>{
 for(const [key,reason]of [['sequence','frame-sequence-changed'],['revision','frame-revision-changed'],['navigationSequence','frame-navigation-changed']]){const f=fixture();f.ctx.window.__pttAudit.frame[key]++;assert.equal(f.queue.sample(f.el,point()).refusal,reason);assert.equal(f.click(f.el,point()).refusal,reason);assert.equal(f.reads(),0);assert.equal(f.queue.metadata().count,0);}
});
test('reentrant frame replacement during pixel or PNG reads rejects publication without mixed proof',()=>{
 const f=fixture(),original=f.el.getContext;f.el.getContext=()=>({getImageData(...args){const data=original().getImageData(...args);f.ctx.window.__pttAudit.frame={...frame(),sequence:9};return data;}});assert.equal(f.queue.sample(f.el,point()).refusal,'frame-changed-during-sample');assert.equal(f.queue.metadata().count,0);
 const g=fixture();g.ctx.atob=input=>{g.ctx.window.__pttAudit.frame={...frame(),sequence:9};return Buffer.from(input,'base64').toString('binary');};assert.equal(g.queue.sample(g.el,point()).refusal,'frame-changed-during-sample');assert.equal(g.queue.metadata().count,0);
});
test('native PNG missing/invalid/empty/over2MiB and area limits refuse, never certify pixels alone',()=>{
 for(const png of ['',null,'invalid base64!',Buffer.alloc(2*1024*1024+1).toString('base64')]){const f=fixture();f.ctx.window.__pttAudit.frame.data=png;assert.throws(()=>f.queue.sample(f.el,point()));assert.equal(f.queue.metadata().count,0);}
 for(const change of [p=>p.rect.width=257,p=>p.rect.height=7,p=>p.rect.x=-1]){const f=fixture(),p=point();change(p);assert.equal(f.queue.sample(f.el,p).refusal,'mapped-control-out-of-bounds');assert.equal(f.queue.metadata().count,0);}
});
test('16-row capacity refuses before reads; release admits a new unique ordinal without aliasing old handles',()=>{
 const f=fixture(),ids=[];for(let i=0;i<16;i++)ids.push(f.queue.sample(f.el,point()).proofOrdinal);assert.equal(f.queue.metadata().count,16);const reads=f.reads();assert.throws(()=>f.queue.sample(f.el,point()));assert.equal(f.reads(),reads);f.queue.release(ids[0]);assert.throws(()=>f.queue.read(ids[0]));const next=f.queue.sample(f.el,point());assert(next.proofOrdinal>ids.at(-1));assert.equal(f.queue.metadata().count,16);
});
test('32MiB retained payload budget refuses without eviction or arbitrary larger limits',()=>{
 const f=fixture();f.ctx.window.__pttAudit.frame.data=Buffer.alloc(2*1024*1024).toString('base64');let admitted=0;while(admitted<16){try{f.queue.sample(f.el,point());admitted++;}catch(error){assert.match(error.message,/byte bound/);break;}}assert(admitted>0&&admitted<16);const metadata=f.queue.metadata();assert.equal(metadata.count,admitted);assert(metadata.bytes<=32*1024*1024);assert(metadata.bytes>24*1024*1024);
});
test('proof readers get copies and cannot mutate stored original RGBA or metadata',()=>{
 const f=fixture(),id=f.queue.sample(f.el,point()).proofOrdinal,a=f.queue.read(id);a.image.rgba.fill(0);a.frame.sequence=99;a.canvas.width=1;const b=f.queue.read(id);assertPaintedPttControl(b.image.rgba,b.image.width,b.image.height);assert.equal(b.frame.sequence,8);assert.equal(b.canvas.width,480);
});
test('retirement cancels future sampling/reading/releasing and never restores stale proofs in a new session',()=>{
 const f=fixture(),id=f.queue.sample(f.el,point()).proofOrdinal;f.queue.retire();f.queue.retire();for(const run of [()=>f.queue.read(id),()=>f.queue.release(id),()=>f.queue.metadata(),()=>f.queue.sample(f.el,point())])assert.throws(run);const fresh=f.ctx.window.__pttProofFactory();assert.equal(fresh.metadata().count,0);assert.throws(()=>fresh.read(id));
});
test('actual harness retains strict genuine-click guard and delays full read/assert/write until checkpoint or finally',()=>{
 const source=readFileSync(fileURLToPath(new URL('./tablet-push-to-talk.mjs',import.meta.url)),'utf8');const pointBody=source.slice(source.indexOf(' async function point('),source.indexOf(' async function click('));assert(pointBody.includes('window.__pttAudit.proofs.sample(el,p)'));assert(!pointBody.includes('nativePNG'));assert(!pointBody.includes('image.rgba'));assert(!pointBody.includes('writeFile('));const clickBody=source.slice(source.indexOf(' async function click('),source.indexOf(' async function audioApp('));assert(clickBody.includes('freshPttClickCoordinates'));assert(clickBody.includes('assert.equal(sampled.refusal,null'));assert(clickBody.includes('await page.mouse.click(sampled.x,sampled.y)'));const flush=source.slice(source.indexOf('async function flushControlProofs'),source.indexOf('async function checkpoint'));assert(flush.includes('assertPaintedPttControl(full.image.rgba,full.image.width,full.image.height)'));assert(flush.includes("{flag:'wx',mode:0o600}"));assert(flush.indexOf('assertPaintedPttControl')<flush.indexOf('writeFile'));assert(source.includes('try{await flushControlProofs();}catch{report.privateControlEvidenceFailed=true;report.completed=false;process.exitCode=1;}'));assert(source.includes('tests/integration/tablet-ptt-proof-queue.mjs'));assert(source.includes('proofs?.retire()'));
});

function extractedFlush(f,entries,writeFile){
 const source=readFileSync(fileURLToPath(new URL('./tablet-push-to-talk.mjs',import.meta.url)),'utf8'),body=source.slice(source.indexOf('async function flushControlProofs'),source.indexOf('async function checkpoint'));
 f.ctx.window.__pttAudit.proofs=f.queue;
 const page={async evaluate(fn,arg){const callable=vm.runInNewContext('('+fn.toString()+')',f.ctx),value=callable(arg);return value===undefined?undefined:plain(value);}};
 return Function('assert','page','privateControlProofs','assertPaintedPttControl','Buffer','writeFile',body+'\nreturn flushControlProofs;')(assert,page,entries,assertPaintedPttControl,Buffer,writeFile);
}
function tracked(f){const sample=f.queue.sample(f.el,point());return new Map([[sample.proofOrdinal,{file:'authored-private-proof.png',frame:plain(sample.frame),canvas:plain(sample.canvas),image:plain(sample.image)}]]);}
test('source-exact post-effect flush reasserts pixel witness, writes0600/O_EXCL, then releases exact browser ownership',async()=>{
 const f=fixture(),entries=tracked(f),writes=[];const flush=extractedFlush(f,entries,async(file,png,options)=>{writes.push({file,bytes:png.length,options});assert.equal(f.queue.metadata().count,1,'Browser evidence survives until the private write completes');});await flush();assert.equal(writes.length,1);assert.deepEqual(plain(writes[0].options),{flag:'wx',mode:0o600});assert.equal(entries.size,0);assert.equal(f.queue.metadata().count,0);assert.equal(f.queue.metadata().bytes,0);
});
test('source-exact full-proof read mismatch and missing evidence refuse before private writes/releases',async()=>{
 for(const corrupt of [(id,row)=>row.frame.sequence++,(id,row)=>row.image.rgba.fill(0)]){
  const f=fixture(),entries=tracked(f),id=entries.keys().next().value,original=f.queue.read;f.queue.read=n=>{const row=original(n);corrupt(n,row);return row;};let writes=0;await assert.rejects(extractedFlush(f,entries,async()=>{writes++;})());assert.equal(writes,0);assert.equal(entries.size,1);assert.equal(f.queue.metadata().count,1);f.queue.retire();assert.throws(()=>f.queue.read(id));
 }
 const f=fixture(),entries=tracked(f);entries.clear();let writes=0;await assert.rejects(extractedFlush(f,entries,async()=>{writes++;})());assert.equal(writes,0);assert.equal(f.queue.metadata().count,1);
});
test('source-exact private write failure retains proof until successful final read/write or explicit retirement',async()=>{
 const f=fixture(),entries=tracked(f),originalError=new Error('owned fixture I/O refusal');const failing=extractedFlush(f,entries,async()=>{throw originalError;});await assert.rejects(failing(),error=>error===originalError);assert.equal(entries.size,1);assert.equal(f.queue.metadata().count,1);await extractedFlush(f,entries,async()=>{})();assert.equal(entries.size,0);assert.equal(f.queue.metadata().count,0);
});
test('actual finally failure checkpoint preserves an earlier primary failure and marks evidence refusal/nonzero',async()=>{
 const source=readFileSync(fileURLToPath(new URL('./tablet-push-to-talk.mjs',import.meta.url)),'utf8'),statement='try{await flushControlProofs();}catch{report.privateControlEvidenceFailed=true;report.completed=false;process.exitCode=1;}';assert(source.includes(statement));const report={completed:false,failure:{phase:'genuine-input',category:'acceptance-refused'}},process={exitCode:1};const run=vm.runInNewContext('(async()=>{'+statement+'})',{report,process,flushControlProofs:async()=>{throw Error('private I/O failure');}});await run();assert.deepEqual(report.failure,{phase:'genuine-input',category:'acceptance-refused'});assert.equal(report.privateControlEvidenceFailed,true);assert.equal(report.completed,false);assert.equal(process.exitCode,1);
});
