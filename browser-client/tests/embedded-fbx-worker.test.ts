// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';import {Worker} from 'node:worker_threads';import {readdir,mkdtemp,rm} from 'node:fs/promises';import {createHash} from 'node:crypto';import {tmpdir} from 'node:os';import path from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';import {build} from 'vite';
import {embeddedFbx,embeddedPNG} from './fixtures/embedded-fbx';import {EmbeddedFbxImages} from '../src/embedded-fbx-images';import {WorldImageCache} from '../src/world-image-cache';import {LoadingManager,Mesh,MeshPhongMaterial,type Texture} from 'three';import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
test('actual production-built preparation worker emits bounded exact bytes; repeated parser consumers share one owned Source',async()=>{
 const owned=await mkdtemp(path.join(tmpdir(),'overte-embedded-worker-proof-')),client=fileURLToPath(new URL('../',import.meta.url)),output=path.join(owned,'bundle');
 let worker:Worker|undefined;
 try {
 await build({root:client,configFile:path.join(client,'vite.embedded.config.mjs'),configLoader:'native',logLevel:'error',build:{outDir:output,emptyOutDir:true}});
 const files=await readdir(path.join(output,'assets')),name=files.find(name=>/^model-fbx-worker-.+\.js$/.test(name));assert(name,'The actual fixture build must emit its production worker');
 worker=new Worker(new URL('./fixtures/node-browser-worker.mjs',import.meta.url),{workerData:{workerURL:pathToFileURL(path.join(output,'assets',name)).href}});
 const activeWorker=worker;
 const pending=new Promise<any>((resolve,reject)=>{activeWorker.on('error',reject);activeWorker.on('message',data=>{if(data.type==='ready'){const buffer=embeddedFbx();activeWorker.postMessage({type:'prepare',id:1,buffer},[buffer]);}else if(data.error)reject(Error(data.error));else if(data.buffer)resolve(data);});});
 const timeout=new Promise<never>((_,reject)=>{const timer=setTimeout(()=>reject(Error('Actual worker exceeded30second proof deadline')),30000);void pending.finally(()=>clearTimeout(timer)).catch(()=>{});});
 try{
  const value=await Promise.race([pending,timeout]);assert.equal(value.embeddedCounts.converted,1);assert.equal(value.embeddedImages.length,1);assert.deepEqual(new Uint8Array(value.embeddedImages[0].bytes),embeddedPNG);assert.equal(value.embeddedCounts.rawBytes,embeddedPNG.length);assert.equal(value.embeddedImages[0].digest,createHash('sha256').update(embeddedPNG).digest('hex'));
  const world=new AbortController(),registry=new EmbeddedFbxImages(world.signal);let requests=0;
  class ImageInput extends EventTarget{crossOrigin='';naturalWidth=1;naturalHeight=1;src='';removeAttribute(){this.src='';}async decode(){} }
  const inputs:ImageInput[]=[],cache=new WorldImageCache({signal:world.signal,createImage:()=>{requests++;const image=new ImageInput();inputs.push(image);return image as unknown as HTMLImageElement;}}),maps:Texture[]=[];
  for(let i=0;i<2;i++){const manager=new LoadingManager(),scope=registry.register(value.buffer,value.embeddedImages,world.signal);manager.setURLModifier(scope.resolveURL);manager.addHandler(/\.png$/i,cache.loader(manager));const model=new FBXLoader(manager).parse(value.buffer,'');model.traverse(o=>{if(o instanceof Mesh){maps.push((o.material as MeshPhongMaterial).map!);o.geometry.dispose();(o.material as MeshPhongMaterial).dispose();}});}
  assert.equal(requests,1);for(const image of inputs)image.dispatchEvent(new Event('load'));await new Promise(r=>setTimeout(r,0));assert.equal(maps[0].source,maps[1].source);world.abort();assert.equal(registry.statistics.bytes,0);assert.equal(registry.statistics.scopes,0);for(const map of maps)map.dispose();
 }finally{await activeWorker.terminate();worker=undefined;}
 }finally{await worker?.terminate();await rm(owned,{recursive:true,force:true});}
});
