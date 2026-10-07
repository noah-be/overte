// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import {createHash} from 'node:crypto';import {gunzipSync,gzipSync} from 'node:zlib';import vm from 'node:vm';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {buildBrowserCaptureUI,AUDIO_SCRIPT_SHA256,AUDIO_RCC_SHA256,readCaptureV7Source} from './integration/capture-readback-source-fixture.mjs';
import {assertPaintedPttControl} from './integration/tablet-ptt-audit.mjs';
const GAIN_ADDITION="palette.dark:enabled?'#00b4ef':'#686868';";
function stripGainPalette(source){assert.equal(source.split(GAIN_ADDITION).length,2);return source.replace(GAIN_ADDITION,'');}

import {stripBrowserCaptureStyle,STYLE_ADDITION,STYLE_ANCHOR} from './fixtures/capture-style-recovery.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
function readNativeAudioGold(bytes){
 assert(Buffer.isBuffer(bytes)&&bytes.length>=18&&bytes.length<=65536,'Bounded native Audio gzip');
 assert.equal(bytes.subarray(0,10).toString('hex'),'1f8b08000000000002ff','Exact metadata-free native gzip header');
 const original=gunzipSync(bytes,{maxOutputLength:65536});
 assert.equal(original.length,35827);assert.equal(sha(original),'4208e7f17c85d1c1bd57e515eb191fa6afb1ffb517b5506d58844922e8f99379');return original.toString('utf8');
}
const original=await readFile(new URL('./fixtures/capture-style-v3-overrides.mjs.txt',import.meta.url),'utf8'),currentCandidate=await readCaptureV7Source('gateway/browser-capture-overrides.mjs'),candidate=stripGainPalette(currentCandidate),nativeAudioGzip=await readFile(new URL('./fixtures/native-audio-f91d15a.qml.gz',import.meta.url)),nativeAudio=readNativeAudioGold(nativeAudioGzip),nativeSwitch=await readFile(new URL('./fixtures/native-switch-f91d15a.qml.txt',import.meta.url),'utf8');
const audio=gunzipSync(await readFile(new URL('../gateway/fixtures/native-audio-f91d15a.js.gz',import.meta.url))).toString(),channel='overte.browser.capture.'+'1'.repeat(32),url='file:///tmp/authored/browser-audio.qml';
function oldGenerate(){const a=original.indexOf('export function buildBrowserCaptureUI('),z=original.indexOf('\nexport async function loadBrowserCapturePackage',a);assert(a>=0&&z>a);const ctx={createHash,AUDIO_SCRIPT_SHA256,URL,path,fileURLToPath,once:(s,a,b)=>{assert.equal(s.split(a).length,2);return s.replace(a,b);}};vm.runInNewContext(original.slice(a,z).replace(/^export /,'')+';this.generate=buildBrowserCaptureUI;',ctx);return ctx.generate(audio,channel,url);}
test('authenticated native Audio and Switch require caller-owned HifiConstants style context',()=>{
 assert.equal(sha(nativeAudio),'4208e7f17c85d1c1bd57e515eb191fa6afb1ffb517b5506d58844922e8f99379');assert.equal(sha(nativeSwitch),'31df4673f94ba0f5828cda60b740f1ca3bdd39e9adc95c875cd23287bbbcb907');
 assert(nativeAudio.includes('import stylesUit 1.0'));assert.equal(nativeAudio.split('HifiConstants { id: hifi; }').length,2);assert(nativeSwitch.includes('property int colorScheme: hifi.colorSchemes.light;'));assert(nativeSwitch.includes('color: hifi.colors.lightGray;'));
 const prior=oldGenerate(),next=buildBrowserCaptureUI(audio,channel,url);assert(!prior.qml.includes('HifiConstants { id: hifi; }'));assert(next.qml.includes('import stylesUit 1.0'));assert.equal(next.qml.split('HifiConstants { id: hifi; }').length,2);
});
test('style correction recovers full authenticated v3 generator and every generated runtime field',()=>{
 assert.equal(sha(original),'3b5ddde7ff350c0ddafe27de9841dac084c8326c7bed8fa1c766a353e81ff4cf');assert.equal(stripBrowserCaptureStyle(candidate),original);
 const old=oldGenerate(),next=buildBrowserCaptureUI(audio,channel,url);assert.equal(next.script,old.script);assert.equal(stripBrowserCaptureStyle(stripGainPalette(next.qml)),old.qml);assert.equal(AUDIO_SCRIPT_SHA256,'42f48103b327c63bdb7a22f7cfb8fe9c57010014e468ed7cda5a557cfc1d2e17');assert.equal(AUDIO_RCC_SHA256,'dd8a9efebe9b09a4b5e84e5c768ad7c7a38ea9702e681a357898dcbb9674ce01');
});
test('style source recovery rejects absent duplicated and relocated declarations',()=>{
 assert.throws(()=>stripBrowserCaptureStyle(original));assert.throws(()=>stripBrowserCaptureStyle(candidate.replace(STYLE_ADDITION,STYLE_ADDITION+STYLE_ADDITION)));assert.throws(()=>stripBrowserCaptureStyle(candidate.replace(STYLE_ADDITION+STYLE_ANCHOR,STYLE_ANCHOR+STYLE_ADDITION)));
 const edited=candidate.replace('switchWidth:40','switchWidth:41');assert.notEqual(stripBrowserCaptureStyle(edited),original);
});
test('original package and private-UI admission refuses mutated resources channel and paths',()=>{
 for(const source of [audio+'\n',audio.replace('onMuteToggled','onMuteToggledChanged')])assert.throws(()=>buildBrowserCaptureUI(source,channel,url));
 for(const invalid of ['overte.browser.capture.'+'g'.repeat(32),'unrelated.channel'])assert.throws(()=>buildBrowserCaptureUI(audio,invalid,url));
 for(const invalid of ['https://example.invalid/browser-audio.qml','file:///tmp/authored/other.qml','file:///tmp/authored/browser-audio.qml?query=1'])assert.throws(()=>buildBrowserCaptureUI(audio,channel,invalid));
});

