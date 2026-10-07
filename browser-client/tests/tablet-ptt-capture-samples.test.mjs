// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {exactPttCaptureFilter} from './integration/tablet-ptt-capture-samples.mjs';
import {composeCaptureRunner,recoverPttRunner} from './integration/tablet-capture-compose.mjs';
const original=await readFile(new URL('./fixtures/capture-original-ptt-20261002.mjs.txt',import.meta.url),'utf8');
const start=original.indexOf('function metrics(bytes){'),end=original.indexOf('async function capture(',start);
assert(start>=0&&end>start);
const metrics=new Function('assert',original.slice(start,end)+';return metrics;')(assert);
function render(input,seconds,filter){
 const args=['-hide_banner','-loglevel','error','-f','lavfi','-i',input,'-t',String(seconds),...(filter?['-af',filter]:[]),'-ar','48000','-ac','2','-f','s16le','pipe:1'];
 return execFileSync('ffmpeg',args,{timeout:5000,maxBuffer:2*1024*1024,stdio:['ignore','pipe','pipe']});
}
test('only original1..5 second capture budget is admitted, at48k before counted trim',()=>{
 for(const seconds of [1,3,5])assert.equal(exactPttCaptureFilter(seconds),'aresample=48000,atrim=end_sample='+seconds*48000);
 for(const value of [0,6,1.5,NaN,Infinity,'5',null])assert.throws(()=>exactPttCaptureFilter(value),/duration refused/);
});
test('actual ffmpeg timestamp discrepancy reproduces original36-byte overrun; counted filter retains exact PCM prefix and997 tone',()=>{
 const input='sine=frequency=997:sample_rate=48000:duration=5.1,asetpts=PTS*0.9999625';
 const old=render(input,5),fixed=render(input,5,exactPttCaptureFilter(5));
 assert.equal(old.length,960036);assert.throws(()=>metrics(old));
 assert.equal(fixed.length,960000);assert.deepEqual(fixed,old.subarray(0,960000));
 const measured=metrics(fixed);assert(measured.rms>.001&&measured.tone997Amplitude>.001);
});
test('real44.1k input is resampled before counting3second48k output; silence remains original quiet',()=>{
 const input='anullsrc=r=44100:cl=stereo:d=3.1,asetpts=PTS*0.9999625';
 const result=render(input,3,exactPttCaptureFilter(3));assert.equal(result.length,3*48000*4);assert(metrics(result).rms<.0005);
 // Deliberately wrong ordering counts source samples rather than emitted48k samples.
 const wrong=render(input,3,'atrim=end_sample=144000,aresample=48000');assert(wrong.length>3*48000*4);
});
test('insufficient source is not padded or given a longer deadline to manufacture success',()=>{
 const result=render('anullsrc=r=48000:cl=stereo:d=0.1',5,exactPttCaptureFilter(5));assert.equal(result.length,4800*4);assert(metrics(result).rms<.0005);
});
test('original cap remains960000 and every PTT action/oracle/body recovers byte-exactly',()=>{
 const composed=composeCaptureRunner(original);assert.equal(recoverPttRunner(composed),original);
 assert(composed.includes('bytes.length<=5*48000*4'));assert(composed.includes("timeoutMs:15000,graceMs:1000"));
 assert(composed.includes("'-t',String(seconds),'-af',exactPttCaptureFilter(seconds),'-ar','48000'"));
 for(const marker of ['Released PTT must silence synthetic input','Browser actual output must contain the native peer997Hz','fresh-session-authority-requires-new-explicit-grant']){
  const literal=marker.includes('peer997Hz')?marker.replace('peer997Hz','peer 997Hz'):marker;assert(composed.includes(literal));
 }
 assert.throws(()=>metrics(Buffer.alloc(960004)));assert.throws(()=>metrics(Buffer.alloc(0)));
});
