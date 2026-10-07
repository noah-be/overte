// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';import {createHash} from 'node:crypto';import vm from 'node:vm';import {transformSync} from 'esbuild';
export const AUTHORED_FIXTURE_SOURCE='tests/fixtures/tablet-fullscreen-original-20261002.ts.txt';
export const SOURCE_PINS=Object.freeze({
 'src/tablet.ts':'d0624d76d2bffa2f60dfeaaefd0e53e6f5a5798f635183ba04c75a983e32e7a6',
 'src/fullscreen.ts':'a311c55214699670c6cacd7bdbba0fec024d0ef50e69f90f2c28db6e3357715e',
 'tests/tablet-fullscreen.browser.spec.ts':'ddaf2bc6ff709c302476b8f63581176684d738b71d076783c94edfcaa77915c2',
 [AUTHORED_FIXTURE_SOURCE]:'53ae639c6ec16a6f57aba3ee60bf997e87589a20ec6ce50735fd3bccfb393c37',
 'tests/integration/system-firefox.mjs':'375416100da67828ba3b91962fff5e8d72d41b64144562eb0e234a48eea639c5',
 'tests/integration/replacement-material-clones-diagnostics.mjs':'6c45bfc48160758f35b312023c9819266de57be00be05f641a72f5923c2010c9',
});
export const sha=b=>createHash('sha256').update(b).digest('hex');
export function fixtureCallbacks(source){
 assert.equal(sha(source),SOURCE_PINS[AUTHORED_FIXTURE_SOURCE],'Exact historical authored source required');
 const between=(start,end)=>{assert.equal(source.split(start).length,2);const rest=source.split(start)[1];assert.equal(rest.split(end).length,2);return rest.split(end)[0];};
 const install=between("async function install(page:Page,path='/'){\n    await page.goto(path);\n    await page.evaluate(async()=>{",'\n    });\n    await expect.poll');
 const proof=between('async function proof(page:Page){return page.evaluate(()=>{','\n});}');
 const replacementPrefix="    await page.evaluate(async()=>{\n        const path='/src/tablet.ts';const {BrowserTablet}=await import(path),p=";
 const replacement=between(replacementPrefix,"\n    });\n    expect((await proof(page)).owner).toBe(true);");
 const build=text=>new vm.Script(transformSync('('+text+')',{loader:'ts',target:'es2022'}).code).runInNewContext();
 return {install:build('async()=>{'+install+'\n}'),proof:build('()=>{'+proof+'\n}'),replacement:build("async()=>{\n        const path='/src/tablet.ts';const {BrowserTablet}=await import(path),p="+replacement+'\n}')};
}
export function embeddingOrigins(value){
 const parent=new URL(value);assert.equal(parent.protocol,'http:');assert.equal(parent.hostname,'127.0.0.1');assert(!parent.username&&!parent.password&&!parent.search&&!parent.hash);assert.equal(parent.pathname,'/');assert(Number.isInteger(Number(parent.port))&&Number(parent.port)>=1024&&Number(parent.port)<=65535);
 const child=new URL(parent.origin);child.hostname='localhost';assert.notEqual(parent.origin,child.origin);assert.equal(parent.port,child.port);return {parent:parent.origin,child:child.origin};
}
export function embeddingDocument(origins,delegated){
 assert.deepEqual(embeddingOrigins(origins.parent),origins);assert.equal(typeof delegated,'boolean');const child=origins.child+'/fullscreen-owned-child.html';return {status:200,contentType:'text/html',body:'<!doctype html><html><body style="margin:0"><iframe id="owned-fullscreen-frame" src="'+child+'" '+(delegated?'allowfullscreen ':'')+'style="position:fixed;inset:0;width:100%;height:100%;border:0"></iframe></body></html>'};
}
export function qualifyEmbedding(p,delegated){
 assert.equal(p.crossOrigin,true);assert.equal(p.visible,true);assert.equal(p.connected,true);assert.equal(p.delegated,delegated);assert.equal(p.extraAllow,false);assert.equal(p.fullscreenEnabled,delegated);assert.equal(p.none,true);assert.equal(p.parentNone,true);assert.equal(p.buttonDisabled,!delegated);assert.equal(p.warning,!delegated);assert.deepEqual(p.pixel,[40,80,100,255]);assert(Math.abs(p.ratio-480/706)<.0005);
}
export function qualifyDeniedProbe(p){assert.deepEqual(p,{trusted:true,calls:1,visible:true,connected:true,enabled:false,rejected:true,name:'TypeError',none:true});}
export function qualifyCanvasWire(p,bounds,events){
 const press=p.inputs.find(v=>v.event==='press'),release=p.inputs.find(v=>v.event==='release');assert(press&&release);assert.equal(events.length,2);assert.deepEqual(events.map(v=>({type:v.type,trusted:v.trusted,button:v.button})),[{type:'pointerdown',trusted:true,button:0},{type:'pointerup',trusted:true,button:0}]);
 for(const v of [press,release]){assert.equal(v.revision,1);assert.equal(v.frameSequence,1);assert.equal(v.button,0);assert(Math.abs(Number(v.x)-.5)*bounds.width<=1);assert(Math.abs(Number(v.y)-.5)*bounds.height<=1);}assert.equal(p.none,true);
}
export async function embeddingCaseDeadline(work){let timer;const pending=Promise.resolve().then(work);void pending.catch(()=>{});try{return await Promise.race([pending,new Promise((_,reject)=>{timer=setTimeout(()=>{const e=Error('Original fullscreen case deadline');e.name='TimeoutError';reject(e);},45000);})]);}finally{clearTimeout(timer);}}
