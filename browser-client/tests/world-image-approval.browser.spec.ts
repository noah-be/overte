// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real HTMLImageElement PNG decode and WebGL pixels; authored HTTP transports.
import {expect,test as base} from '@playwright/test';
import type {Page} from '@playwright/test';
const green=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGNk+M/AwMDAxMDAwMDAAAAMHgEDBINhkwAAAABJRU5ErkJggg==','base64');
const red=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==','base64');
const vertices=Buffer.from(new Float32Array([-.5,-.5,0,.5,-.5,0,0,.5,0,0,0,1,0,.5,1]).buffer);
const gltf={asset:{version:'2.0'},scene:0,scenes:[{nodes:[0]}],nodes:[{mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0,TEXCOORD_0:1},material:0}]}],buffers:[{byteLength:vertices.length,uri:'triangle.bin'}],bufferViews:[{buffer:0,byteOffset:0,byteLength:36},{buffer:0,byteOffset:36,byteLength:24}],accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[-.5,-.5,0],max:[.5,.5,0]},{bufferView:1,componentType:5126,count:3,type:'VEC2'}],extensionsUsed:['KHR_materials_unlit'],materials:[{extensions:{KHR_materials_unlit:{}},pbrMetallicRoughness:{baseColorTexture:{index:0}},doubleSided:true}],textures:[{source:0}],images:[{uri:'green.png'}]};
import {createServer,type ServerResponse} from 'node:http';
import {WebSocketServer} from 'ws';
interface Assets {origin:string;requests:string[];held:ServerResponse[];generation:number;reapprove():void}
const test=base.extend<{assets:Assets}>({assets:async({},use)=>{
 const state:Assets={origin:'',requests:[],held:[],generation:1,reapprove(){state.generation++;for(const client of sockets.clients){client.send(JSON.stringify({type:'state',state:'connecting',sessionId:'image-fixture'}));client.send(JSON.stringify({type:'state',state:'connected',sessionId:'image-fixture',permissionRevision:1}));}}};
 const server=createServer((request,response)=>{
  const address=new URL(request.url!,state.origin);response.setHeader('Cache-Control','no-store');
  if(address.pathname==='/'){response.setHeader('Content-Type','text/html');response.end('<!doctype html><body style="margin:0"></body>');return;}
  let file=address.pathname;
  if(file==='/api/assets/image-fixture'){
   const original=address.searchParams.get('url');if(!original){response.writeHead(400).end();return;}
   const input=new URL(original);if(input.origin!==state.origin){response.writeHead(403).end();return;}file=input.pathname;
  }
  state.requests.push(file);
  if(/^\/approval-pending\/[0-6]\.png$/.test(file)){state.held.push(response);return;}
  if(file==='/approval-model/triangle.gltf'){response.setHeader('Content-Type','model/gltf+json');response.end(JSON.stringify(gltf));return;}
  if(file==='/approval-model/triangle.bin'){response.setHeader('Content-Type','application/octet-stream');response.end(vertices);return;}
  if(['/approval-ready.png','/approval-pending/fresh.png','/approval-model/green.png'].includes(file)){response.setHeader('Content-Type','image/png');response.end(state.generation===1?green:red);return;}
  response.writeHead(404).end('Unknown authored dependency');
 });
 const sockets=new WebSocketServer({server,path:'/session',maxPayload:192*1024,perMessageDeflate:false});
 sockets.on('connection',socket=>socket.on('message',data=>{const message=JSON.parse(data.toString());if(message.type==='join'){socket.send(JSON.stringify({type:'state',state:'connecting',sessionId:'image-fixture'}));socket.send(JSON.stringify({type:'state',state:'connected',sessionId:'image-fixture',permissionRevision:1}));}}));
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const address=server.address();if(!address||typeof address==='string')throw Error('Owned HTTP fixture unavailable');state.origin=`http://127.0.0.1:${address.port}`;
 try{await use(state);}finally{for(const response of state.held)response.destroy();for(const client of sockets.clients)client.terminate();await new Promise<void>(resolve=>sockets.close(()=>resolve()));server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));}
}});
async function blank(page:Page,assets:Assets,baseURL:string|undefined){if(!baseURL)throw Error('Reviewed Vite origin required');await page.goto(assets.origin);await page.evaluate(origin=>{(window as any).viteOrigin=origin;},new URL(baseURL).origin);}
function acesGreen(exposure:number):number[]{
  const [r,g,b]=[.35458,.90834,.13383].map(value=>value*exposure/.6)
    .map(value=>(value*(value+.0245786)-.000090537)/(value*(.983729*value+.432951)+.238081));
  return [1.60475*r-.53108*g-.07367*b,-.10208*r+1.10813*g-.00605*b,-.00327*r-.07276*g+1.07602*b]
    .map(value=>Math.max(0,Math.min(1,value))).map(value=>Math.round(255*(value<=.0031308?value*12.92:1.055*Math.pow(value,1/2.4)-.055)));
}
function expectPixel(actual:number[],expected:number[]){
  expect(actual[3]).toBe(255);
  for(let channel=0;channel<3;channel++)expect(Math.abs(actual[channel]-expected[channel]),`Color channel ${channel} must match the analytic authored-color oracle`).toBeLessThanOrEqual(1);
}
async function pixels(page:Page){
  const bytes=await page.locator('#approval-model-world canvas').screenshot();
  return page.evaluate(async base64=>{const image=await createImageBitmap(await(await fetch(`data:image/png;base64,${base64}`)).blob());const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;const context=canvas.getContext('2d')!;context.drawImage(image,0,0);const rgb=[...context.getImageData(image.width/2,image.height/2,1,1).data];image.close();return rgb;},bytes.toString('base64'));
}
function errors(page:Page){const result:string[]=[];page.on('pageerror',e=>result.push(e.message));return result;}

