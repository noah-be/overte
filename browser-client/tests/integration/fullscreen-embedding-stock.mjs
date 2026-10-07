import {observeEmbeddingComposedReady} from './fullscreen-embedding-composed-ready.mjs';
import {installEmbeddingPointerDiagnostic,readEmbeddingPointerDiagnostic} from './fullscreen-embedding-pointer-diagnostic.mjs';
// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Two additional genuine embedding cases; original four registered bodies unchanged.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import puppeteer from 'puppeteer-core';
import {SOURCE_PINS,AUTHORED_FIXTURE_SOURCE,sha,fixtureCallbacks,embeddingOrigins,embeddingDocument,qualifyEmbedding,qualifyDeniedProbe,qualifyCanvasWire,embeddingCaseDeadline as actualCaseDeadline} from './fullscreen-embedding-contract.mjs';

const root=path.resolve(process.env.OVERTE_FULLSCREEN_SOURCE||'');
process.umask(0o077);
const output=path.resolve(process.env.OVERTE_FULLSCREEN_OUTPUT||'');
const origins=embeddingOrigins(process.env.OVERTE_FULLSCREEN_URL||''),origin=origins.parent;
assert(root.endsWith('/browser-client'));assert(output.startsWith('/tmp/')||output.startsWith('/home/user/tmp/'));
await mkdir(output,{mode:0o700});
const sources={};for(const name of Object.keys(SOURCE_PINS)){sources[name]=sha(await readFile(path.join(root,name)));assert.equal(sources[name],SOURCE_PINS[name]);}
const callbacks=fixtureCallbacks(await readFile(path.join(root,AUTHORED_FIXTURE_SOURCE),'utf8'));
const {sizeSystemFirefoxWindow}=await import(pathToFileURL(path.join(root,'tests/integration/system-firefox.mjs')));
const {privateCloneMessage}=await import(pathToFileURL(path.join(root,'tests/integration/replacement-material-clones-diagnostics.mjs')));
const firefox=process.env.OVERTE_FULLSCREEN_BROWSER==='system-firefox';assert(firefox||process.env.OVERTE_FULLSCREEN_BROWSER==='system-chromium');const executable=firefox?process.env.OVERTE_FULLSCREEN_FIREFOX:process.env.OVERTE_FULLSCREEN_CHROMIUM;assert(typeof executable==='string'&&path.isAbsolute(executable));
assert((await stat(executable)).isFile());
const report={version:1,startedAt:new Date().toISOString(),completed:false,scope:'Two actual embedding cases with byte-identical historical authored callbacks; corrected active main spec separately source-pinned; historical stock HTTP-header failure retained',startSources:sources,historicalOriginalBodiesUnchanged:true,activeRegisteredSpecChanged:true,actualNativeTabletQualified:false,cases:[],cleanupVerified:false};
let browser;
const wait=async(page,callback,arg)=>{const handle=await page.waitForFunction(callback,{timeout:10000},arg);try{return await handle.jsonValue();}finally{await handle.dispose();}};
async function clickNamed(page,name){
 const handle=await page.waitForFunction(name=>Array.from(document.querySelectorAll('#fullscreen-tablet-owner button')).find(e=>e.textContent===name&&e.getClientRects().length),{timeout:10000},name);
 try{const element=handle.asElement();assert(element);const before=await page.evaluate(()=>window.__fullscreenTrustedClicks?.length??0);await element.click();
  const clicks=await page.evaluate(()=>window.__fullscreenTrustedClicks);assert.equal(clicks.length,before+1);assert.equal(clicks.at(-1).trusted,true);assert.equal(clicks.at(-1).name,name);
 }finally{await handle.dispose();}
}
const proof=page=>page.evaluate(callbacks.proof);
async function buttonRead(page,name){return page.evaluate(name=>{const e=Array.from(document.querySelectorAll('#fullscreen-tablet-owner button')).find(e=>e.textContent===name);if(!e)return null;const r=e.getBoundingClientRect();return {disabled:e.disabled,aria:e.getAttribute('aria-pressed'),visible:!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden',rect:{x:r.x,y:r.y,width:r.width,height:r.height}};},name);}
async function install(page,url=origin+'/'){
 await page.goto(url);
 await page.evaluate(()=>{window.__fullscreenTrustedClicks=[];document.addEventListener('click',event=>{const b=event.target instanceof Element?event.target.closest('#fullscreen-tablet-owner button'):null;if(b&&['Fullscreen','Exit fullscreen'].includes(b.textContent)){window.__fullscreenTrustedClicks.push({name:b.textContent,trusted:event.isTrusted===true});if(window.__fullscreenTrustedClicks.length>16)window.__fullscreenTrustedClicks.shift();}},{capture:true});});
 await page.evaluate(callbacks.install);
 await wait(page,()=>window.__fullscreenTablet.sent.some(value=>value.action==='frameAck'&&value.displayed===true));
}
async function privateGeometry(page){
 let timer;const task=Promise.resolve().then(()=>page.evaluate(()=>{
  const host=document.getElementById('fullscreen-tablet-owner'),rect=host?.getBoundingClientRect(),v=visualViewport;
  const finite=value=>typeof value==='number'&&Number.isFinite(value)&&Math.abs(value)<=1048576?value:null;
  const r=value=>value?{x:finite(value.x),y:finite(value.y),width:finite(value.width),height:finite(value.height)}:null;
  return {owner:!!host&&document.fullscreenElement===host,host:r(rect),inner:{width:innerWidth,height:innerHeight},nativeDPR:finite(devicePixelRatio),
   visualViewport:v?{offsetLeft:finite(v.offsetLeft),offsetTop:finite(v.offsetTop),width:finite(v.width),height:finite(v.height),scale:finite(v.scale)}:null};
 }));void task.catch(()=>{});
 try{return await Promise.race([task,new Promise(resolve=>{timer=setTimeout(()=>resolve({censored:true}),250);})]);}catch{return {unavailable:true};}finally{clearTimeout(timer);}
}
const noFullscreen=page=>wait(page,()=>document.fullscreenElement===null);
const ownFullscreen=page=>wait(page,()=>document.fullscreenElement?.id==='fullscreen-tablet-owner');
async function disposed(page){await page.evaluate(()=>window.__fullscreenTablet?.tablet.dispose());await noFullscreen(page);}
async function caseRun(kind,callback){
 const context=await browser.createBrowserContext();let page;
 try{
  await actualCaseDeadline(async()=>{page=await context.newPage();await page.bringToFront();if(firefox)await sizeSystemFirefoxWindow(browser,page,{width:1280,height:720});await callback(page);await disposed(page);});
  report.cases.push({kind,passed:true});
 }catch(error){
  report.cases.push({kind,passed:false,failureCategory:error?.name==='TimeoutError'?'actual-case-deadline':'actual-api-pixels-input-or-ownership-refused',privateMessage:privateCloneMessage(error),privateGeometry:page?await privateGeometry(page):null});
  if(page)try{await page.screenshot({path:path.join(output,kind+'-failure.png')});}catch{}
  throw error;
 }finally{try{if(page)await disposed(page);}finally{await context.close();}}
}async function embedding(page,delegated){
 const parentURL=origin+'/fullscreen-owned-parent.html',childURL=origins.child+'/fullscreen-owned-child.html';let handledParent=0,handledChild=0,interceptionFailure,frame;
 const event=request=>{void(async()=>{if(request.url()===parentURL){assert.equal(++handledParent,1);await request.respond(embeddingDocument(origins,delegated));}else if(request.url()===childURL){assert.equal(++handledChild,1);await request.respond({status:200,contentType:'text/html',body:'<!doctype html><html><body></body></html>'});}else await request.continue();})().catch(e=>{interceptionFailure=e;});};await page.setRequestInterception(true);page.on('request',event);
 try{
  await page.goto(parentURL);frame=page.frames().find(f=>f.url()===childURL);assert(frame,'Actual current cross-origin child Frame required');const crossOrigin=new URL(frame.url()).origin!==new URL(page.url()).origin;assert.equal(crossOrigin,true);if(interceptionFailure)throw interceptionFailure;assert.equal(handledParent,1);assert.equal(handledChild,1);
  await frame.evaluate(()=>{window.__fullscreenTrustedClicks=[];window.__ownedFullscreenPointer=[];document.addEventListener('click',e=>{const b=e.target instanceof Element?e.target.closest('#fullscreen-tablet-owner button'):null;if(b&&['Fullscreen','Exit fullscreen'].includes(b.textContent)){const a=window.__fullscreenTrustedClicks;if(a.length>=8)throw Error('Authored click bound');a.push({name:b.textContent,trusted:e.isTrusted===true});}},{capture:true});for(const type of ['pointerdown','pointerup'])document.addEventListener(type,e=>{if(e.target!==document.querySelector('#fullscreen-tablet-owner canvas'))return;const a=window.__ownedFullscreenPointer;if(a.length>=8)throw Error('Authored pointer bound');a.push({type:e.type,trusted:e.isTrusted===true,button:e.button});},{capture:true});});
  await frame.evaluate(callbacks.install);await wait(frame,()=>window.__fullscreenTablet.sent.some(v=>v.action==='frameAck'&&v.displayed===true));
  const parent=await page.evaluate(()=>{const e=document.getElementById('owned-fullscreen-frame');return {delegated:e.hasAttribute('allowfullscreen'),extraAllow:e.hasAttribute('allow'),parentNone:document.fullscreenElement===null};});const before={...await proof(frame),...parent,...await frame.evaluate(()=>{const p=window.__fullscreenTablet,b=Array.from(p.host.querySelectorAll('button')).find(e=>e.textContent==='Fullscreen');return {visible:document.visibilityState==='visible',connected:p.host.isConnected,fullscreenEnabled:document.fullscreenEnabled,buttonDisabled:b.disabled,warning:Array.from(p.host.querySelectorAll('[role=status]')).some(e=>e.textContent==='Fullscreen is unavailable in this browser or embedding.'&&e.getClientRects().length>0)};}),crossOrigin};qualifyEmbedding(before,delegated);report.embeddingWitnesses||=[];const witness={delegated,enabled:before.fullscreenEnabled,disabled:before.buttonDisabled,warning:before.warning,pixel:before.pixel,ratio:before.ratio};report.embeddingWitnesses.push(witness);
  await page.evaluate(installEmbeddingPointerDiagnostic);await frame.evaluate(installEmbeddingPointerDiagnostic);
  const canvas=await frame.$('#fullscreen-tablet-owner canvas');assert(canvas);let bounds;try{witness.composedReadiness=await observeEmbeddingComposedReady(canvas,{privatePngPath:path.join(output,delegated?'delegated-positive-composed.png':'embedding-negative-composed.png')});bounds=await canvas.boundingBox();assert(bounds&&bounds.width>0&&bounds.height>0);await page.mouse.click(bounds.x+bounds.width/2,bounds.y+bounds.height/2);}finally{await canvas.dispose();}witness.pointerDiagnostic={parent:await page.evaluate(readEmbeddingPointerDiagnostic),child:await frame.evaluate(readEmbeddingPointerDiagnostic),requestedBounds:bounds};qualifyCanvasWire(await proof(frame),bounds,await frame.evaluate(()=>window.__ownedFullscreenPointer));witness.actualCanvasInput=true;
  if(delegated){
   await clickNamed(frame,'Fullscreen');await ownFullscreen(frame);assert.equal(await page.evaluate(()=>document.fullscreenElement===document.getElementById('owned-fullscreen-frame')),true);const value=await proof(frame);assert.deepEqual(value.pixel,[40,80,100,255]);assert(Math.abs(value.ratio-480/706)<.0005);assert.equal((await buttonRead(frame,'Exit fullscreen')).aria,'true');await clickNamed(frame,'Exit fullscreen');await noFullscreen(frame);await noFullscreen(page);assert.deepEqual(await frame.evaluate(()=>window.__fullscreenTablet.statuses),[]);witness.actualEnterExit=true;
  }else{
   await frame.evaluate(()=>{const b=document.createElement('button');b.id='owned-fullscreen-api-probe';b.textContent='Probe actual embedded fullscreen permission';Object.assign(b.style,{position:'fixed',right:'4px',top:'4px',zIndex:'1000'});document.body.append(b);window.__ownedFullscreenProbe=null;let count=0;b.addEventListener('click',e=>{const host=window.__fullscreenTablet.host,current={trusted:e.isTrusted===true,calls:++count,visible:document.visibilityState==='visible',connected:host.isConnected,enabled:document.fullscreenEnabled};let operation;try{operation=host.requestFullscreen();}catch(error){window.__ownedFullscreenProbe={...current,rejected:true,name:error?.name,none:document.fullscreenElement===null};return;}void Promise.resolve(operation).then(()=>{window.__ownedFullscreenProbe={...current,rejected:false,name:null,none:document.fullscreenElement===null};},error=>{window.__ownedFullscreenProbe={...current,rejected:true,name:error?.name,none:document.fullscreenElement===null};});});});
   const probe=await frame.$('#owned-fullscreen-api-probe');assert(probe);try{await probe.click();}finally{await probe.dispose();}const denied=await wait(frame,()=>window.__ownedFullscreenProbe);qualifyDeniedProbe(denied);witness.apiDenial=denied;await noFullscreen(frame);await noFullscreen(page);
  }
  await disposed(frame);await noFullscreen(page);if(interceptionFailure)throw interceptionFailure;await page.screenshot({path:path.join(output,delegated?'delegated-positive.png':'embedding-negative.png')});
 }finally{try{if(frame)await disposed(frame);await noFullscreen(page);}finally{page.off('request',event);await page.setRequestInterception(false);}}
}
try{
 assert(/^:[0-9]{1,3}$/.test(process.env.DISPLAY||''));
 browser=await puppeteer.launch({browser:firefox?'firefox':'chrome',protocol:firefox?'webDriverBiDi':'cdp',executablePath:executable,headless:false,defaultViewport:null,userDataDir:path.join(output,'profile'),env:{...process.env,...(!firefox&&process.env.OVERTE_FULLSCREEN_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_FULLSCREEN_CHROMIUM_LIBRARY_PATH}:{})},timeout:30000,protocolTimeout:30000,...(firefox?{extraPrefsFirefox:{'focusmanager.testmode':false}}:{pipe:false,args:['--remote-debugging-address=127.0.0.1','--remote-debugging-port=0']})});
 assert.match(await browser.version(),firefox?/^firefox\/156\./i:/^Chrome\/154\./i);report.stockVersion=await browser.version();const leader=browser.process();assert(leader&&Number.isSafeInteger(leader.pid)&&leader.pid>0);
 await caseRun('actual-cross-origin-no-delegation-denial',page=>embedding(page,false));await caseRun('actual-explicit-fullscreen-delegation-positive',page=>embedding(page,true));report.completed=true;
}catch(error){process.exitCode=1;report.privateMessage=privateCloneMessage(error);report.failureCategory=error?.name==='TimeoutError'?'actual-stock-deadline':'actual-stock-source-api-or-case-refused';}
finally{
 if(browser){try{const process=browser.process();assert(process);await browser.close();report.cleanupVerified=process.exitCode!==null;}catch{report.cleanupVerified=false;process.exitCode=1;}}
 const end={};for(const name of Object.keys(SOURCE_PINS))end[name]=sha(await readFile(path.join(root,name)));report.endSources=end;report.sourceCoherent=JSON.stringify(end)===JSON.stringify(sources);if(!report.sourceCoherent||!report.cleanupVerified){report.completed=false;process.exitCode=1;}
 report.finishedAt=new Date().toISOString();report.originalFourBodiesExecuted=false;report.headerNegativeRequalified=false;await writeFile(path.join(output,'report.private.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx',mode:0o600});console.log(JSON.stringify({completed:report.completed,cases:report.cases.map(v=>({kind:v.kind,passed:v.passed})),cleanupVerified:report.cleanupVerified,sourceCoherent:report.sourceCoherent,originalFourBodiesExecuted:false,headerNegativeRequalified:false}));
}
