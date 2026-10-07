// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Public-driver ownership/wiring contracts; no browser/process is launched.
import test from 'node:test';import assert from 'node:assert/strict';import {EventEmitter}from'node:events';
import {readFile}from'node:fs/promises';
import {useActualPttPageFocus,openActualPttChromium} from './tablet-ptt-real-focus.mjs';
const configuration={executablePath:'/reviewed/owned-chromium',microphone:'/reviewed/synthetic.wav',env:{DISPLAY:':95',PULSE_SERVER:'owned-fixture-only'}};
function fixture({endpoint='ws://127.0.0.1:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef',count=1,connectFailure,grantFailure,ownerCloseFailure,controllerCloseFailure,noProcess=false}={}){
 const calls=[],leader=new EventEmitter();Object.assign(leader,{pid:123,exitCode:null,signalCode:null});
 const context={async grantPermissions(value){calls.push(['grant',value]);if(grantFailure)throw grantFailure;},get newCDPSession(){throw Error('No original/new agent access admitted');}};
 const owner={process:()=>noProcess?null:leader,wsEndpoint:()=>endpoint,async close(){calls.push('owner-close');leader.exitCode=0;leader.emit('close',0,null);if(ownerCloseFailure)throw ownerCloseFailure;}};
 const controller={contexts:()=>Array(count).fill(context),version:()=> 'authored-no-browser',get newContext(){throw Error('No new emulated context admitted');},async close(){calls.push('controller-close');if(controllerCloseFailure)throw controllerCloseFailure;}};
 const drivers={async launch(options){calls.push(['launch',options]);return owner;},async connect(value,options){calls.push(['connect',value,options]);if(connectFailure)throw connectFailure;return controller;}};
 return {calls,leader,context,owner,controller,drivers};
}
test('Fresh public launch uses only noDefaults default context and no focus command',async()=>{
 const f=fixture(),result=await openActualPttChromium(configuration,f.drivers);const launch=f.calls[0][1];assert.equal(launch.browser,'chrome');assert.equal(launch.protocol,'cdp');assert.equal(launch.headless,false);assert.equal(launch.defaultViewport,null);assert.equal(launch.pipe,false);assert.equal(launch.timeout,30000);assert.equal(launch.protocolTimeout,30000);assert(!('userDataDir'in launch));assert.equal(launch.executablePath,configuration.executablePath);assert.equal(launch.env,configuration.env);
 assert.deepEqual(launch.ignoreDefaultArgs,['--mute-audio']);assert.deepEqual(launch.args,['--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+configuration.microphone]);assert.deepEqual(f.calls[1],['connect',f.owner.wsEndpoint(),{noDefaults:true,isLocal:true,timeout:30000}]);assert.deepEqual(f.calls[2],['grant',['microphone']]);assert.equal(result.context,f.context);assert.equal(result.browser.newContext,undefined);
 const page={context:()=>f.context};assert.deepEqual(await useActualPttPageFocus(f.context,page,'system-chromium'),{engine:'system-chromium',focusEmulationDisabled:false,focusOverridesSkipped:true,scope:'actual-Chromium-default-context-no-overrides'});assert.deepEqual(result.readOwnership(),{defaultContextOnly:true,focusOverridesSkipped:true,ownedLeaderClosed:false});assert.equal(result.browser.version(),'authored-no-browser');
 await result.browser.close();assert.deepEqual(f.calls.slice(-2),['owner-close','controller-close']);assert.equal(result.readOwnership().ownedLeaderClosed,true);assert.equal(f.leader.listenerCount('close'),0);assert.equal(f.leader.listenerCount('error'),0);await assert.rejects(useActualPttPageFocus(f.context,page,'system-chromium'),/fresh noDefaults/);await result.browser.close();assert.equal(f.calls.filter(c=>c==='owner-close').length,1);
});
test('Unregistered context and wrong-page ownership refuse without protocol/getter access',async()=>{
 const foreign={get newCDPSession(){throw Error('No protocol access');}};await assert.rejects(useActualPttPageFocus(foreign,{},'system-chromium'),/fresh noDefaults/);const f=fixture(),r=await openActualPttChromium(configuration,f.drivers);try{await assert.rejects(useActualPttPageFocus(f.context,{context:()=>foreign},'system-chromium'),/fresh noDefaults/);}finally{await r.browser.close();}
});
test('Firefox unchanged genuine BiDi path never accesses CDP or page identity',async()=>{const context={get newCDPSession(){throw Error('No CDP permitted');}},page={get context(){throw Error('No Chromium page check permitted');}};assert.deepEqual(await useActualPttPageFocus(context,page,'system-firefox'),{engine:'system-firefox',focusEmulationDisabled:false,scope:'actual-BiDi-page-focus'});});
test('Unsupported engine refuses before protocol access',async()=>{await assert.rejects(useActualPttPageFocus({get newCDPSession(){throw Error('No protocol permitted');}},{},'foreign'),/Unsupported owned PTT focus engine/);});
for(const endpoint of ['ws://remote.invalid:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef','ws://secret@127.0.0.1:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef','ws://127.0.0.1:49220/devtools/browser/01234567-89ab-cdef-0123-456789abcdef?private=value'])test('Nonowned CDP endpoint refuses before connecting and closes owned launch',async()=>{const f=fixture({endpoint});await assert.rejects(openActualPttChromium(configuration,f.drivers),/loopback/);assert.equal(f.calls.filter(c=>Array.isArray(c)&&c[0]==='connect').length,0);assert.equal(f.calls.at(-1),'owner-close');});
for(const count of [0,2])test('No new/ambiguous browser context is admitted',async()=>{const f=fixture({count});await assert.rejects(openActualPttChromium(configuration,f.drivers),/Exactly one/);assert.deepEqual(f.calls.slice(-2),['owner-close','controller-close']);});
test('Connect and permission errors retain original failure and close all created owners',async()=>{for(const kind of ['connectFailure','grantFailure']){const failure=Error('Controlled original refusal'),f=fixture({[kind]:failure});await assert.rejects(openActualPttChromium(configuration,f.drivers),error=>error===failure);assert(f.calls.includes('owner-close'));assert.equal(f.calls.includes('controller-close'),kind==='grantFailure');}});
test('Actual launch owner cleanup failure still attempts CDP close and never reports success',async()=>{const failure=Error('Controlled owner cleanup refusal'),f=fixture({ownerCloseFailure:failure}),r=await openActualPttChromium(configuration,f.drivers);await assert.rejects(r.browser.close(),error=>error instanceof AggregateError&&error.errors.includes(failure));assert.deepEqual(f.calls.slice(-2),['owner-close','controller-close']);assert.equal(r.readOwnership().ownedLeaderClosed,true);});
test('CDP cleanup failure remains failure despite actual leader-close evidence',async()=>{const failure=Error('Controlled transport cleanup refusal'),f=fixture({controllerCloseFailure:failure}),r=await openActualPttChromium(configuration,f.drivers);await assert.rejects(r.browser.close(),error=>error instanceof AggregateError&&error.errors.includes(failure));assert.equal(r.readOwnership().ownedLeaderClosed,true);});
test('Missing launched-process ownership refuses and still calls public owner close',async()=>{const f=fixture({noProcess:true});await assert.rejects(openActualPttChromium(configuration,f.drivers),/browser process required/);assert.equal(f.calls.at(-1),'owner-close');});
test('Invalid launch inputs refuse before public launcher',async()=>{const f=fixture();for(const config of [{...configuration,executablePath:'relative'},{...configuration,microphone:'relative'},{...configuration,env:{DISPLAY:'remote:95'}}])await assert.rejects(openActualPttChromium(config,f.drivers),/Invalid owned/);assert.deepEqual(f.calls,[]);});
test('Runner original genuine input, visibility, native state, audio and cleanup gates are preserved',async()=>{const s=await readFile(new URL('./tablet-push-to-talk.mjs',import.meta.url),'utf8');for(const exact of ["const visibilityOutcome=page.waitForFunction(({blur,hidden})=>document.hidden&&window.__pttAudit.events.blur>blur&&window.__pttAudit.events.hidden>hidden,beforeEvents,{timeout:10000,polling:100})","e.code==='KeyT'&&e.isTrusted","Native released ACK cannot permit further browser PCM","Browser actual output must contain the native peer 997Hz synthetic input","Released PTT must silence synthetic input at real native output","Exact owned native profiles removed"])assert(s.includes(exact));assert(s.includes('if(firefox)context=await browser.newContext'));assert(s.includes('page.setViewportSize({width:1280,height:800})'));assert(!s.includes('chromium.launch('));});

test('Launch leader error is consumed but never promoted to verified successful close',async()=>{const f=fixture(),r=await openActualPttChromium(configuration,f.drivers);f.leader.emit('error',Error('Controlled owned leader error'));await assert.rejects(r.browser.close(),/cleanup refused/);assert.equal(r.readOwnership().ownedLeaderClosed,false);assert.equal(f.leader.listenerCount('close'),0);});

// Invoke the exact installed launch-argument builder without launching Chromium.
// Temporary profiles are owned by this CPU test and always removed.
async function actualArguments(args){
 const {mkdtemp,rm}=await import('node:fs/promises'),{tmpdir}=await import('node:os'),path=await import('node:path');
 const {ChromeLauncher}=await import(new URL('./node/ChromeLauncher.js',import.meta.resolve('puppeteer-core')));
 const directory=await mkdtemp(path.join(tmpdir(),'overte-ptt-launch-args-'));
 try{
  const launcher=new ChromeLauncher({_isPuppeteerCore:true},()=>{});
  launcher.getProfilePath=async()=>path.join(directory,'profile-');
  const result=await launcher.computeLaunchArguments({executablePath:configuration.executablePath,headless:false,pipe:false,ignoreDefaultArgs:['--mute-audio'],args:[...args]});
  assert(result.isTempUserDataDir);assert(result.userDataDir.startsWith(directory+path.sep));
  assert.equal(result.args.filter(a=>a.startsWith('--user-data-dir=')).length,1);
  return result.args.filter(a=>!a.startsWith('--user-data-dir='));
 }finally{await rm(directory,{recursive:true,force:true});}
}
test('actual installed Puppeteer old address-only control suppresses its automatic debugging port',async()=>{
 const result=await actualArguments(['--remote-debugging-address=127.0.0.1']);
 assert(result.includes('--remote-debugging-address=127.0.0.1'));
 assert(!result.some(a=>a.startsWith('--remote-debugging-port=')||a==='--remote-debugging-pipe'));
 assert(result.includes('about:blank'));assert(!result.includes('--no-sandbox'));
});
test('actual public helper supplies explicit ephemeral port to installed Puppeteer while keeping ownership/default-context/focus guards',async()=>{
 const f=fixture(),owned=await openActualPttChromium(configuration,f.drivers);
 try{
  const launch=f.calls[0][1],result=await actualArguments(launch.args);
  assert.equal(result.filter(a=>a.startsWith('--remote-debugging-port=')).length,1);
  assert(result.includes('--remote-debugging-port=0'));assert(result.includes('--remote-debugging-address=127.0.0.1'));
  assert(!result.includes('--remote-debugging-pipe'));assert(!result.includes('--no-sandbox'));
  assert.equal(launch.timeout,30000);assert.equal(launch.protocolTimeout,30000);
  assert(!('userDataDir' in launch));assert.equal(launch.defaultViewport,null);
  assert.deepEqual(f.calls[1][2],{noDefaults:true,isLocal:true,timeout:30000});
 }finally{await owned.browser.close();}
 assert.equal(owned.readOwnership().ownedLeaderClosed,true);
});