test('Real ready PNG readers refuse revoked delivery while loaded samplers keep exact pixels',async({page,assets,baseURL})=>{
 const faults=errors(page);await blank(page,assets,baseURL);
 const result=await page.evaluate(async()=>{
  const threePath=(window as any).viteOrigin+'/node_modules/three/build/three.module.js',cachePath=(window as any).viteOrigin+'/src/world-image-cache.ts';const THREE=await import(/* @vite-ignore */threePath),{WorldImageCache}=await import(/* @vite-ignore */cachePath);const session=new AbortController(),cache=new WorldImageCache({signal:session.signal});const renderer=new THREE.WebGLRenderer({antialias:false});renderer.setSize(64,64);renderer.setClearColor(0xff00ff);document.body.append(renderer.domElement);
  const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10);camera.position.z=2;const geometry=new THREE.PlaneGeometry(2,2);const textures:any[]=[],materials:any[]=[];
  const pixel=(texture:any)=>{const material=new THREE.MeshBasicMaterial({map:texture,toneMapped:false});materials.push(material);const mesh=new THREE.Mesh(geometry,material);scene.add(mesh);renderer.render(scene,camera);const gl=renderer.getContext(),rgba=new Uint8Array(4);gl.readPixels(32,32,1,1,gl.RGBA,gl.UNSIGNED_BYTE,rgba);scene.remove(mesh);return [...rgba];};
  try{
   const first=await cache.loader(new THREE.LoadingManager()).loadAsync(`${location.origin}/approval-ready.png`);first.colorSpace=THREE.SRGBColorSpace;textures.push(first);
   const second=await cache.loader(new THREE.LoadingManager()).loadAsync(`${location.origin}/approval-ready.png`);second.colorSpace=THREE.SRGBColorSpace;textures.push(second);second.repeat.set(2,3);
   const before=pixel(first),source=first.source,image=first.image;
   const manager=new THREE.LoadingManager();let delivered=0,refused=0,retired=0,accounted=0;manager.onLoad=()=>accounted++;
   const stale=cache.loader(manager).load(`${location.origin}/approval-ready.png`,()=>delivered++,undefined,()=>refused++);stale.addEventListener('dispose',()=>retired++);
   cache.invalidate();await Promise.resolve();await Promise.resolve();await Promise.resolve();await Promise.resolve();
   const fresh=await cache.loader(new THREE.LoadingManager()).loadAsync(`${location.origin}/approval-ready.png`);fresh.colorSpace=THREE.SRGBColorSpace;textures.push(fresh);
   const after=pixel(second),freshPixel=pixel(fresh);first.dispose();textures.splice(textures.indexOf(first),1);const afterNeighborRemoval=pixel(second);
   return {before,after,freshPixel,afterNeighborRemoval,oldImageStillReal:image instanceof HTMLImageElement&&image.naturalWidth===2&&image.naturalHeight===2,sharedOldSource:second.source===source,freshSource:fresh.source!==source,freshImage:fresh.image!==image,independentSampler:first!==second&&second.repeat.x===2&&second.repeat.y===3&&first.repeat.x===1,delivered,refused,retired,accounted,stats:cache.stats()};
  }finally{session.abort();for(const material of materials)material.dispose();for(const texture of textures)texture.dispose();geometry.dispose();renderer.dispose();renderer.domElement.remove();}
 });
 for(const value of [result.before,result.after,result.freshPixel,result.afterNeighborRemoval])expect(value).toEqual([0,255,0,255]);
 expect(result).toMatchObject({oldImageStillReal:true,sharedOldSource:true,freshSource:true,freshImage:true,independentSampler:true,delivered:0,refused:1,retired:1,accounted:1});expect(result.stats.uniqueImages).toBe(2);expect(result.stats.peakActive).toBeLessThanOrEqual(6);expect(faults).toEqual([]);
});

