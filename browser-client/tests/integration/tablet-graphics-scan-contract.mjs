// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {validateBrowserGraphics} from '../../shared/browser-graphics.mjs';
export const SCAN_SOURCE_PINS=Object.freeze({
'src/world.ts':'66fd95766c79f4deb78400e342fd19cbc19d55a127b75c53f00da09061d660da',
'src/main.ts':'58930f7e982e7c5304503ecd0c4f1a9c8b1ae8062bc07fb9f2d2c4818d8d18f7',
'src/tablet.ts':'d0624d76d2bffa2f60dfeaaefd0e53e6f5a5798f635183ba04c75a983e32e7a6',
'gateway/native-tablet.js':'53238a8ca18606137b146b43c93a7f53c9c81305482577fcc3078309594e7c0c',
'src/graphics-environment-scan.ts':'308cceab6b7d07ee52bf582be6c531128dcc72ae4d5abd8c3f849e587c896d5c',
'src/graphics-environment-panel.ts':'347fcdc6289229d813106abd2d48f3b501a6a61ba94567f93c28e13c2b1d134d',
 'tests/integration/system-firefox.mjs':'375416100da67828ba3b91962fff5e8d72d41b64144562eb0e234a48eea639c5',
});
export function assertSourcePins(value){for(const [file,sha]of Object.entries(SCAN_SOURCE_PINS))assert.equal(value[file],sha,'Exact reviewed graphics scan source required');}
export function qualifyScan(before,after){
 assert.equal(after.connected,true);assert.equal(after.censored,false);assert.deepEqual(validateBrowserGraphics(after.settings),validateBrowserGraphics(before.settings));
 assert.equal(after.width,before.width);assert.equal(after.height,before.height);assert.equal(after.nativeDPR,before.nativeDPR);
 assert.deepEqual(after.commands,before.commands,'Scan itself sends no graphics change/request/result');
 assert(after.rendered-before.rendered>=13,'At least13 successful existing World renders');assert(after.observedAt-before.observedAt>=2000,'Existing scan observes a genuine2-second span');
 assert(after.home.sequence>before.frame.sequence&&after.home.revision===before.frame.revision&&after.home.visible===true&&after.home.screen==='Home','Fresh actual native Home frame after scan');
 const text=after.status;assert(typeof text==='string'&&text.length<=2048);const match=/WebGL2; buffer (\d+)×(\d+) at scan start; observed (\d+(?:\.\d+)?) Hz, p95 (\d+(?:\.\d+)?) ms in this model-jobs-idle view; images\/materials may still arrive\./.exec(text);assert(match,'Actual scanner differentiates environment and sampled view');
 assert.equal(Number(match[1]),before.width);assert.equal(Number(match[2]),before.height);assert(Number(match[3])>0&&Number(match[3])<=10000);assert(Number(match[4])>=0&&Number(match[4])<=5000);
 assert(text.includes('Keep the current settings. This short sample')||text.includes('Keep the current settings by default.'));assert.equal(typeof after.applyDisabled,'boolean');
 if(after.applyDisabled){assert(!text.includes('Optional: try '));return {optional:null,cadenceHz:Number(match[3]),p95Ms:Number(match[4])};}
 const optional=/Optional: try (\d+)% resolution/.exec(text);assert(optional);const value=Number(optional[1]);assert.equal(value,Math.max(10,before.settings.resolutionPercent-10));assert(before.settings.resolutionPercent>10);
 // The UI rounds to one decimal; admission remains the unchanged scanner's
 // strict <30Hz/>50ms condition, not this descriptive rounded projection.
 assert(Number(match[3])<=30.05||Number(match[4])>=49.95,'Rounded text must be compatible with an actually slow source sample');
 return {optional:value,cadenceHz:Number(match[3]),p95Ms:Number(match[4])};
}
export function qualifyApplied(before,after,wanted){
 const intent=after.intent,request=after.request,ack=after.ack,completion=after.completion;
 assert(intent&&request&&ack&&completion);assert.equal(intent.action,'graphicsChange');assert.equal(intent.schemaVersion,1);assert(Number.isSafeInteger(intent.browserRequestId)&&intent.browserRequestId>=1);
 assert.equal(intent.field,'resolutionPercent');assert.equal(intent.value,wanted);assert.equal(request.operation,'change');assert.equal(request.field,'resolutionPercent');assert.equal(request.value,wanted);
 assert.equal(request.browserRequestId,intent.browserRequestId);assert.equal(ack.requestId,request.requestId);assert.equal(completion.browserRequestId,intent.browserRequestId);
 for(const value of [intent,request,ack,completion])assert.equal(value.revision,before.frame.revision);
 assert.equal(ack.accepted,true);assert.equal(completion.accepted,true);assert(intent.observedAt<=request.observedAt&&request.observedAt<=ack.observedAt&&ack.observedAt<=completion.observedAt,'Native cached completion follows ordinary effective ACK');
 const expected={...before.settings,resolutionPercent:wanted};assert.deepEqual(validateBrowserGraphics(after.settings),expected);assert.deepEqual(validateBrowserGraphics(ack.settings),expected);assert.deepEqual(validateBrowserGraphics(completion.settings),expected);assert.deepEqual(validateBrowserGraphics(after.persisted),expected);
 assert.equal(after.connected,true);assert.equal(after.censored,false);return expected;
}
/** Source-pinned SettingSlider has a16x36 gray handle within20x40 black border. */
export function measureNativeResolutionThumb(canvas,input){
 const rect=input?.rect,y=input?.y;if(!rect||![rect.x,rect.y,rect.width,rect.height,y].every(Number.isFinite)||canvas.width*canvas.height>4_000_000||rect.x<0||rect.y<0||rect.width<1||rect.height<1||rect.x+rect.width>canvas.width+1||rect.y+rect.height>canvas.height+1||y<80||y>630)throw Error('Native slider bounds refused');
 const ctx=canvas.getContext('2d');if(!ctx)throw Error('Native slider pixels unavailable');const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data,runs=[];let start=null;
 for(let x=270;x<=460;x++){let grey=0;for(let dy=-15;dy<=15;dy++){const xx=Math.floor(rect.x+x*rect.width/480),yy=Math.floor(rect.y+(y+dy)*rect.height/706);if(xx<0||yy<0||xx>=canvas.width||yy>=canvas.height)throw Error('Native slider crop refused');const i=(yy*canvas.width+xx)*4;if(pixels[i+3]>240&&Math.abs(pixels[i]-128)<=2&&Math.abs(pixels[i+1]-128)<=2&&Math.abs(pixels[i+2]-128)<=2)grey++;}if(grey>=27){if(start===null)start=x;}else if(start!==null){runs.push({start,end:x-1});start=null;}}
 if(start!==null)runs.push({start,end:460});const candidates=runs.filter(r=>r.end-r.start+1>=14&&r.end-r.start+1<=18);if(candidates.length!==1)throw Error('Exactly one authentic gray native slider handle required');return {x:(candidates[0].start+candidates[0].end)/2,width:candidates[0].end-candidates[0].start+1};
}
