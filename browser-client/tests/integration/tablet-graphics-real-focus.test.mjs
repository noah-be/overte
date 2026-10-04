// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {EventEmitter} from 'node:events';import {readFile,mkdtemp,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import path from 'node:path';
import {openActualGraphicsChromium,requireActualGraphicsPage,sizeActualGraphicsPage,readActualScanVisibility} from './tablet-graphics-real-focus.mjs';
const config={executablePath:'/reviewed/owned-chromium',env:{DISPLAY:':95'}};
function fixture({count=1,endpoint='ws://127.0.0.1:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef',connectFailure,ownerFailure,controllerFailure,noProcess=false}={}){
 const calls=[],leader=new EventEmitter();Object.assign(leader,{pid:123,exitCode:null,signalCode:null});
 const context={get grantPermissions(){throw Error('Graphics may not grant permissions');},get newCDPSession(){throw Error('No direct CDP or override');}};
 const owner={process:()=>noProcess?null:leader,wsEndpoint:()=>endpoint,async close(){calls.push('owner-close');leader.exitCode=0;leader.emit('close',0,null);if(ownerFailure)throw ownerFailure;}};
 const controller={contexts:()=>Array(count).fill(context),version:()=> 'authored-no-browser',get newContext(){throw Error('No new emulated context');},async close(){calls.push('controller-close');if(controllerFailure)throw controllerFailure;}};
 return {calls,leader,context,owner,controller,drivers:{async launch(v){calls.push(['launch',v]);return owner;},async connect(e,v){calls.push(['connect',e,v]);if(connectFailure)throw connectFailure;return controller;}}};
}
test('actual Graphics public launcher uses fresh noDefaults existing context, no media or permission grants',async()=>{
 const f=fixture(),r=await openActualGraphicsChromium(config,f.drivers),v=f.calls[0][1];assert.deepEqual(v,{browser:'chrome',protocol:'cdp',executablePath:config.executablePath,headless:false,defaultViewport:null,pipe:false,env:config.env,timeout:30000,protocolTimeout:30000,args:['--remote-debugging-address=127.0.0.1','--remote-debugging-port=0']});
 assert.deepEqual(f.calls[1],['connect',f.owner.wsEndpoint(),{noDefaults:true,isLocal:true,timeout:30000}]);assert.equal(r.context,f.context);assert.equal(r.browser.newContext,undefined);
 assert.deepEqual(requireActualGraphicsPage(f.context,{context:()=>f.context}),{scope:'actual-Chromium-default-context-no-overrides',focusOverridesSkipped:true});await r.browser.close();await r.browser.close();assert.deepEqual(f.calls.slice(-2),['owner-close','controller-close']);assert.equal(f.calls.filter(c=>c==='owner-close').length,1);assert.equal(r.readOwnership().ownedLeaderClosed,true);assert.equal(f.leader.listenerCount('close'),0);assert.equal(f.leader.listenerCount('error'),0);assert.throws(()=>requireActualGraphicsPage(f.context,{context:()=>f.context}),/fresh noDefaults/);
});
test('foreign/ambiguous context, missing process and endpoint refuse before page/permission overrides',async()=>{
 for(const count of [0,2]){const f=fixture({count});await assert.rejects(openActualGraphicsChromium(config,f.drivers),/Exactly one/);assert.deepEqual(f.calls.slice(-2),['owner-close','controller-close']);}
 for(const endpoint of ['ws://remote.invalid:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef','ws://secret@127.0.0.1:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef','ws://127.0.0.1:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef?private=1']){const f=fixture({endpoint});await assert.rejects(openActualGraphicsChromium(config,f.drivers),/loopback/);assert.equal(f.calls.filter(c=>Array.isArray(c)&&c[0]==='connect').length,0);assert.equal(f.calls.at(-1),'owner-close');}
 const f=fixture({noProcess:true});await assert.rejects(openActualGraphicsChromium(config,f.drivers),/process required/);assert.equal(f.calls.at(-1),'owner-close');assert.throws(()=>requireActualGraphicsPage({},{get context(){throw Error('Do not access a foreign page');}}),/fresh noDefaults/);
});
test('setup and either cleanup failure remain failure while all owned transports close',async()=>{
 const failure=Error('Authored owned refusal'),f=fixture({connectFailure:failure});await assert.rejects(openActualGraphicsChromium(config,f.drivers),e=>e===failure);assert.equal(f.calls.at(-1),'owner-close');
 for(const field of ['ownerFailure','controllerFailure']){const f=fixture({[field]:failure}),r=await openActualGraphicsChromium(config,f.drivers);await assert.rejects(r.browser.close(),e=>e instanceof AggregateError&&e.errors.includes(failure));assert.deepEqual(f.calls.slice(-2),['owner-close','controller-close']);}
 const e=fixture(),r=await openActualGraphicsChromium(config,e.drivers);e.leader.emit('error',failure);await assert.rejects(r.browser.close(),/cleanup refused/);assert.equal(r.readOwnership().ownedLeaderClosed,false);
});
test('invalid launch inputs refuse without launch or untrusted environment mutation',async()=>{
 const f=fixture();for(const value of [{...config,executablePath:'relative'},{...config,env:{DISPLAY:'remote:95'}},{...config,env:{DISPLAY:':1000'}}])await assert.rejects(openActualGraphicsChromium(value,f.drivers),/Invalid owned/);assert.deepEqual(f.calls,[]);
});
test('actual installed Puppeteer argument builder keeps loopback port/profile/sandbox and ordinary media defaults',async()=>{
 const {ChromeLauncher}=await import(new URL('./node/ChromeLauncher.js',import.meta.resolve('puppeteer-core'))),directory=await mkdtemp(path.join(tmpdir(),'overte-graphics-args-')),f=fixture(),r=await openActualGraphicsChromium(config,f.drivers);
 try{const launcher=new ChromeLauncher({_isPuppeteerCore:true},()=>{});launcher.getProfilePath=async()=>path.join(directory,'profile-');const actual=await launcher.computeLaunchArguments(f.calls[0][1]);assert(actual.isTempUserDataDir);assert(actual.userDataDir.startsWith(directory+path.sep));assert.equal(actual.args.filter(a=>a.startsWith('--user-data-dir=')).length,1);assert(actual.args.includes('--remote-debugging-address=127.0.0.1'));assert(actual.args.includes('--remote-debugging-port=0'));assert(!actual.args.includes('--no-sandbox'));assert(!actual.args.some(a=>/fake|use-angle|disable-web-security|force-device-scale-factor/.test(a)));}
 finally{await r.browser.close();await rm(directory,{recursive:true,force:true});}
});
test('actual installed Playwright override condition exposes original fresh-context counterfactual',async()=>{
 const body=await readFile(new URL('../../node_modules/playwright-core/lib/coreBundle.js',import.meta.url),'utf8'),expression=/const skipDefaultOverrides = (browserOptions\.noDefaults[^;]+);/.exec(body)?.[1];assert(expression);
 const decide=new Function('browserOptions','return ('+expression+');'),defaultContext={},other={};
 const scope=c=>({_crPage:{_browserContext:Object.assign(c,{_browser:{_defaultContext:defaultContext}})}});
 assert.equal(decide.call(scope(defaultContext),{noDefaults:true}),true);assert.equal(decide.call(scope(other),{noDefaults:true}),false);assert.equal(decide.call(scope(defaultContext),{noDefaults:false}),false);
 assert(body.includes('if (this._isMainFrame() && !skipDefaultOverrides)'));assert(body.includes('"Emulation.setFocusEmulationEnabled", { enabled: true }'));
});
test('bounded passive hidden diagnostics read real fixed scalars and consume late refusal',async()=>{
 let calls=0;const v={visible:true,hidden:false,focused:true,connected:true,tabletVisible:false};assert.deepEqual(await readActualScanVisibility({evaluate:async fn=>{calls++;assert(fn.toString().includes('document.visibilityState'));return v;}}),v);assert.equal(calls,1);
 assert.deepEqual(await readActualScanVisibility({evaluate:()=>Promise.reject(Error('Authored refusal'))}),{unavailable:true});let reject;const pending=new Promise((_,r)=>{reject=r;});assert.deepEqual(await readActualScanVisibility({evaluate:()=>pending}),{unavailable:true});reject(Error('Authored late refusal'));await new Promise(r=>setImmediate(r));
});
test('runner keeps all seventeen original control/popup functions and every original hidden five-second wait',async()=>{
 const s=await readFile(new URL('./tablet-graphics-scan-session.mjs',import.meta.url),'utf8'),old=await readFile(new URL('./fixtures/original-tablet-graphics.mjs',import.meta.url),'utf8');
 const segment=(s,a,b)=>s.split(a)[1].split(b)[0];for(const [a,b]of [['    async function paintedPopup','    async function openPopup'],['    async function openPopup','    async function preset'],['    async function preset','    async function control']])assert.equal(segment(s,a,b),segment(old,a,b));
 assert.equal(segment(s,"    await control('fieldOfView',20",'    report.resolutionProfileAcceptance=true;').replaceAll('await ownWorker();',''),segment(old,"    await control('fieldOfView',20",'    report.resolutionProfileAcceptance=true;'));
 for(const gate of ["await page.waitForFunction(()=>document.visibilityState==='visible',undefined,{timeout:5000})","await page.waitForFunction(()=>!window.__overte.tabletVisible,undefined,{timeout:5000})","await page.waitForFunction(()=>document.visibilityState==='hidden',undefined,{timeout:5000})"])assert(s.includes(gate));
 for(const phase of ['initialVisible','tabletHidden','documentHidden','cancelStatus'])assert(s.includes('report.hiddenPhase.'+phase));assert(s.includes('readActualScanVisibility(page)'));assert(s.includes('browserCleanupRefused=true'));assert(s.includes('ownedLeaderClosed,true'));assert(s.includes('sizeActualGraphicsPage(context,page,{width:1280,height:900})'));assert(!s.includes('page.setViewportSize('));
 assert(!s.includes('chromium.launch('));assert(!s.includes('setFocusEmulationEnabled'));assert(s.includes('if(systemFirefox){browser=await launchSystemFirefox'));assert(s.includes('requireActualGraphicsPage(context,page)'));
});

