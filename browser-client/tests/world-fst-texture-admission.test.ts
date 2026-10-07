// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual BrowserWorld FST/material/FBX code and actual Three parser. Only network,
// image transport and worker execution are controlled CPU test boundaries.
import test from 'node:test';
import assert from 'node:assert/strict';
import {Loader,Texture,Mesh,Group,LoadingManager,MeshBasicMaterial} from 'three';
import {BrowserWorld} from '../src/world';
import {FstGraphCache} from '../src/fst-graph-cache';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {EmbeddedFbxImages} from '../src/embedded-fbx-images';
import {extractEmbeddedFbxImages} from '../src/baked-fbx';
import {ModelResources} from '../src/model-resources';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
const rootURL='https://approved.example/model.fst',modelURL='https://approved.example/model.fbx';
const methods=BrowserWorld.prototype as unknown as {loadModel(source:string,visited?:Set<string>,base?:string,signal?:AbortSignal):Promise<Group>};
function harness(options:{selector?:string;extra?:Record<string,unknown>;nested?:boolean;second?:boolean;embedded?:boolean;failTexture?:boolean;invalidate?:boolean;abortTemplate?:boolean}={}){
 const context=Object.create(BrowserWorld.prototype),abort=new AbortController(),events:string[]=[],textures:Texture[]=[];
 const original=fstTextureAdmissionFbx({embedded:options.embedded}),bytes=original.slice(0);let preparedBuffer=original,valid=true,disposedTextures=0;
 const rows=[{[options.selector??'all']:'replacement.json#Replacement'},...(options.second?[{'mat::Replacement':'second.json#Final'}]:[])];
 class OriginalImages extends Loader{load(url:string){const resolved=this.manager.resolveURL(/^(?:data:|blob:)/.test(url)?url:this.path+url);events.push('original:'+resolved);return new Texture({width:1,height:1,src:resolved});}}
 const preparedFbx=new PreparedFbxCache({signal:abort.signal});
 Object.assign(context,{abort,disposed:false,nativeCullDefaults:false,loadManagers:new Set(),preparedFbx,
  embeddedFbxCounts:{preparations:0,convertedImages:0,extractedBytes:0,skippedOversize:0,skippedUnsupported:0},embeddedFbxImages:new EmbeddedFbxImages(abort.signal),
  imageCache:{loader:(manager:LoadingManager)=>new OriginalImages(manager)},
  fbxPreparePool:{prepare:async(input:ArrayBuffer)=>{const result=options.embedded?await extractEmbeddedFbxImages(input):{buffer:input,images:[]};preparedBuffer=result.buffer;return{buffer:result.buffer,embeddedImages:result.images,embeddedCounts:'counts' in result?result.counts:{converted:0,rawBytes:0,skippedOversize:0,skippedUnsupported:0},phases:{materialBindingsMs:0,decodeMs:0}};}},
  options:{resolveAsset:(url:string)=>url,onStatus(){},captureAssetAuthority:()=>({generation:'connected-approval',assertCurrent(){if(!valid)throw Error('Visitor authority changed');}})},
  sourceText:async(url:string)=>{events.push('text:'+url);if(url===rootURL)return 'filename = '+(options.nested?'nested.fst':'model.fbx')+'\nmaterialMap = '+JSON.stringify(rows);if(url.endsWith('nested.fst'))return 'filename = model.fbx';return JSON.stringify({materials:[{name:url.includes('second')?'Final':'Replacement',model:'hifi_pbr',unlit:true,albedoMap:'replacement.png',...options.extra}]});},
  texture:async(url:string,_color:boolean,_role:unknown,signal:AbortSignal)=>{events.push('replacement:'+url);signal.throwIfAborted();if(options.failTexture)throw Error('Approved replacement image failed');const texture=new Texture({width:1,height:1,src:url});texture.addEventListener('dispose',()=>disposedTextures++);textures.push(texture);return texture;},
  configureAlpha:async(material:MeshBasicMaterial,_options:unknown,signal:AbortSignal)=>{signal.throwIfAborted();if(material.name==='Replacement'){if(options.invalidate)valid=false;if(options.abortTemplate)abort.abort();}},
  recordLoadPhase(){},recordLoadDuration(){},
 });
 context.fstGraphCache=new FstGraphCache(abort.signal);
 return{context,abort,events,original,bytes,textures,preparedBuffer:()=>preparedBuffer,disposedTextures:()=>disposedTextures,invalidate:()=>valid=false};
}
function mesh(model:Group){let result!:Mesh;model.traverse(object=>{if(object instanceof Mesh)result=object;});assert(result);return result;}
function release(model:Group){const resources=new ModelResources();resources.capture(model);resources.releaseKeeping();}
for(const selector of ['all','mat::A'])test(`actual World ${selector} preloads successful templates before admitting only necessary original FBX images`,async t=>{
 const h=harness({selector});t.mock.method(globalThis,'fetch',async(input:unknown)=>{assert.equal(String(input),modelURL);h.events.push('fbx');return new Response(h.original.slice(0));});
 const result=await methods.loadModel.call(h.context,rootURL),loaded=mesh(result),materials=loaded.material as MeshBasicMaterial[];
 assert.equal(materials[0].name,'Replacement');assert.equal(materials[0].map,h.textures[0]);
 const originals=h.events.filter(event=>event.startsWith('original:'));
 assert.deepEqual(originals,selector==='all'?[]:['original:https://approved.example/shared.png','original:https://approved.example/only-b.png']);
 const replacementAt=h.events.indexOf('replacement:https://approved.example/replacement.png');assert(h.events.indexOf('fbx')<replacementAt,'Immutable-byte preflight precedes template images');
 if(originals.length)assert(replacementAt<h.events.findIndex(event=>event.startsWith('original:')),'Omitted-image proof precedes surviving original image admission');
 assert.equal(loaded.geometry.attributes.position.count,6);assert.deepEqual(loaded.geometry.groups,[{start:0,count:3,materialIndex:0},{start:3,count:3,materialIndex:1}]);
 assert.deepEqual(new Uint8Array(h.original),new Uint8Array(h.bytes));assert.equal(h.disposedTextures(),0);release(result);assert.equal(h.disposedTextures(),1);h.abort.abort();
});
test('actual World source ordering applies renamed selectors and disposes superseded template images once',async t=>{
 const h=harness({selector:'mat::A',second:true});t.mock.method(globalThis,'fetch',async()=>new Response(h.original.slice(0)));
 const model=await methods.loadModel.call(h.context,rootURL),materials=mesh(model).material as MeshBasicMaterial[];
 assert.deepEqual(materials.map(material=>material.name),['Final','B']);assert.equal(materials[0].map,h.textures[1]);assert.equal(h.disposedTextures(),1);release(model);assert.equal(h.disposedTextures(),2);h.abort.abort();
});
for(const mode of ['nested','fallthrough','unmatched'] as const)test(`actual World uncertain ${mode} keeps ordinary original image admission`,async t=>{
 const h=harness({nested:mode==='nested',extra:mode==='fallthrough'?{defaultFallthrough:true}:undefined,selector:mode==='unmatched'?'mat::NotPresent':'all'});
 t.mock.method(globalThis,'fetch',async()=>{h.events.push('fbx');return new Response(h.original.slice(0));});const model=await methods.loadModel.call(h.context,rootURL);
 assert.equal(h.events.filter(event=>event.startsWith('original:')).length,3);
 if(mode==='nested')assert(h.events.indexOf('fbx')<h.events.indexOf('replacement:https://approved.example/replacement.png'));
 if(mode==='unmatched'){assert.deepEqual((mesh(model).material as MeshBasicMaterial[]).map(material=>material.name),['A','B']);assert.equal(h.disposedTextures(),1);}
 release(model);h.abort.abort();
});
for(const mode of ['failTexture','invalidate','abortTemplate'] as const)test(`actual World ${mode} before original-image admission releases successful template resources`,async t=>{
 const h=harness({[mode]:true});let fetches=0;t.mock.method(globalThis,'fetch',async()=>{fetches++;return new Response(h.original.slice(0));});
 await assert.rejects(methods.loadModel.call(h.context,rootURL),mode==='abortTemplate'?{name:'AbortError'}:/failed|authority changed/);
 assert.equal(fetches,1);assert.equal(h.events.filter(event=>event.startsWith('original:')).length,0);assert.equal(h.disposedTextures(),h.textures.length);h.abort.abort();
});
test('actual World registers filtered embedded images with original cached buffer identity across differently mapped consumers',async t=>{
 const h=harness({selector:'mat::A',embedded:true});t.mock.method(globalThis,'fetch',async()=>new Response(h.original.slice(0)));
 const registry=h.context.embeddedFbxImages,register=registry.register.bind(registry),owners:ArrayBuffer[]=[],counts:number[]=[];
 t.mock.method(registry,'register',(buffer:ArrayBuffer,images:unknown[],signal:AbortSignal)=>{owners.push(buffer);counts.push(images.length);return register(buffer,images,signal);});
 const a=await methods.loadModel.call(h.context,rootURL),b=await methods.loadModel.call(h.context,modelURL);
 assert.equal(owners.length,2);assert.equal(owners[0],h.preparedBuffer());assert.equal(owners[1],owners[0]);assert.deepEqual(counts,[2,3]);
 assert.equal(registry.statistics.createdURLs,3);assert(registry.statistics.reusedURLs>=2);release(a);release(b);h.abort.abort();assert.equal(registry.statistics.entries,0);
});
