// SPDX-License-Identifier: Apache-2.0
// Actual World/Three/cache methods. Controlled Image and transport boundaries:
// these CPU cases do not establish HTML decode, network or renderer fidelity.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {BrowserWorld} from '../src/world';
import {WorldImageCache} from '../src/world-image-cache';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {ModelResources} from '../src/model-resources';
import {EmbeddedFbxImages} from '../src/embedded-fbx-images';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
function deferred<T>(){let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return{promise,resolve};}
const outcome=<T>(p:Promise<T>)=>p.then(value=>({value,error:undefined}),error=>({value:undefined,error:error as Error}));
class ImageBoundary extends EventTarget{
  crossOrigin='';naturalWidth=2;naturalHeight=2;src='';removals=0;decodeGate?:ReturnType<typeof deferred<void>>;onRemove?:()=>void;
  removeAttribute(name:string){assert.equal(name,'src');this.src='';this.removals++;this.onRemove?.();}
  async decode(){if(this.decodeGate)await this.decodeGate.promise;}
  loaded(){this.dispatchEvent(new Event('load'));}
}
function fixture(){
  const world:any=Object.create(BrowserWorld.prototype),abort=new AbortController(),images:ImageBoundary[]=[],textures:THREE.Texture[]=[],roots:THREE.Object3D[]=[];
  let generation=1,approved=true,captures=0,warning=0;
  const previousFetch=globalThis.fetch,buffer=fstTextureAdmissionFbx();
  // Only the transport byte boundary is controlled; the real Three FBX parser,
  // World manager and geometry/material/Source constructors execute unchanged.
  globalThis.fetch=async input=>new Response(String(input).endsWith('.json')?'{}':buffer.slice(0));
  const cache=new WorldImageCache({signal:abort.signal,createImage:()=>{const image=new ImageBoundary();images.push(image);return image as unknown as HTMLImageElement;}});
  Object.assign(world,{abort,disposed:false,imageCache:cache,loadManagers:new Set(),preparedFbx:new PreparedFbxCache({signal:abort.signal}),preparedFbxEpoch:0,
    embeddedFbxImages:new EmbeddedFbxImages(abort.signal),embeddedFbxCounts:{preparations:0,convertedImages:0,extractedBytes:0,skippedOversize:0,skippedUnsupported:0},
    fbxPreparePool:{async prepare(buffer:ArrayBuffer){return{buffer,phases:{decodeMs:0,materialBindingsMs:0}};}},
    recordLoadDuration(){},recordLoadPhase(){},configureAlpha:async()=>{},
    options:{onStatus(){warning++;},resolveAsset(url:string){return url;},captureAssetAuthority(){captures++;const captured=generation;return{generation:String(captured),assertCurrent(){if(!approved||captured!==generation)throw new DOMException('Approval ended','AbortError');}};}}});
  return{world,abort,cache,images,counts:()=>({captures,warning}),
    read:async(url='https://owned.invalid/image.png',signal=abort.signal)=>{const value=await world.texture(url,true,'albedo',signal) as THREE.Texture;textures.push(value);return value;},
    model:async(signal=abort.signal,onGeometryReady?:(root:THREE.Object3D)=>void)=>{const value=await world.loadModel('https://owned.invalid/model.fbx',new Set(),undefined,signal,onGeometryReady) as THREE.Object3D;roots.push(value);return value;},
    revoke(){approved=false;},approve(){approved=true;generation++;},
    close(){abort.abort();for(const image of images)image.decodeGate?.resolve();cache.close();world.preparedFbx.dispose();world.embeddedFbxImages.close();for(const texture of textures)texture.dispose();for(const root of roots){const resources=new ModelResources();resources.capture(root);resources.releaseKeeping();}globalThis.fetch=previousFetch;}};
}
async function completeImages(f:ReturnType<typeof fixture>){await tick();for(const image of f.images)if(image.src)image.loaded();await tick();}
for(const hook of ['invalidateSourceTexts','invalidateModelParses'] as const){
  test(`World ${hook} drops ready image lease and preserves borrowed Source/sampler state`,async()=>{
    const f=fixture();try{const p=f.read();await completeImages(f);const first=await p,oldSource=first.source,version=oldSource.version;first.wrapS=THREE.RepeatWrapping;
      const same=await f.read();assert.notEqual(first,same);assert.equal(same.source,oldSource);assert.equal(same.wrapS,THREE.ClampToEdgeWrapping);assert.equal(oldSource.version,version);
      f.revoke();f.world[hook]();assert.equal(oldSource.data,f.images[0]);assert.equal(oldSource.version,version);f.approve();const next=f.read();await completeImages(f);assert.notEqual((await next).source,oldSource);assert.equal(f.images.length,2);assert(f.counts().captures>=3);
    }finally{f.close();}
  });
  test(`World ${hook} refuses a queued ready hit`,async()=>{
    const f=fixture();try{const p=f.read();await completeImages(f);await p;const next=outcome(f.read());f.world[hook]();assert.equal((await next).error?.name,'AbortError');assert.equal(f.world.loadManagers.size,0);}finally{f.close();}
  });
  test(`World ${hook} cancels active load before fresh approval`,async()=>{
    const f=fixture();try{const old=outcome(f.read());assert.equal(f.cache.stats().active,1);f.revoke();f.world[hook]();assert.equal((await old).error?.name,'AbortError');assert.equal(f.images[0].removals,1);f.approve();const fresh=f.read();await completeImages(f);assert.equal((await fresh).source.data,f.images[1]);}finally{f.close();}
  });
  test(`World ${hook} rejects pending decode but retains its uncancellable slot until settlement`,async()=>{
    const f=fixture();try{const old=outcome(f.read());const gate=f.images[0].decodeGate=deferred<void>();f.images[0].loaded();await tick();f.revoke();f.world[hook]();assert.equal((await old).error?.name,'AbortError');assert.equal(f.cache.stats().active,1);assert.equal(f.cache.stats().pending,1);
      f.approve();const next=f.read();await completeImages(f);const fresh=await next;gate.resolve();await tick();assert.equal(f.cache.stats().active,0);assert.equal(f.cache.stats().pending,0);assert.equal((await f.read()).source,fresh.source);assert.notEqual(fresh.source.data,f.images[0]);
    }finally{f.close();}
  });
}
test('World catches missing invalidation callback on approval rollover',async()=>{
  const f=fixture();try{const p=f.read();await completeImages(f);const old=await p;f.approve();const next=f.read();await completeImages(f);assert.notEqual((await next).source,old.source);assert.equal(f.images.length,2);}finally{f.close();}
});
test('World rejects unapproved image routes before image creation',async()=>{
  const f=fixture();try{f.revoke();await assert.rejects(f.read(),{name:'AbortError'});assert.equal(f.images.length,0);}finally{f.close();}
});
test('World ready delivery rechecks authority even without a callback',async()=>{
  const f=fixture();try{const p=f.read();await completeImages(f);await p;const hit=outcome(f.read());f.revoke();assert.equal((await hit).error?.name,'AbortError');}finally{f.close();}
});
test('World image first same-approval metadata read does not cancel its producer',async()=>{
  const f=fixture();try{const p=f.read();await f.world.sourceText('https://owned.invalid/material.json','fixture',8192,f.abort.signal);assert.equal(f.images[0].removals,0);await completeImages(f);await p;}finally{f.close();}
});
test('World new-approval read admitted from remove-src callback survives old invalidation',async()=>{
  const f=fixture();try{const old=outcome(f.read());let next:ReturnType<typeof f.read>|undefined;f.images[0].onRemove=()=>{f.images[0].onRemove=undefined;f.approve();next=f.read();};f.revoke();f.world.invalidateSourceTexts();assert.equal((await old).error?.name,'AbortError');assert(next);await completeImages(f);const value=await next;assert.equal(f.world.imageGeneration,'2');assert.equal((await f.read()).source,value.source);}finally{f.close();}
});
test('World stale rollover never stomps a newer approval from an abort callback',async()=>{
  const f=fixture();try{const old=outcome(f.read());let newest:ReturnType<typeof f.read>|undefined;f.images[0].onRemove=()=>{f.images[0].onRemove=undefined;f.approve();newest=f.read();};f.approve();const stale=outcome(f.read());assert.equal((await old).error?.name,'AbortError');assert.equal((await stale).error?.name,'AbortError');assert(newest);await completeImages(f);const current=await newest;assert.equal(f.world.imageGeneration,'3');assert.equal((await f.read()).source,current.source);}finally{f.close();}
});
test('cache reentrant readmission survives invalidate; only old ready continuations revoke',async()=>{
  const abort=new AbortController(),images:ImageBoundary[]=[],cache=new WorldImageCache({signal:abort.signal,createImage:()=>{const image=new ImageBoundary();images.push(image);return image as unknown as HTMLImageElement;}});
  try{const old=cache.acquire('same',abort.signal,''),result=outcome(old.ready);let next:ReturnType<typeof cache.acquire>|undefined;images[0].onRemove=()=>{next=cache.acquire('same',abort.signal,'');};cache.invalidate();assert.equal((await result).error?.name,'AbortError');assert(next);images[1].loaded();await next.ready;assert.equal(cache.stats().retainedEntries,1);}finally{abort.abort();}
});
test('six retired decodes retain six physical slots and bound pending admission across approval',async()=>{
  const f=fixture();try{const old=Array.from({length:6},(_,i)=>outcome(f.read(`https://owned.invalid/${i}.png`)));const gates=f.images.map(image=>image.decodeGate=deferred<void>());for(const image of f.images)image.loaded();await tick();f.revoke();f.world.invalidateModelParses();assert((await Promise.all(old)).every(value=>value.error?.name==='AbortError'));
    f.approve();const next=f.read('https://owned.invalid/fresh.png');assert.equal(f.cache.stats().active,6);assert.equal(f.cache.stats().queued,1);assert.equal(f.images[6].src,'');assert.equal(f.cache.stats().peakActive,6);gates[0].resolve();await tick();assert.notEqual(f.images[6].src,'');f.images[6].loaded();await next;for(const gate of gates)gate.resolve();await tick();assert.equal(f.cache.stats().active,0);assert.equal(f.cache.stats().pendingKeyBytes,0);
  }finally{f.close();}
});
test('one reader abort preserves same-approval joined decode and Source',async()=>{
  const f=fixture(),a=new AbortController();try{const old=outcome(f.read(undefined,a.signal)),next=f.read();assert.equal(f.images.length,1);a.abort();assert.equal((await old).error?.name,'AbortError');assert.equal(f.images[0].removals,0);await completeImages(f);await next;assert.equal(f.cache.stats().completed,1);}finally{f.close();}
});
test('decode deadline releases readers but retains occupied slots until actual completion, including close',async()=>{
  const abort=new AbortController(),image=new ImageBoundary(),cache=new WorldImageCache({signal:abort.signal,deadlineMs:5,maximumActive:1,maximumPending:1,createImage:()=>image as unknown as HTMLImageElement});
  const gate=image.decodeGate=deferred<void>();try{const first=outcome(cache.acquire('a',abort.signal,'').ready);image.loaded();assert.match((await first).error!.message,/deadline/);assert.equal(cache.stats().active,1);assert.throws(()=>cache.acquire('b',abort.signal,''),/pending/);cache.close();assert.equal(cache.stats().active,1);gate.resolve();await tick();assert.equal(cache.stats().pending,0);assert.equal(cache.stats().pendingKeyBytes,0);}finally{gate.resolve();abort.abort();}
});
for(const hook of ['invalidateSourceTexts','invalidateModelParses'] as const){
  test(`actual World binary FBX ${hook} cancels image-dependent root and owns exact disposal`,async()=>{
    const f=fixture();let root:THREE.Object3D|undefined,disposed=0;try{const old=outcome(f.model(undefined,value=>{root=value;value.traverse(object=>{if(object instanceof THREE.Mesh)object.geometry.addEventListener('dispose',()=>disposed++);});}));await tick();await tick();assert(root);assert.equal(f.images.length,3);const gate=f.images[0].decodeGate=deferred<void>();f.images[0].loaded();await tick();f.revoke();f.world[hook]();assert.equal((await old).error?.name,'AbortError');assert.equal(disposed,1);assert.equal(f.world.loadManagers.size,0);assert.equal(f.counts().warning,0);gate.resolve();await tick();
      f.approve();const fresh=f.model();await completeImages(f);await completeImages(f);const next=await fresh;assert.notEqual(next,root);assert.equal(next.userData.avatarFormat,'fbx');let mesh!:THREE.Mesh;next.traverse(o=>{if(o instanceof THREE.Mesh)mesh=o;});assert(mesh);const materials=mesh.material as THREE.MeshPhongMaterial[];assert.equal(materials[0].map,materials[1].map);assert.equal(f.cache.stats().active,0);
    }finally{f.close();}
  });
}
test('actual World binary FBX repeated readers have own graphs/materials/samplers but same approved images',async()=>{
  const f=fixture();try{const first=f.model();await completeImages(f);await completeImages(f);const a=await first,b=await f.model();let am!:THREE.Mesh,bm!:THREE.Mesh;a.traverse(o=>{if(o instanceof THREE.Mesh)am=o;});b.traverse(o=>{if(o instanceof THREE.Mesh)bm=o;});assert.notEqual(am,bm);assert.notEqual(am.geometry,bm.geometry);const aa=am.material as THREE.MeshPhongMaterial[],bb=bm.material as THREE.MeshPhongMaterial[];assert.notEqual(aa[0],bb[0]);assert.notEqual(aa[0].map,bb[0].map);assert.equal(aa[0].map!.source,bb[0].map!.source);assert.equal(f.images.length,3);assert.equal(am.geometry.attributes.position.count,6);}finally{f.close();}
});
test('actual World binary FBX ready and queued-ready model readers revoke under reapproval',async()=>{
  const f=fixture();try{const p=f.model();await completeImages(f);await completeImages(f);const old=await p;const queued=outcome(f.model());f.revoke();f.world.invalidateSourceTexts();assert.equal((await queued).error?.name,'AbortError');f.approve();const next=f.model();await completeImages(f);await completeImages(f);const fresh=await next;let oldMap!:THREE.Texture,newMap!:THREE.Texture;old.traverse(o=>{if(o instanceof THREE.Mesh)oldMap=(o.material as THREE.MeshPhongMaterial[])[0].map!;});fresh.traverse(o=>{if(o instanceof THREE.Mesh)newMap=(o.material as THREE.MeshPhongMaterial[])[0].map!;});assert.notEqual(newMap.source,oldMap.source);assert.equal(f.images.length,6);assert.equal(oldMap.image,f.images[0]);}finally{f.close();}
});
test('actual World binary FBX rejects a root revoked at final alpha continuation and disposes its graph',async()=>{
  const f=fixture();let disposed=0;try{f.world.configureAlpha=async()=>{f.revoke();};const read=outcome(f.model(undefined,root=>root.traverse(o=>{if(o instanceof THREE.Mesh)o.geometry.addEventListener('dispose',()=>disposed++);})));await completeImages(f);await completeImages(f);assert.equal((await read).error?.name,'AbortError');assert.equal(disposed,1);assert.equal(f.world.loadManagers.size,0);}finally{f.close();}
});
test('actual scoped loader refuses old ready callback and accounts manager item exactly once',async()=>{
  const abort=new AbortController(),image=new ImageBoundary(),cache=new WorldImageCache({signal:abort.signal,createImage:()=>image as unknown as HTMLImageElement});
  try{const ready=cache.acquire('same',abort.signal,'');image.loaded();await ready.ready;const manager=new THREE.LoadingManager();let loads=0,errors=0,ends=0;manager.onLoad=()=>ends++;cache.loader(manager).load('same',()=>loads++,undefined,()=>errors++);cache.invalidate();await tick();assert.equal(loads,0);assert.equal(errors,1);assert.equal(ends,1);assert.equal(ready.source.data,image);}finally{abort.abort();}
});
test('retired decode retains pending-key budget; fresh queued reader cannot exceed it',async()=>{
  const abort=new AbortController(),image=new ImageBoundary(),cache=new WorldImageCache({signal:abort.signal,maximumPendingKeyBytes:4,createImage:()=>image as unknown as HTMLImageElement}),gate=image.decodeGate=deferred<void>();
  try{const old=outcome(cache.acquire('aa',abort.signal,'').ready);image.loaded();cache.invalidate();assert.equal((await old).error?.name,'AbortError');assert.equal(cache.stats().pendingKeyBytes,4);assert.throws(()=>cache.acquire('b',abort.signal,''),/memory budget/);gate.resolve();await tick();assert.equal(cache.stats().pendingKeyBytes,0);}finally{gate.resolve();abort.abort();}
});
// Real CompressedColorSession authority lifecycle, controlled transport only.
import {CompressedColorSession} from '../src/compressed-color-session';
class SocketBoundary{
  static OPEN=1;static current:SocketBoundary;readyState=0;bufferedAmount=0;binaryType='blob';
  onopen?:()=>void;onmessage?:(e:{data:string})=>void;onclose?:(e:{reason:string})=>void;
  constructor(_url:URL){SocketBoundary.current=this;}
  send(_value:unknown){}open(){this.readyState=1;this.onopen?.();}deliver(value:unknown){this.onmessage?.({data:JSON.stringify(value)});}close(_code?:number,reason=''){this.readyState=3;this.onclose?.({reason});}
}
test('genuine session same-revision approval changes reject old ready Sources at unchanged asset route',async()=>{
  const old=new Map(['window','WebSocket'].map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  Object.defineProperty(globalThis,'window',{configurable:true,value:{location:{href:'https://owned.invalid/client'}}});Object.defineProperty(globalThis,'WebSocket',{configurable:true,value:SocketBoundary});
  const f=fixture();let connected=false;
  const session=new CompressedColorSession({message(m){if(m.type==='state'&&m.state==='connecting'&&connected){connected=false;f.world.invalidateSourceTexts();f.world.invalidateModelParses();}if(m.type==='state'&&m.state==='connected')connected=true;},error(){},closed(){},audio(){}});
  try{session.join('overte://owned.invalid','Fixture');const socket=SocketBoundary.current;socket.open();socket.deliver({type:'state',state:'connecting',sessionId:'fixture-session'});socket.deliver({type:'state',state:'connected',sessionId:'fixture-session',permissionRevision:1});
    f.world.options.captureAssetAuthority=()=>session.captureAssetAuthority();f.world.options.resolveAsset=(url:string)=>session.assetURL(url);const url='https://assets.invalid/image.png',route=session.assetURL(url),generation=session.captureAssetAuthority().generation;
    const p=f.read(url);await completeImages(f);const first=await p;socket.deliver({type:'state',state:'connecting',sessionId:'fixture-session'});socket.deliver({type:'state',state:'connected',sessionId:'fixture-session',permissionRevision:1});assert.equal(session.assetURL(url),route);assert.notEqual(session.captureAssetAuthority().generation,generation);
    const next=f.read(url);await completeImages(f);assert.notEqual((await next).source,first.source);assert.equal(f.images.length,2);
  }finally{session.leave();f.close();for(const[name,descriptor]of old){if(descriptor)Object.defineProperty(globalThis,name,descriptor);else Reflect.deleteProperty(globalThis,name);}}
});
test('World preserves new image approval admitted by actual prepared-producer abort before outer image invalidation',async()=>{
  const f=fixture(),gate=deferred<{buffer:ArrayBuffer;phases:{decodeMs:number;materialBindingsMs:number}}>();try{const oldImage=outcome(f.read());let newest:ReturnType<typeof f.read>|undefined;
    const oldPrepared=outcome(f.world.preparedFbx.get('held',async(signal:AbortSignal)=>{signal.addEventListener('abort',()=>{f.approve();newest=f.read();},{once:true});return gate.promise;}));await tick();f.revoke();f.world.invalidateModelParses();assert.equal((await oldPrepared).error?.name,'AbortError');assert.equal((await oldImage).error?.name,'AbortError');assert(newest);await completeImages(f);const fresh=await newest;assert.equal(f.world.imageGeneration,'2');assert.equal((await f.read()).source,fresh.source);
  }finally{gate.resolve({buffer:new ArrayBuffer(0),phases:{decodeMs:0,materialBindingsMs:0}});f.close();}
});
test('World publishes image epoch before abort listeners and keeps nested newer approval',async()=>{
  const f=fixture();try{const old=outcome(f.read());let newest:ReturnType<typeof f.read>|undefined;f.world.imageEpoch.signal.addEventListener('abort',()=>{f.approve();newest=f.read();},{once:true});f.revoke();f.world.invalidateSourceTexts();assert.equal((await old).error?.name,'AbortError');assert(newest);await completeImages(f);const fresh=await newest;assert.equal(f.world.imageGeneration,'2');assert.equal((await f.read()).source,fresh.source);}finally{f.close();}
});