test('binary gold preserves exact raw source and rejects corrupt oversized or replaced native bytes',()=>{
 assert.equal(sha(nativeAudioGzip),'c8cd2d3ebafe34bf895ece8c9ad8f6bc48d62a3f38d0bea294714f5235b65116');assert.equal(Buffer.byteLength(nativeAudio),35827);assert.equal(nativeAudioGzip.readUInt32LE(4),0);assert.equal(nativeAudioGzip[3],0);
 const metadata=Buffer.from(nativeAudioGzip);metadata[3]=8;assert.throws(()=>readNativeAudioGold(metadata));
 const corrupt=Buffer.from(nativeAudioGzip);corrupt[corrupt.length-8]^=1;assert.throws(()=>readNativeAudioGold(corrupt));
 const compress=raw=>{const bytes=gzipSync(raw,{level:9,mtime:0});bytes[9]=255;return bytes;};
 assert.throws(()=>readNativeAudioGold(compress(Buffer.from(nativeAudio+'\n'))));assert.throws(()=>readNativeAudioGold(compress(Buffer.alloc(65537,65))));assert.throws(()=>readNativeAudioGold(Buffer.alloc(65537)));
});

// Same native Slider/handle/geometry/input logic; only its local filled-track palette changes.
test('gain palette addition recovers entire661 generator and leaves generated handlers/script/settings exact',()=>{
 assert.equal(sha(candidate),'661347b2b9e27f18ce1cebf2f88fa3d853a7646f236818a7f93dc08cede48f52');
 const old=(()=>{const a=candidate.indexOf('export function buildBrowserCaptureUI('),z=candidate.indexOf('\nexport async function loadBrowserCapturePackage',a),ctx={createHash,AUDIO_SCRIPT_SHA256,URL,path,fileURLToPath,once:(s,a,b)=>{assert.equal(s.split(a).length,2);return s.replace(a,b);}};vm.runInNewContext(candidate.slice(a,z).replace(/^export /,'')+';this.generate=buildBrowserCaptureUI;',ctx);return ctx.generate(audio,channel,url);})();
 const current=buildBrowserCaptureUI(audio,channel,url);assert.equal(current.script,old.script);assert.equal(stripGainPalette(current.qml),old.qml);
 assert.equal(current.qml.split(GAIN_ADDITION).length,2);assert(current.qml.includes('Slider{id:gainControl;'+GAIN_ADDITION));assert(!GAIN_ADDITION.includes('handle')&&!GAIN_ADDITION.includes('background'));
 assert.throws(()=>stripGainPalette(currentCandidate.replace(GAIN_ADDITION,GAIN_ADDITION+GAIN_ADDITION)));assert.throws(()=>stripGainPalette(candidate));
});
test('retained actual native 16px groove contrast17 fails original painted oracle; only palette color counterfactual passes',()=>{
 // Private retained capture-control16 SHA3e151cee5a9fd9c22c55ceee1a5a2af324469dec652b56c8cbc4d153efbbd01a.
 // Match pre-cleanup native geometry. These two exact native RGB colors fill the crop.
 const rows=[0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0];const rgba=[];for(const row of rows)for(let x=0;x<16;x++)rgba.push(...(row?[53,54,55,255]:[37,37,37,255]));
 assert.throws(()=>assertPaintedPttControl(rgba,16,16),/painted visible contrast/);
 const colored=rgba.slice();for(let i=0;i<colored.length;i+=4)if(colored[i]===53&&colored[i+1]===54&&colored[i+2]===55){colored[i]=0;colored[i+1]=180;colored[i+2]=239;}
 assert.equal(assertPaintedPttControl(colored,16,16),true);assert.equal(rgba.length,colored.length);
 // This is a CPU color counterfactual, not an actual Qt rendering qualification.
});
test('gain palette honors actual enabled state without altering default Qt geometry or native actions',()=>{
 const choose=new vm.Script("enabled?'#00b4ef':'#686868'");assert.equal(choose.runInNewContext({enabled:true}),'#00b4ef');assert.equal(choose.runInNewContext({enabled:false}),'#686868');
 const qml=buildBrowserCaptureUI(audio,channel,url).qml,original=stripGainPalette(qml);
 for(const token of ['from:0;to:200;stepSize:1;','onMoved:if(!pressed)','onPressedChanged:if(!pressed)','enabled:root.browserReady&&!root.awaiting&&root.browserState.controls.inputGainPercent'])assert(qml.includes(token)&&original.includes(token));
 assert.equal(qml.split('Slider{').length,original.split('Slider{').length);assert.equal(qml.split('onMoved:').length,original.split('onMoved:').length);
});
