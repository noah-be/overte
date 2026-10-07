// Copyright 2026 Overte contributors
import {selectGoogleChromeJourney} from './chrome-journey-selection.mjs';
// SPDX-License-Identifier: Apache-2.0
// Genuine authored native Emote UI; no native setter or synthetic web event.
import {chromium} from '@playwright/test';import {launchSystemFirefox} from './system-firefox.mjs';
import assert from 'node:assert/strict';import {mkdir,readFile,writeFile,open,lstat,readdir,realpath} from 'node:fs/promises';import {constants} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';import path from 'node:path';import {tmpdir} from 'node:os';import {fileURLToPath} from 'node:url';
import {buildBrowserEmoteOverride} from '../../gateway/tablet-emote.mjs';import {gunzipSync} from 'node:zlib';
import {workerProfiles,freshWorkerProfile} from './tablet-create-selection.mjs';import {readCreateWorkerLog} from './tablet-create-readiness.mjs';
import {assertIsolatedCreateTarget,baselineIdentity} from './tablet-create-contract.mjs';import {createPeopleFrameAcknowledgement} from './tablet-people-audit.mjs';
import {currentSitFrameMetadata,sampleSitDisplayedControl,freshSitClickCoordinates,sitProofQueueInstallerSource} from './tablet-sit-proof-queue.mjs';
import {finishSitLifecycle} from './tablet-sit-lifecycle.mjs';
import {sitCopiedSourceHashes} from './tablet-sit-source.mjs';
import {parseEmoteHomeAudit,emoteHomeControl,instrumentEmoteView,instrumentEmoteEvents,parseEmoteAudit,EMOTE_PREFIX,VIEW_PREFIX,emoteControl,assertPaintedEmoteControl,sitPose,sitDifference,actualRigMatches,SIT_JOINTS,angle} from './tablet-sit-audit.mjs';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..'),client=path.join(repo,'browser-client'),base=process.env.OVERTE_LAB_URL||'http://127.0.0.1:8095',domain='overte://127.0.0.2:45102';assertIsolatedCreateTarget(base,domain);
const directory=path.join(repo,'build/browser-lab/evidence/tablet-sit',randomUUID()),sha=b=>createHash('sha256').update(b).digest('hex'),delay=ms=>new Promise(r=>setTimeout(r,ms));
const sources=['tests/integration/chrome-journey-selection.mjs','tests/google-chrome-selection.mjs','tests/integration/tablet-sit-session.mjs','tests/integration/tablet-sit-audit.mjs','tests/integration/prepare-tablet-sit-audit.mjs','tests/integration/tablet-sit-proof-queue.mjs','tests/integration/tablet-sit-lifecycle.mjs','tests/integration/tablet-sit-source.mjs','tests/integration/tablet-create-readiness.mjs','tests/integration/tablet-create-selection.mjs','tests/integration/tablet-create-contract.mjs','gateway/fixtures/native-emote-f91d15a.js.gz','package.json','package-lock.json','tests/integration/system-firefox.mjs','tests/integration/tablet-people-audit.mjs','gateway/tablet-emote.mjs','gateway/server.mjs','gateway/worker-sandbox.mjs','gateway/native-bridge.js','gateway/native-tablet.js','gateway/tablet-capture.qml','src/avatar-rig.ts','src/world.ts','src/main.ts','src/session.ts','dist/index.html'];
async function hashes(){
 const result=Object.fromEntries(await Promise.all(sources.map(async f=>[f,sha(await readFile(path.join(client,f)))])));
 async function assets(relative){for(const entry of await readdir(path.join(client,'dist',relative),{withFileTypes:true})){const file=path.posix.join(relative,entry.name);if(entry.isDirectory())await assets(file);else if(entry.isFile()&&/\.(?:js|css|wasm)$/.test(file))result['dist/'+file]=sha(await readFile(path.join(client,'dist',file)));}}
 await assets('');return Object.fromEntries(Object.entries(result).sort(([a],[b])=>a.localeCompare(b)));
}
const privateProofs=new Map();let proofOrdinal=0,copiedClient;
async function copiedHashes(){assert(copiedClient);return sitCopiedSourceHashes(copiedClient);}
async function flushProofs(){
 if(!page){assert.equal(privateProofs.size,0);return;}
 const meta=await page.evaluate(()=>window.__sitAudit?.proofs?.metadata()??{ordinals:[],count:0,bytes:0});assert.deepEqual(meta.ordinals,[...privateProofs.keys()]);assert.equal(meta.count,privateProofs.size);assert(meta.count<=16&&meta.bytes<=32*1024*1024);
 for(const id of meta.ordinals){const data=await page.evaluate(id=>window.__sitAudit.proofs.read(id),id),saved=privateProofs.get(id);assert.equal(data.proofOrdinal,id);assert.deepEqual(data.frame,saved.frame);assert.deepEqual(data.canvas,saved.canvas);assert.equal(data.image.width,saved.image.width);assert.equal(data.image.height,saved.image.height);assertPaintedEmoteControl(data.image);const png=Buffer.from(data.nativePNG,'base64');assert(png.length>0&&png.length<=2*1024*1024);
  await writeFile(saved.file+'-native.png',png,{flag:'wx',mode:0o600});await writeFile(saved.file+'-displayed-control.rgba',Buffer.from(data.image.rgba),{flag:'wx',mode:0o600});await writeFile(saved.file+'-displayed-control.json',JSON.stringify({width:data.image.width,height:data.image.height,frame:data.frame}),{flag:'wx',mode:0o600});await page.evaluate(id=>window.__sitAudit.proofs.release(id),id);privateProofs.delete(id);
 }
}
async function waitFor(fn,label,timeout=10000){const until=Date.now()+timeout;while(Date.now()<until){const r=await fn();if(r)return r;await delay(100);}throw Error(label+' deadline');}
async function runtimeFile(profile,name,expected){const dir=await open(profile,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);let file;try{file=await open('/proc/self/fd/'+dir.fd+'/'+name,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);const st=await file.stat();assert(st.isFile()&&st.size<=128*1024);const b=Buffer.alloc(st.size);let n=0;while(n<b.length){const r=await file.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}assert.equal(b.subarray(0,n).toString(),expected);return sha(b.subarray(0,n));}finally{await file?.close();await dir.close();}}
const report={startedAt:new Date().toISOString(),completed:false,microphoneEnabled:false,scope:'Owned isolated native Emote Sit/random variant and genuine key Stop; exact native/browser hip and leg readback, no entity writes',steps:[],cleanupVerified:false};let browser,page,profile,baseline,start;
try{
 await mkdir(directory,{recursive:true,mode:0o700});start=await hashes();report.startSourceSHA256=start;report.startShippingSnapshotSHA256=await sitCopiedSourceHashes(client);
 copiedClient=await realpath(process.env.OVERTE_SIT_AUDIT_CLIENT);assert(copiedClient!==client);report.startCopiedSourceSHA256=await copiedHashes();
 const original=gunzipSync(await readFile(path.join(client,'gateway/fixtures/native-emote-f91d15a.js.gz')),{maxOutputLength:32768}).toString();
 const expectedScript=instrumentEmoteEvents(buildBrowserEmoteOverride(original)),expectedQml=instrumentEmoteView(await readFile(path.join(client,'gateway/tablet-capture.qml'),'utf8'));
 const prepared=JSON.parse(await readFile(path.join(path.dirname(copiedClient),'audit-manifest.private.json'),'utf8'));assert.equal(prepared.version,2);assert.deepEqual(prepared.shippingSourceSHA256,report.startShippingSnapshotSHA256);assert.deepEqual(prepared.copiedSourceSHA256,report.startCopiedSourceSHA256);
 const expectedSnapshot={...report.startShippingSnapshotSHA256,'gateway/tablet-capture.qml':sha(expectedQml),'gateway/tablet-emote.mjs':prepared.copiedAdapterSHA256};assert.deepEqual(report.startCopiedSourceSHA256,expectedSnapshot,'Only exact reviewed capture/Emote adapter instrumentation may differ from Root');
 const sourceAdapter=await readFile(path.join(client,'gateway/tablet-emote.mjs'),'utf8'),marker='const generated=buildBrowserEmoteOverride(await readTrusted(target));';assert.equal(sourceAdapter.split(marker).length,2);const expectedAdapter="import {instrumentEmoteEvents} from '../tests/integration/tablet-sit-audit.mjs';\n"+sourceAdapter.replace(marker,'const generated=instrumentEmoteEvents(buildBrowserEmoteOverride(await readTrusted(target)));');assert.equal(prepared.copiedAdapterSHA256,sha(expectedAdapter));assert.equal(prepared.shippingCaptureSHA256,start['gateway/tablet-capture.qml']);assert.equal(prepared.shippingAdapterSHA256,start['gateway/tablet-emote.mjs']);assert.equal(prepared.copiedCaptureSHA256,sha(expectedQml));assert.equal(prepared.copiedEmoteGeneratedSHA256,sha(expectedScript));
 const display=process.env.OVERTE_LAB_BROWSER_DISPLAY,env={...process.env,...(display?{DISPLAY:display}:{})};
 browser=await chromium.launch({headless:!display,...selectGoogleChromeJourney(process.env),env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:[...(!display?['--use-angle=swiftshader']:[]),'--mute-audio']});
 report.browserVersion=await browser.version();const context=await browser.newContext({viewport:{width:1280,height:800}});page=await context.newPage();
 await page.addInitScript(sitProofQueueInstallerSource(sampleSitDisplayedControl,assertPaintedEmoteControl));
 await page.addInitScript('window.__sitFrameAck=('+createPeopleFrameAcknowledgement.toString()+')();');
 await page.addInitScript(()=>{const Original=window.WebSocket;window.__sitAudit={proofs:window.__sitProofFactory(),frame:null,frames:[],state:null,own:null,selfId:null,entities:new Map(),errors:[],baseline:null,entityChanged:false,avatarBatches:0};
  const canonical=id=>String(id).replace(/[{}]/g,'').toLowerCase(),identity=entities=>JSON.stringify([...entities.values()].map(e=>({id:e.id,name:e.name,type:e.type})).sort((a,b)=>a.id.localeCompare(b.id)));
  window.WebSocket=class extends Original{constructor(...args){super(...args);this.addEventListener('message',e=>{if(typeof e.data!=='string')return;try{const m=JSON.parse(e.data),a=window.__sitAudit;
   if(m.type==='avatars'){a.selfId=m.selfId;a.own=m.avatars.find(v=>canonical(v.id)===canonical(m.selfId));a.avatarBatches++;}
   if(m.type==='entities')a.entities=new Map(m.entities.map(v=>[v.id,v]));
   if(m.type==='entityUpdates'){for(const id of m.removed)a.entities.delete(id);for(const v of m.entities)a.entities.set(v.id,v);}
   if((m.type==='entities'||m.type==='entityUpdates')&&a.baseline&&identity(a.entities)!==a.baseline)a.entityChanged=true;
   if(m.type==='tablet'){if(m.kind==='frame'){a.frames.push(m);if(a.frames.length>16)a.frames.shift();}else if(m.kind==='state')a.state=m;else if(m.kind==='error')a.errors.push(m.message);}
  }catch{}});}send(data){if(typeof data==='string')try{const m=JSON.parse(data),a=window.__sitAudit;if(m.type==='tablet'){if(['open','home','back','close'].includes(m.action))a.frame=null;const f=window.__sitFrameAck(m,a.frames);if(f)a.frame=f;}}catch{}super.send(data);}};
 });
 const before=await workerProfiles(tmpdir());report.step='join-isolated';await page.goto(base);await page.locator('#domain').fill(domain);await page.locator('#name').fill('Owned Sit Audit');await page.locator('#join').click();
 await page.waitForFunction(()=>window.__overte?.connected&&window.__sitAudit.entities.size===7&&window.__sitAudit.own?.jointNames?.includes('LeftUpLeg')&&window.__overte.avatarRig?.joints?.LeftUpLeg,undefined,{timeout:90000});
 profile=freshWorkerProfile(before,await workerProfiles(tmpdir()));report.runtimeCaptureSHA256=await runtimeFile(profile,'tablet-capture.qml',expectedQml);report.runtimeEmoteSHA256=await runtimeFile(profile,'browser-emote.js',expectedScript);
 baseline=baselineIdentity(await page.evaluate(()=>[...window.__sitAudit.entities.values()]));assert.equal(baseline.length,7);assert(baseline.every(v=>v.name.startsWith('Browser Lab ')));
 await page.evaluate(()=>{const a=window.__sitAudit;a.baseline=JSON.stringify([...a.entities.values()].map(e=>({id:e.id,name:e.name,type:e.type})).sort((x,y)=>x.id.localeCompare(y.id)));});report.baselineIdentitySHA256=sha(JSON.stringify(baseline));
 async function sample(){const r=await page.evaluate(()=>({own:window.__sitAudit.own,rig:window.__overte.avatarRig,entityChanged:window.__sitAudit.entityChanged,connected:window.__overte.connected,batches:window.__sitAudit.avatarBatches}));assert(r.connected&&!r.entityChanged);const pose=sitPose(r.own);return {pose,matched:actualRigMatches(r.rig,pose),batches:r.batches};}
 const initial=await waitFor(async()=>{const s=await sample();return s.matched?s:null;},'Actual default rig/native joint agreement');
 const canvas=page.getByLabel('Native tablet apps and dialogs');await page.locator('#tablet').click();await page.waitForFunction(()=>window.__sitAudit.frame?.tabletRect,undefined,{timeout:30000});
 async function save(label){const f=await page.evaluate(()=>window.__sitAudit.frame);assert(f);await writeFile(path.join(directory,label+'-native.png'),Buffer.from(f.data,'base64'),{mode:0o600});await writeFile(path.join(directory,label+'-displayed.png'),Buffer.from((await canvas.evaluate(e=>e.toDataURL('image/png'))).split(',')[1],'base64'),{mode:0o600});report.steps.push({label,sequence:f.sequence,revision:f.revision,navigationSequence:f.navigationSequence,surface:f.surface,width:f.width,height:f.height});return f;}
 async function proofPoint(control,label){
  const small=await canvas.evaluate((el,control)=>window.__sitAudit.proofs.sample(el,control),control);if(small.refusal){report.calibrationRefusal=small.refusal;return null;}
  assert(privateProofs.size<16&&Number.isSafeInteger(small.proofOrdinal)&&!privateProofs.has(small.proofOrdinal));privateProofs.set(small.proofOrdinal,{file:path.join(directory,label+'-'+(++proofOrdinal)),frame:small.frame,canvas:small.canvas,image:small.image});return control;
 }
 async function click(point){const small=await canvas.evaluate(freshSitClickCoordinates,point);assert.equal(small.refusal,null,'Exact displayed frame/revision/navigation must still own the genuine Sit pointer');await page.mouse.click(small.x,small.y);}
 const first=await page.evaluate(currentSitFrameMetadata);await page.getByRole('button',{name:'Home',exact:true}).click();await page.waitForFunction(seq=>window.__sitAudit.frame?.sequence>seq&&window.__sitAudit.state?.screen==='Home',first.sequence,{timeout:20000});
 const home=await waitFor(async()=>{const frame=await page.evaluate(currentSitFrameMetadata);if(!frame)return null;const control=emoteHomeControl(parseEmoteHomeAudit(await readCreateWorkerLog(profile)),frame);return control?await proofPoint(control,'home-emote'):null;},'Unique ACK-paired actual painted native EMOTE Home control',20000);await click(home);
 const count=parseEmoteAudit(await readCreateWorkerLog(profile),EMOTE_PREFIX).length;
 report.step='calibrate-genuine-painted-Sit';const target=await waitFor(async()=>{const frame=await page.evaluate(currentSitFrameMetadata);if(!frame)return null;const control=emoteControl(parseEmoteAudit(await readCreateWorkerLog(profile),VIEW_PREFIX),frame);return control?await proofPoint(control,'emote-before-Sit'):null;},'Exact ACK-paired authored Emote Sit control',20000);
 const clickedAt=Date.now();report.step='genuine-Sit';await click(target);
 const action=await waitFor(async()=>{const a=parseEmoteAudit(await readCreateWorkerLog(profile),EMOTE_PREFIX).slice(count).filter(v=>v.kind==='override-returned'&&/^Sit[123]$/.test(v.name));assert(a.length<=1);return a[0]||null;},'Authored native Sit override returned',10000);assert(Number.isSafeInteger(action.frames)&&action.frames>0&&action.frames<=600&&action.fps===60);report.nativeAction={variant:action.name,frames:action.frames,fps:action.fps};
 let held;
 const seated=await waitFor(async()=>{const s=await sample(),d=sitDifference(initial.pose,s.pose);if(Date.now()-clickedAt<action.frames/action.fps*1000+100||!s.matched||s.batches<=initial.batches||d.hipsDrop<=20||d.maximumThighChange<=.5)return null;
  if(!held){held={at:Date.now(),sample:s};return null;}if(Date.now()-held.at<500)return null;
  if(Math.abs(held.sample.pose.Hips.position.y-s.pose.Hips.position.y)>1||Math.max(...SIT_JOINTS.map(n=>angle(held.sample.pose[n].orientation,s.pose[n].orientation)))>.05){held={at:Date.now(),sample:s};return null;}return {sample:s,difference:d};
 },'Actual held native sitting pose applied to real browser hip/leg bones',10000);report.sitDifference=seated.difference;report.appliedJointCount=SIT_JOINTS.length;await flushProofs();await save('emote-seated');
 report.step='genuine-key-Stop';const restoredCount=parseEmoteAudit(await readCreateWorkerLog(profile),EMOTE_PREFIX).filter(v=>v.kind==='restore-control-returned').length;await page.keyboard.press('x');
 await waitFor(async()=>parseEmoteAudit(await readCreateWorkerLog(profile),EMOTE_PREFIX).filter(v=>v.kind==='restore-control-returned').length>restoredCount,'Native authored restore control returned',10000);
 const stopped=await waitFor(async()=>{const s=await sample(),d=sitDifference(initial.pose,s.pose);return s.matched&&s.batches>seated.sample.batches&&Math.abs(d.hipsDrop)<10&&d.maximumThighChange<.35?{sample:s,difference:d}:null;},'Actual standing native/default browser pose restored after key',10000);report.restoredDifference=stopped.difference;await save('emote-stopped');
 await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.keyboard.press('v');await page.waitForFunction(()=>window.__overte.avatarRender?.thirdPerson&&window.__overte.avatarRender?.selfVisible&&window.__overte.performance.graphicsActive,undefined,{timeout:10000});await page.screenshot({path:path.join(directory,'browser-restored.png')});
 assert.deepEqual(await page.evaluate(()=>window.__sitAudit.errors),[]);assert(await page.evaluate(()=>document.querySelector('#microphone').getAttribute('aria-pressed')==='false'));report.completed=true;
}catch(e){report.completed=false;report.failure=String(e.message||e).slice(0,1024);process.exitCode=1;if(page)try{const f=await page.evaluate(()=>window.__sitAudit.frame);if(f)await writeFile(path.join(directory,'failure-native.png'),Buffer.from(f.data,'base64'),{mode:0o600});report.tabletErrors=await page.evaluate(()=>window.__sitAudit.errors);}catch{}}
finally{
 if(page&&baseline)try{assert.deepEqual(baselineIdentity(await page.evaluate(()=>[...window.__sitAudit.entities.values()])),baseline);assert(await page.evaluate(()=>!window.__sitAudit.entityChanged));report.baselineUnchanged=true;}catch{report.completed=false;process.exitCode=1;report.baselineUnchanged=false;}
 if(profile)try{await writeFile(path.join(directory,'worker.private.log'),await readCreateWorkerLog(profile),{mode:0o600});}catch{report.workerLogUnavailable=true;}
 if(page)try{await page.bringToFront();if(await page.evaluate(()=>window.__overte?.tabletVisible))await page.getByRole('button',{name:'Close tablet',exact:true}).click();if(await page.evaluate(()=>window.__overte?.connected))await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte?.connected&&!window.__overte?.tabletVisible,undefined,{timeout:10000});}catch{report.completed=false;report.leaveFailed=true;process.exitCode=1;}
 try{await flushProofs();}catch{report.completed=false;report.controlEvidenceFailed=true;process.exitCode=1;}
 try{if(page)await page.evaluate(()=>window.__sitAudit?.proofs?.retire());}catch{report.completed=false;report.proofRetirementFailed=true;process.exitCode=1;}
 const accepted=await finishSitLifecycle(report,{
  closeBrowser:async()=>{await browser?.close();if(!browser)throw Error('No owned browser');},
  removeOwnedProfile:async()=>{if(!profile)return false;await waitFor(async()=>{try{await lstat(profile);return false;}catch(e){if(e.code==='ENOENT')return true;throw e;}},'Exact owned profile removal',12000);return !!baseline;},
  attest:async()=>{report.endSourceSHA256=await hashes();report.endCopiedSourceSHA256=await copiedHashes();report.endShippingSnapshotSHA256=await sitCopiedSourceHashes(client);return JSON.stringify(report.startShippingSnapshotSHA256)===JSON.stringify(report.endShippingSnapshotSHA256)&& !!start&&JSON.stringify(start)===JSON.stringify(report.endSourceSHA256)&&JSON.stringify(report.startCopiedSourceSHA256)===JSON.stringify(report.endCopiedSourceSHA256);},
  persist:async()=>{await mkdir(directory,{recursive:true,mode:0o700});await writeFile(path.join(directory,'report.private.json'),JSON.stringify(report,null,2)+'\n',{mode:0o600});console.log(JSON.stringify({completed:report.completed,cleanupVerified:report.cleanupVerified,sourceCoherent:report.sourceCoherent,reportSHA256:sha(JSON.stringify(report))}));}
 });if(!accepted)process.exitCode=1;
}
