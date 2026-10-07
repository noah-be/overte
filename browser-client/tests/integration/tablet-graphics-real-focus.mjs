// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// noDefaults affects only an existing default context, not browser.newContext().
// Never synthesize focus/visibility, override document state, or access agents.
import puppeteer from 'puppeteer-core';
import {chromium} from '@playwright/test';
import path from 'node:path';import {randomUUID} from 'node:crypto';
const actualContexts=new WeakSet();const ownedBrowsers=new WeakMap();
export async function openActualGraphicsChromium({executablePath,env},drivers={launch:options=>puppeteer.launch(options),connect:(endpoint,options)=>chromium.connectOverCDP(endpoint,options)}){
 if(typeof executablePath!=='string'||!path.isAbsolute(executablePath)||typeof env?.DISPLAY!=='string'||!/^:[0-9]{1,3}$/.test(env.DISPLAY))throw Error('Invalid owned Graphics Chromium launch');
 let owner,controller,context,leader,leaderDone,closing;
 const state={defaultContextOnly:true,focusOverridesSkipped:true,ownedLeaderClosed:false};
 const close=()=>closing??=(async()=>{
  if(context){actualContexts.delete(context);ownedBrowsers.delete(context);}
  const deadline=Date.now()+10000,errors=[];
  const bounded=async operation=>{
   const pending=Promise.resolve().then(operation);void pending.catch(()=>{});let timer;
   try{return await Promise.race([pending,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Owned Graphics browser cleanup deadline')),Math.max(0,deadline-Date.now()));})]);}finally{clearTimeout(timer);}
  };
  // The launch owner's public close owns the actual process and temporary profile.
  // A connectOverCDP browser.close alone may close only the transport.
  try{if(owner)await bounded(()=>owner.close());}catch(error){errors.push(error);}
  finally{try{if(controller)await bounded(()=>controller.close());}catch(error){errors.push(error);}}
  if(leaderDone){try{state.ownedLeaderClosed=await bounded(()=>leaderDone);if(!state.ownedLeaderClosed)errors.push(Error('Owned Graphics browser leader exit not observed'));}catch(error){errors.push(error);}}
  if(errors.length)throw new AggregateError(errors,'Owned Graphics Chromium cleanup refused');
 })();
 try{
  // Puppeteer treats the address switch as an existing debugging transport.
  // Explicit port0 is required; retain its owned temporary profile and loopback.
  owner=await drivers.launch({browser:'chrome',protocol:'cdp',executablePath,headless:false,defaultViewport:null,pipe:false,env,
   timeout:30000,protocolTimeout:30000,args:['--remote-debugging-address=127.0.0.1','--remote-debugging-port=0']});
  leader=owner.process();if(!leader||!Number.isSafeInteger(leader.pid)||leader.pid<1||typeof leader.once!=='function'||typeof leader.removeListener!=='function')throw Error('Owned Graphics browser process required');
  leaderDone=new Promise(resolve=>{let finished=false;const finish=value=>{if(finished)return;finished=true;leader.removeListener('close',onClose);leader.removeListener('error',onError);resolve(value);};const onClose=()=>finish(true),onError=()=>finish(false);leader.once('close',onClose);leader.once('error',onError);if(leader.exitCode!==null||leader.signalCode!==null)finish(true);});
  const endpoint=owner.wsEndpoint(),url=new URL(endpoint);if(url.protocol!=='ws:'||url.hostname!=='127.0.0.1'||!/^\d+$/.test(url.port)||Number(url.port)<1||Number(url.port)>65535||url.username||url.password||url.search||url.hash||!/^\/devtools\/browser\/[a-f0-9-]{36}$/.test(url.pathname))throw Error('Owned loopback Graphics browser endpoint required');
  controller=await drivers.connect(endpoint,{noDefaults:true,isLocal:true,timeout:30000});const contexts=controller.contexts();if(contexts.length!==1)throw Error('Exactly one fresh owned default browser context required');context=contexts[0];
  // No new context: that would re-enable Playwright main-frame focus emulation.
  actualContexts.add(context);ownedBrowsers.set(context,owner);
  const browser=Object.freeze({version:()=>controller.version(),close});
  return Object.freeze({browser,context,readOwnership:()=>Object.freeze({...state})});
 }catch(error){try{await close();}catch(cleanup){throw new AggregateError([error,cleanup],'Owned Graphics Chromium setup and cleanup refused');}throw error;}
}
export function requireActualGraphicsPage(context,page){
 if(!actualContexts.has(context)||page.context()!==context)throw Error('Page must belong to the fresh noDefaults owned Graphics default context');
 return {scope:'actual-Chromium-default-context-no-overrides',focusOverridesSkipped:true};
}
/** Fixed scalar failure-only diagnostics; does not mutate visibility or focus. */
export async function readActualScanVisibility(page){
 let timer;const operation=Promise.resolve().then(()=>page.evaluate(()=>({visible:document.visibilityState==='visible',hidden:document.hidden,focused:document.hasFocus(),connected:window.__overte?.connected===true,tabletVisible:window.__overte?.tabletVisible===true})));void operation.catch(()=>{});
 try{return await Promise.race([operation,new Promise(resolve=>{timer=setTimeout(()=>resolve({unavailable:true}),250);})]);}
 catch{return {unavailable:true};}finally{clearTimeout(timer);}
}
/** Public exact-tab viewport API, retaining independently measured native DPR. */
export async function sizeActualGraphicsPage(context,page,viewport){
 requireActualGraphicsPage(context,page);if(viewport?.width!==1280||viewport?.height!==900)throw Error('Only the reviewed Graphics viewport is admitted');
 const owner=ownedBrowsers.get(context);if(!owner)throw Error('Missing owned Graphics launch browser');const started=Date.now(),deadline=started+10000;const current=()=>{requireActualGraphicsPage(context,page);if(ownedBrowsers.get(context)!==owner)throw Error('Owned Graphics viewport owner changed');};
 const bounded=async operation=>{const remaining=deadline-Date.now();if(remaining<=0)throw Error('Owned Graphics viewport deadline');let timer;const pending=Promise.resolve().then(()=>{if(Date.now()>=deadline)throw Error('Owned Graphics viewport deadline');current();return operation();});void pending.catch(()=>{});try{const value=await Promise.race([pending,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Owned Graphics viewport deadline')),remaining);})]);current();return value;}finally{clearTimeout(timer);}};
 const read=()=>bounded(()=>page.evaluate(()=>({width:innerWidth,height:innerHeight,density:devicePixelRatio})));const initial=await read();if(!Number.isFinite(initial.density)||initial.density<=0||initial.density>8)throw Error('Invalid native Graphics density');
 const marker='about:blank#overte-graphics-owned-'+randomUUID();await bounded(()=>page.goto(marker));if(page.url()!==marker)throw Error('Owned Graphics tab marker changed');
 const pages=await bounded(()=>owner.pages()),matches=pages.filter(value=>value.url()===marker);if(matches.length!==1)throw Error('Exactly one public owned Graphics tab required');const actual=matches[0];if(actual.browser()!==owner||actual.browserContext()!==owner.defaultBrowserContext())throw Error('Graphics public tab does not belong to the owned default context');
 await bounded(()=>actual.setViewport({width:1280,height:900,deviceScaleFactor:initial.density}));const result=await read();if(page.url()!==marker||actual.url()!==marker||result.width!==1280||result.height!==900||result.density!==initial.density)throw Error('Owned Graphics viewport or native density changed');
 return {method:'public-owned-Puppeteer-viewport',requested:{width:1280,height:900},initial,actual:result,durationMs:Date.now()-started};
}