test('Real in-flight and queued PNG consumers revoke with the original six active slots',async({page,assets,baseURL})=>{
 const faults=errors(page);await blank(page,assets,baseURL);const requests=assets.requests;
 try{
  await page.evaluate(async()=>{const cachePath=(window as any).viteOrigin+'/src/world-image-cache.ts';const {WorldImageCache}=await import(/* @vite-ignore */cachePath);const state=window as any;state.owner=new AbortController();state.cache=new WorldImageCache({signal:state.owner.signal});state.outcomes=[];state.oldReaders=Array.from({length:7},(_,i)=>state.cache.acquire(`${location.origin}/approval-pending/${i}.png`,state.owner.signal,'anonymous').ready.then(()=>state.outcomes.push('delivered'),(e:any)=>state.outcomes.push(e.name)));});
  await expect.poll(()=>assets.held.length).toBe(6);
  expect(await page.evaluate(()=>(window as any).cache.stats())).toMatchObject({active:6,queued:1,pending:7,peakActive:6});expect(requests).not.toContain('/approval-pending/6.png');
  await page.evaluate(async()=>{const state=window as any;state.cache.invalidate();await Promise.all(state.oldReaders);});
  const result=await page.evaluate(async()=>{const state=window as any,reader=state.cache.acquire(`${location.origin}/approval-pending/fresh.png`,state.owner.signal,'anonymous');const record=await reader.ready;const canvas=document.createElement('canvas');canvas.width=canvas.height=1;canvas.getContext('2d')!.drawImage(record.image,0,0,1,1);return {outcomes:state.outcomes,pixel:[...canvas.getContext('2d')!.getImageData(0,0,1,1).data],stats:state.cache.stats()};});
  expect(result.outcomes).toEqual(Array(7).fill('AbortError'));expect(result.pixel).toEqual([0,255,0,255]);expect(result.stats).toMatchObject({active:0,queued:0,pending:0,peakActive:6,cancelled:7,completed:1});expect(requests).not.toContain('/approval-pending/6.png');expect(faults).toEqual([]);
 }finally{await page.evaluate(()=>(window as any).owner?.abort());for(const response of assets.held)response.destroy();}
});