function sizingFixture({duplicates=false,foreign=false,wrongDensity=false,markChanged=false}={}){
 const f=fixture(),density=1.6666666269302368;let url='about:blank',metrics={width:800,height:600,density};const calls=[];
 const actual={url:()=>url,browser:()=>foreign?{}:f.owner,browserContext:()=>f.context,async setViewport(v){calls.push(v);metrics={width:v.width,height:v.height,density:wrongDensity?1.000000015894571:v.deviceScaleFactor};}};
 f.owner.defaultBrowserContext=()=>f.context;f.owner.pages=async()=>duplicates?[actual,actual]:[actual];const page={context:()=>f.context,url:()=>url,async goto(v){url=markChanged?'about:blank':v;},async evaluate(){return {...metrics};},get setViewportSize(){throw Error('No density-defaulting Playwright setter');}};return {f,page,calls,density};
}
test('public owned exact-tab API retains actually recorded Float32 native density, old Playwright-default control does not',async()=>{
 const c=sizingFixture(),r=await openActualGraphicsChromium(config,c.f.drivers);try{const old={width:1280,height:900,density:1.000000015894571};assert.notEqual(old.density,c.density);const proof=await sizeActualGraphicsPage(c.f.context,c.page,{width:1280,height:900});assert.deepEqual(c.calls,[{width:1280,height:900,deviceScaleFactor:c.density}]);assert.equal(proof.actual.density,c.density);assert.equal(proof.actual.width,1280);assert.equal(proof.actual.height,900);assert.equal(proof.method,'public-owned-Puppeteer-viewport');}finally{await r.browser.close();}
});
test('ambiguous/foreign/changed blank marker refuse before any viewport setter; wrong density refuses after actual readback',async()=>{
 for(const field of ['duplicates','foreign','markChanged','wrongDensity']){const c=sizingFixture({[field]:true}),r=await openActualGraphicsChromium(config,c.f.drivers);try{await assert.rejects(sizeActualGraphicsPage(c.f.context,c.page,{width:1280,height:900}));assert.equal(c.calls.length,field==='wrongDensity'?1:0);}finally{await r.browser.close();}}
 const c=sizingFixture(),r=await openActualGraphicsChromium(config,c.f.drivers);try{await assert.rejects(sizeActualGraphicsPage(c.f.context,c.page,{width:1280,height:800}),/reviewed/);assert.equal(c.calls.length,0);}finally{await r.browser.close();}
});
test('public Graphics viewport helper accesses no private targets/protocol, renderer or DOM density setters',async()=>{
 const s=await readFile(new URL('./tablet-graphics-real-focus.mjs',import.meta.url),'utf8');for(const part of ['owner.pages()','actual.browser()!==owner','actual.browserContext()!==owner.defaultBrowserContext()','deviceScaleFactor:initial.density','result.density!==initial.density','started+10000'])assert(s.includes(part));assert(!/newCDPSession|createCDPSession|_targetId|_client|setDeviceMetricsOverride|setFocusEmulationEnabled|Object.defineProperty|window.devicePixelRatio\s*=/.test(s));
});

test('owned browser retirement during viewport delivery cannot publish a stale setup proof',async()=>{
 const c=sizingFixture(),r=await openActualGraphicsChromium(config,c.f.drivers);const original=c.f.owner.pages;c.f.owner.pages=async()=>{const pages=await original();const actual=pages[0],set=actual.setViewport;actual.setViewport=async v=>{await set(v);await r.browser.close();};return pages;};await assert.rejects(sizeActualGraphicsPage(c.f.context,c.page,{width:1280,height:900}),/fresh noDefaults/);assert.equal(r.readOwnership().ownedLeaderClosed,true);assert.equal(c.calls.length,1);
});
