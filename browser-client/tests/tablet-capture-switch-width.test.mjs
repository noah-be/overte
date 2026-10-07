// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';import vm from 'node:vm';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {buildBrowserCaptureUI,AUDIO_SCRIPT_SHA256,readCaptureV7Source} from './integration/capture-readback-source-fixture.mjs';
import {captureControl} from './integration/tablet-capture-audit.mjs';
import {stripBrowserCaptureStyle} from './fixtures/capture-style-recovery.mjs';
const read=p=>readFile(new URL(p,import.meta.url),'utf8');
const GAIN_ADDITION="palette.dark:enabled?'#00b4ef':'#686868';";
function stripGainPalette(source){
 assert.equal(source.split('Slider{id:gainControl;'+GAIN_ADDITION).length,2,'Exact owned gain Slider palette anchor');
 assert.equal(source.split(GAIN_ADDITION).length,2,'Exactly one local gain palette addition');
 return source.replace('Slider{id:gainControl;'+GAIN_ADDITION,'Slider{id:gainControl;');
}
const currentGenerator=await readCaptureV7Source('gateway/browser-capture-overrides.mjs');
assert.equal(createHash('sha256').update(currentGenerator).digest('hex'),'9a41d28676ada36d6a54bec5186214963d9864f6cad8c79e7abe666f9d36d7fe');
const historicalGenerator=stripGainPalette(currentGenerator);
assert.equal(createHash('sha256').update(historicalGenerator).digest('hex'),'661347b2b9e27f18ce1cebf2f88fa3d853a7646f236818a7f93dc08cede48f52');
const before=await read('./fixtures/capture-overrides-before-switch-width.mjs.txt'),after=stripBrowserCaptureStyle(historicalGenerator),native=await read('./fixtures/native-switch-f91d15a.qml.txt'),observed=JSON.parse(await read('./fixtures/capture-clipped-switch-source-row.json'));
const audio=gunzipSync(await readFile(new URL('../gateway/fixtures/native-audio-f91d15a.js.gz',import.meta.url))).toString();
const channel='overte.browser.capture.'+'1'.repeat(32),url='file:///tmp/owned/browser-audio.qml';
function oldGenerate(){const a=before.indexOf('export function buildBrowserCaptureUI('),z=before.indexOf('\nexport async function loadBrowserCapturePackage',a);assert(a>=0&&z>a);const ctx={createHash,AUDIO_SCRIPT_SHA256,URL,path,fileURLToPath,once:(s,a,b)=>{assert.equal(s.split(a).length,2);return s.replace(a,b);}};vm.runInNewContext(before.slice(a,z).replace(/^export /,'')+';this.generate=buildBrowserCaptureUI;',ctx);return ctx.generate(audio,channel,url);}
test('exact native f91 Switch requires caller width and narrow fix recovers entire old generator',()=>{
 assert.equal(createHash('sha256').update(native).digest('hex'),'31df4673f94ba0f5828cda60b740f1ca3bdd39e9adc95c875cd23287bbbcb907');
 assert(native.includes('anchors.leftMargin: rootSwitch.width/2 - rootSwitch.switchWidth/2;'));
 assert(!native.includes('implicitWidth:') || !native.slice(0,native.indexOf('Original.Switch {')).includes('implicitWidth:'));
 assert.equal(after.split('width:switchWidth;height:44;switchWidth:40;labelTextOn:').length-1,3);
 assert.equal(after.replaceAll('width:switchWidth;height:44;switchWidth:40;labelTextOn:','height:44;switchWidth:40;labelTextOn:'),before);
});
test('actual old generator control target remains clipped negative; explicit native caller width permits full bounds only',()=>{
 const frame={sequence:observed.sequence,revision:observed.revision,navigationSequence:observed.navigationSequence,width:480,height:706,tabletRect:{x:0,y:0,width:480,height:706}};
 const old=observed.controls.find(c=>c.kind==='echoCancellation');assert(old.enabled&&old.checked);assert(old.rect.x<0);assert.equal(captureControl([observed],frame,'echoCancellation',true),null);
 // Source equation: caller Item width is zero before, switchWidth=40; setting
 // width:switchWidth moves the unchanged native Switch exactly 20 CSS pixels.
 const fixed=structuredClone(observed),control=fixed.controls.find(c=>c.kind==='echoCancellation');control.rect.x+=(40/2-40/2)-(0/2-40/2);
 const target=captureControl([fixed],frame,'echoCancellation',true);assert(target);assert(target.rect.x>=0);assert.equal(target.rect.width,old.rect.width);assert.equal(target.rect.height,old.rect.height);
 for(const key of ['sequence','revision','navigationSequence'])assert.equal(captureControl([fixed],{...frame,[key]:frame[key]+1},'echoCancellation',true),null);
 control.rect.x=-1;assert.equal(captureControl([fixed],frame,'echoCancellation',true),null);control.rect.x=0;control.enabled=false;assert.equal(captureControl([fixed],frame,'echoCancellation',true),null);
});
test('generated UI retains complete original widgets handlers and auth script byte-for-byte',()=>{
 const old=oldGenerate(),next=buildBrowserCaptureUI(audio,channel,url);assert.equal(next.script,old.script);assert.equal(stripBrowserCaptureStyle(stripGainPalette(next.qml)).replaceAll('width:switchWidth;height:44;switchWidth:40;labelTextOn:','height:44;switchWidth:40;labelTextOn:'),old.qml);
 assert.throws(()=>buildBrowserCaptureUI(audio+'\n',channel,url));
 for(const id of ['echoControl','noiseControl','agcControl'])assert(next.qml.includes('id:'+id+';width:switchWidth;height:44;switchWidth:40;'));
});

test('width history recovery rejects absent duplicate relocated palette and retains unrelated handler edits',()=>{
 const recovered=stripGainPalette(currentGenerator);
 assert.throws(()=>stripGainPalette(recovered));
 assert.throws(()=>stripGainPalette(currentGenerator.replace(GAIN_ADDITION,GAIN_ADDITION+GAIN_ADDITION)));
 assert.throws(()=>stripGainPalette(currentGenerator.replace('Slider{id:gainControl;'+GAIN_ADDITION,GAIN_ADDITION+'Slider{id:gainControl;')));
 const edited=currentGenerator.replace('onMoved:if(!pressed)','onMoved:if(pressed)');
 assert.notEqual(stripGainPalette(edited),recovered);
 assert.notEqual(createHash('sha256').update(edited).digest('hex'),'9a41d28676ada36d6a54bec5186214963d9864f6cad8c79e7abe666f9d36d7fe');
});