test('Actual loaded Models survive approval-cache revocation until their own removal',async({page,assets,baseURL})=>{
 const faults=errors(page);await blank(page,assets,baseURL);
 try{
  await page.evaluate(async()=>{const worldPath=(window as any).viteOrigin+'/src/world.ts';const {BrowserWorld}=await import(/* @vite-ignore */worldPath);const state=window as any;document.body.innerHTML='<div id="approval-model-world" style="width:640px;height:480px"></div>';state.generation=1;const sessionPath=state.viteOrigin+'/src/compressed-color-session.ts';const {CompressedColorSession}=await import(/* @vite-ignore */sessionPath);state.session=new CompressedColorSession({message(message:any){if(message.type==='state'&&message.state==='connecting'){state.world?.invalidateSourceTexts();state.world?.invalidateModelParses();}if(message.type==='state'&&message.state==='connected')state.generation++;},error(reason:string){throw Error(reason);},closed(){},audio(){}});state.session.join('overte://owned-fixture.invalid','ImageFixture');
   state.world=new BrowserWorld(document.getElementById('approval-model-world')!,{resolveAsset:(url:string)=>state.session.assetURL(url),captureAssetAuthority:()=>state.session.captureAssetAuthority(),onPose:()=>{},onInteract:()=>{},onStatus:()=>{}});
   state.entities=['center','neighbor'].map((id,i)=>({id,type:'Model',modelURL:`${location.origin}/approval-model/triangle.gltf`,position:{x:i*4,y:1.5,z:-3},dimensions:{x:2,y:2,z:.1}}));state.world.setSpawn({x:0,y:.85,z:0});
   state.map=(id:string)=>{let map:any;state.world.objects.get(id).traverse((node:any)=>{if(node.isMesh)map=(Array.isArray(node.material)?node.material[0]:node.material).map;});return map;};
  });
  await expect.poll(()=>page.evaluate(()=>(window as any).session.connected)).toBe(true);await page.evaluate(()=>{const state=window as any;state.originalRoute=state.session.assetURL(`${location.origin}/approval-model/green.png`);state.originalAuthority=state.session.captureAssetAuthority();state.world.setEntities(state.entities);});
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(2);await expect.poll(()=>page.evaluate(()=>(window as any).world.compilingGraphics)).toBe(0);
  const beforePixel=await pixels(page),exposure=await page.evaluate(()=>(window as any).world.renderer.toneMappingExposure);expectPixel(beforePixel,acesGreen(exposure));
  const before=await page.evaluate(()=>{const state=window as any;state.old=state.map('center');state.neighbor=state.map('neighbor');state.oldDisposals=0;state.neighborDisposals=0;state.old.addEventListener('dispose',()=>state.oldDisposals++);state.neighbor.addEventListener('dispose',()=>state.neighborDisposals++);state.old.repeat.set(2,3);return {sameSource:state.old.source===state.neighbor.source,separateSampler:state.old!==state.neighbor,neighborRepeat:state.neighbor.repeat.toArray()};});expect(before).toEqual({sameSource:true,separateSampler:true,neighborRepeat:[1,1]});
  assets.reapprove();await expect.poll(()=>page.evaluate(()=>(window as any).generation)).toBe(3);expect(await page.evaluate(()=>{const state=window as any;let revoked=false;try{state.originalAuthority.assertCurrent();}catch{revoked=true;}return {revoked,sameRoute:state.session.assetURL(`${location.origin}/approval-model/green.png`)===state.originalRoute};})).toEqual({revoked:true,sameRoute:true});
  await page.evaluate(()=>{const state=window as any;state.world.setEntities([...state.entities,{...state.entities[0],id:'fresh',position:{x:8,y:1.5,z:-3}}]);});
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(3);await expect.poll(()=>page.evaluate(()=>(window as any).world.compilingGraphics)).toBe(0);
  const admitted=await page.evaluate(()=>{const state=window as any,fresh=state.map('fresh');const decoded=(map:any)=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=1;canvas.getContext('2d')!.drawImage(map.image,0,0,1,1);return [...canvas.getContext('2d')!.getImageData(0,0,1,1).data];};return {oldDisposals:state.oldDisposals,neighborDisposals:state.neighborDisposals,oldSourceStillShared:state.old.source===state.neighbor.source,newSource:fresh.source!==state.old.source,newImage:fresh.image!==state.old.image,pixels:[decoded(state.old),decoded(state.neighbor),decoded(fresh)]};});
  expect(admitted).toMatchObject({oldDisposals:0,neighborDisposals:0,oldSourceStillShared:true,newSource:true,newImage:true});expect(admitted.pixels).toEqual([[0,255,0,255],[0,255,0,255],[255,0,0,255]]);expect(assets.requests.filter(value=>value==='/approval-model/green.png')).toHaveLength(2);
  await page.evaluate(()=>{const state=window as any;state.world.setEntities([state.entities[0]]);});
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(1);
  expect(await page.evaluate(()=>{const state=window as any;return {oldDisposals:state.oldDisposals,neighborDisposals:state.neighborDisposals,liveCenter:state.map('center')===state.old,imageReady:state.old.image.complete&&state.old.image.naturalWidth===2};})).toEqual({oldDisposals:0,neighborDisposals:1,liveCenter:true,imageReady:true});expectPixel(await pixels(page),acesGreen(exposure));expect(faults).toEqual([]);
  expect(await page.evaluate(()=>{const state=window as any;state.world.dispose();return {oldDisposals:state.oldDisposals,neighborDisposals:state.neighborDisposals};})).toEqual({oldDisposals:1,neighborDisposals:1});
 }finally{await page.evaluate(()=>{const state=window as any;state.world?.dispose();state.session?.leave();});}
});
