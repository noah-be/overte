// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {Loader,LoadingManager,Group,Mesh,Texture} from 'three';
import {BrowserWorld} from '../src/world';
import {FstGraphCache} from '../src/fst-graph-cache';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
import {ModelResources} from '../src/model-resources';
const methods=BrowserWorld.prototype as unknown as {loadModel(source:string,visited:Set<string>,base:undefined,signal:AbortSignal,publish:(model:Group)=>void):Promise<Group>};
const wait=async(predicate:()=>boolean)=>{for(let i=0;i<1000;i++){if(predicate())return;await new Promise(resolve=>setImmediate(resolve));}assert.fail('Expected actual loader stage was not reached');};
for(const kind of ['noTextures','unknown','fallthrough','unmatched','eligible'] as const)test(`actual World ${kind} preflight preserves the correct geometry/template order using one preparation`,async t=>{
 const context=Object.create(BrowserWorld.prototype),abort=new AbortController();let prepared=0,fetches=0,published:Group|undefined,textureWaiting=false,finish!:(value:Texture)=>void;const requests:string[]=[];
 const buffer=fstTextureAdmissionFbx({withoutOriginalTextures:kind==='noTextures',ambiguousID:kind==='unknown'?'negative':undefined,nativeEndRecords:true}),copy=buffer.slice(0);
 class Images extends Loader{load(url:string){requests.push(this.path+url);return new Texture({width:1,height:1});}}
 Object.assign(context,{abort,disposed:false,nativeCullDefaults:false,loadManagers:new Set(),preparedFbx:new PreparedFbxCache({signal:abort.signal}),imageCache:{loader:(manager:LoadingManager)=>new Images(manager)},
  fbxPreparePool:{prepare:async(buffer:ArrayBuffer)=>{prepared++;return{buffer,phases:{materialBindingsMs:0,decodeMs:0}};}},
  options:{resolveAsset:(url:string)=>url,onStatus(){},captureAssetAuthority:()=>({generation:'current',assertCurrent(){abort.signal.throwIfAborted();}})},
  sourceText:async(url:string)=>url.endsWith('.fst')?'filename = model.fbx\nmaterialMap = '+JSON.stringify([{[kind==='unmatched'?'mat::Missing':'all']:'replacement.json#Replacement'}]):JSON.stringify({materials:[{name:'Replacement',unlit:true,albedoMap:'replacement.png',...(kind==='fallthrough'?{defaultFallthrough:true}:{})}]}),
  texture:async()=>{textureWaiting=true;return new Promise<Texture>(resolve=>finish=resolve);},configureAlpha:async()=>{},recordLoadPhase(){},recordLoadDuration(){},
 });
 context.fstGraphCache=new FstGraphCache(abort.signal);
 t.mock.method(globalThis,'fetch',async()=>{fetches++;return new Response(buffer.slice(0));});
 const loading=methods.loadModel.call(context,'https://approved.example/model.fst',new Set(),undefined,abort.signal,model=>published=model);
 await wait(()=>textureWaiting);assert.equal(fetches,1);assert.equal(prepared,1);assert.deepEqual(new Uint8Array(buffer),new Uint8Array(copy));
 if(kind==='eligible'){assert.equal(published,undefined);assert.equal(requests.length,0);}
 else {assert(published,'Genuine parsed geometry must be published before required replacement images finish');let vertices=0;published.traverse(object=>{if(object instanceof Mesh)vertices+=object.geometry.attributes.position.count;});assert.equal(vertices,6);assert.equal(requests.length,kind==='noTextures'?0:3);}
 finish(new Texture({width:1,height:1}));const model=await loading;assert.equal(model,published);assert.equal(fetches,1);assert.equal(prepared,1);
 assert.equal(requests.length,kind==='eligible'||kind==='noTextures'?0:3);const resources=new ModelResources();resources.capture(model);resources.releaseKeeping();abort.abort();
});
