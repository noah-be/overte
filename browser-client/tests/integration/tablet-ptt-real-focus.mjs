// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// noDefaults affects only an existing default context, not browser.newContext().
// Never synthesize focus/visibility, override document state, or access agents.
import puppeteer from 'puppeteer-core';
import {chromium} from '@playwright/test';
import path from 'node:path';
const actualContexts=new WeakSet();
export async function openActualPttChromium({executablePath,env,microphone},drivers={launch:options=>puppeteer.launch(options),connect:(endpoint,options)=>chromium.connectOverCDP(endpoint,options)}){
 if(typeof executablePath!=='string'||!path.isAbsolute(executablePath)||typeof microphone!=='string'||!path.isAbsolute(microphone)||typeof env?.DISPLAY!=='string'||!/^:[0-9]{1,3}$/.test(env.DISPLAY))throw Error('Invalid owned PTT Chromium launch');
 let owner,controller,context,leader,leaderDone,closing;
 const state={defaultContextOnly:true,focusOverridesSkipped:true,ownedLeaderClosed:false};
 const close=()=>closing??=(async()=>{
  if(context)actualContexts.delete(context);
  const deadline=Date.now()+10000,errors=[];
  const bounded=async operation=>{
   const pending=Promise.resolve().then(operation);void pending.catch(()=>{});let timer;
   try{return await Promise.race([pending,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Owned PTT browser cleanup deadline')),Math.max(0,deadline-Date.now()));})]);}finally{clearTimeout(timer);}
  };
  // The launch owner's public close owns the actual process and temporary profile.
  // A connectOverCDP browser.close alone may close only the transport.
  try{if(owner)await bounded(()=>owner.close());}catch(error){errors.push(error);}
  finally{try{if(controller)await bounded(()=>controller.close());}catch(error){errors.push(error);}}
  if(leaderDone){try{state.ownedLeaderClosed=await bounded(()=>leaderDone);if(!state.ownedLeaderClosed)errors.push(Error('Owned PTT browser leader exit not observed'));}catch(error){errors.push(error);}}
  if(errors.length)throw new AggregateError(errors,'Owned PTT Chromium cleanup refused');
 })();
 try{
  // Puppeteer treats the address switch as an existing debugging transport.
  // Explicit port0 is required; retain its owned temporary profile and loopback.
  owner=await drivers.launch({browser:'chrome',protocol:'cdp',executablePath,headless:false,defaultViewport:null,pipe:false,env,
   timeout:30000,protocolTimeout:30000,ignoreDefaultArgs:['--mute-audio'],args:['--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+microphone]});
  leader=owner.process();if(!leader||!Number.isSafeInteger(leader.pid)||leader.pid<1||typeof leader.once!=='function'||typeof leader.removeListener!=='function')throw Error('Owned PTT browser process required');
  leaderDone=new Promise(resolve=>{let finished=false;const finish=value=>{if(finished)return;finished=true;leader.removeListener('close',onClose);leader.removeListener('error',onError);resolve(value);};const onClose=()=>finish(true),onError=()=>finish(false);leader.once('close',onClose);leader.once('error',onError);if(leader.exitCode!==null||leader.signalCode!==null)finish(true);});
  const endpoint=owner.wsEndpoint(),url=new URL(endpoint);if(url.protocol!=='ws:'||url.hostname!=='127.0.0.1'||!/^\d+$/.test(url.port)||Number(url.port)<1||Number(url.port)>65535||url.username||url.password||url.search||url.hash||!/^\/devtools\/browser\/[a-f0-9-]{36}$/.test(url.pathname))throw Error('Owned loopback PTT browser endpoint required');
  controller=await drivers.connect(endpoint,{noDefaults:true,isLocal:true,timeout:30000});const contexts=controller.contexts();if(contexts.length!==1)throw Error('Exactly one fresh owned default browser context required');context=contexts[0];
  // No new context: that would re-enable Playwright main-frame focus emulation.
  actualContexts.add(context);await context.grantPermissions(['microphone']);
  const browser=Object.freeze({version:()=>controller.version(),close});
  return Object.freeze({browser,context,readOwnership:()=>Object.freeze({...state})});
 }catch(error){try{await close();}catch(cleanup){throw new AggregateError([error,cleanup],'Owned PTT Chromium setup and cleanup refused');}throw error;}
}
export async function useActualPttPageFocus(context,page,engine){
 if(!['system-chromium','system-firefox'].includes(engine))throw Error('Unsupported owned PTT focus engine');
 if(engine==='system-firefox')return {engine,focusEmulationDisabled:false,scope:'actual-BiDi-page-focus'};
 if(!actualContexts.has(context)||page.context()!==context)throw Error('Page must belong to the fresh noDefaults owned default context');
 return {engine,focusEmulationDisabled:false,focusOverridesSkipped:true,scope:'actual-Chromium-default-context-no-overrides'};
}
