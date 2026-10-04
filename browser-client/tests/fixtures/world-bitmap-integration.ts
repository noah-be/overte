// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual World Image publishers and native UV/sampler configuration; no network
// or native-domain compatibility claim. Root executes real GPU comparisons.
import * as THREE from 'three';
import {BrowserWorld} from '../../src/world';
import {SessionUploadTexture} from '../../src/world-bitmap-upload';
export async function runWorldBitmapIntegrationProof(){
 const source=document.createElement('canvas');source.width=source.height=4096;const painter=source.getContext('2d')!;
 painter.fillStyle='#f02008';painter.fillRect(0,0,2048,2048);painter.fillStyle='rgba(8,240,32,0.5)';painter.fillRect(2048,0,2048,2048);
 painter.fillStyle='rgba(16,24,248,0.25)';painter.fillRect(0,2048,2048,2048);painter.fillStyle='#f0c010';painter.fillRect(2048,2048,2048,2048);
 const url=source.toDataURL('image/png'),reports=[];
 for(const enabled of [false,true]){
  const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;width:256px;height:128px';document.body.append(host);
  const warnings:string[]=[];const world=new BrowserWorld(host,{bitmapUpload:enabled,resolveAsset:url=>url,captureAssetAuthority:()=>({generation:'fixture-'+Number(enabled),assertCurrent(){}}),onPose(){},onInteract(){},onStatus:(message,kind)=>{if(kind==='warning'||kind==='error')warnings.push(message);}});
  const w=world as unknown as {renderer:THREE.WebGLRenderer;camera:THREE.PerspectiveCamera;objects:Map<string,THREE.Group>;frame:number;bitmapUploads?:{stats():Record<string,number>}};
  const renderer=w.renderer,gl=renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 required');
  const uploads={imageCalls:0,bitmapCalls:0,totalMs:0,maxMs:0};const originalMethods=new Map<string,unknown>();
  for(const name of ['texImage2D','texSubImage2D']){const driver=gl as unknown as Record<string,(...args:unknown[])=>unknown>,original=driver[name];originalMethods.set(name,original);
   driver[name]=function(...args:unknown[]){const last=args[args.length-1],kind=last instanceof HTMLImageElement?'image':last instanceof ImageBitmap?'bitmap':undefined;const measured=kind!==undefined&&(last as HTMLImageElement|ImageBitmap).width===4096;const start=measured?performance.now():0;
    try{return original.apply(gl,args);}finally{if(measured){if(kind==='image')uploads.imageCalls++;else uploads.bitmapCalls++;const elapsed=performance.now()-start;uploads.totalMs+=elapsed;uploads.maxMs=Math.max(uploads.maxMs,elapsed);}}
   };
  }
  let disposal:unknown;
  try{
   world.setPresentationEnabled(false);world.setEnabled(false);world.setInputEnabled(false);cancelAnimationFrame(w.frame);renderer.setPixelRatio(1);renderer.setSize(256,128);world.scene.background=new THREE.Color(0);w.camera.position.set(0,0,4);w.camera.quaternion.identity();w.camera.aspect=2;w.camera.updateProjectionMatrix();
   // The second native sampler is genuinely different and its out-of-range UVs
   // visibly distinguish clamp from repeat, rather than changing a default twice.
   world.upsertEntities(['left','right'].map((id,index)=>({id,type:'Image',imageURL:url,emissive:true,keepAspectRatio:false,dimensions:{x:1.8,y:1.8,z:.1},position:{x:index===0?-1:1,y:0,z:0},sampler:{minFilter:'linearMipmapLinear',magFilter:'linear',wrapModeU:index===0?'repeat':'clamp',wrapModeV:'repeat'},subImage:{x:1024,y:0,width:4096,height:4096}})));
   const deadline=performance.now()+60000;
   while(['left','right'].some(id=>w.objects.get(id)?.userData.shadersReady!==true)||world.getPerformance().compilingGraphics!==0){if(warnings.length)throw Error(warnings.join('; '));if(performance.now()>deadline)throw Error('Actual 4096 World Image publication deadline');await new Promise(resolve=>setTimeout(resolve,10));}
   const maps:THREE.Texture[]=[],states:unknown[]=[];
   for(const id of ['left','right']){let mesh:THREE.Mesh|undefined;w.objects.get(id)!.traverse(o=>{if(o instanceof THREE.Mesh)mesh=o;});if(!mesh||Array.isArray(mesh.material)||!(mesh.material instanceof THREE.MeshBasicMaterial)||!mesh.material.map)throw Error('Actual unlit Image material required');const map=mesh.material.map;maps.push(map);
    states.push({flipY:map.flipY,premultiplyAlpha:map.premultiplyAlpha,colorSpace:map.colorSpace,wrapS:map.wrapS,wrapT:map.wrapT,minFilter:map.minFilter,magFilter:map.magFilter,anisotropy:map.anisotropy,offset:map.offset.toArray(),repeat:map.repeat.toArray(),matrix:map.matrix.elements.slice(),transparent:mesh.material.transparent,alphaTest:mesh.material.alphaTest,side:mesh.material.side,depthWrite:mesh.material.depthWrite});
    if(enabled?!(map instanceof SessionUploadTexture):map instanceof SessionUploadTexture)throw Error('Captured default-off/conversion path incorrect');if((map.image as HTMLImageElement|ImageBitmap).width!==4096||(map.image as HTMLImageElement|ImageBitmap).height!==4096)throw Error('Original dimensions changed');
   }
   if(maps[0].source!==maps[1].source||maps[0]===maps[1]||maps[0].wrapS===maps[1].wrapS)throw Error('Shared Source and independent genuinely different samplers required');
   const programsBefore=renderer.info.programs?.length,versions=maps.map(map=>map.version),before=performance.now();renderer.render(world.scene,w.camera);const firstRenderMs=performance.now()-before;
   const pixels=new Uint8Array(256*128*4);gl.readPixels(0,0,256,128,gl.RGBA,gl.UNSIGNED_BYTE,pixels);if(gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual first-frame GL error');
   let reds=0,greens=0,blues=0;for(let i=0;i<pixels.length;i+=4){if(pixels[i]>pixels[i+1]+40&&pixels[i]>pixels[i+2]+40)reds++;if(pixels[i+1]>pixels[i]+30&&pixels[i+1]>pixels[i+2]+30)greens++;if(pixels[i+2]>pixels[i]+20&&pixels[i+2]>pixels[i+1]+20)blues++;}if(!reds||!greens||!blues)throw Error('Real opaque/residual-alpha image regions must be visible');
   const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels))).map(v=>v.toString(16).padStart(2,'0')).join('');
   for(let frame=0;frame<20;frame++)renderer.render(world.scene,w.camera);if(versions.some((value,index)=>maps[index].version!==value))throw Error('Steady rendering changed texture versions');
   const programsAfter=renderer.info.programs?.length;if(programsAfter!==programsBefore)throw Error('Converted maps caused a new first-draw shader program');
   const statistics=world.getPerformance().bitmapUpload;reports.push({enabled,programsBefore,programsAfter,states,pixelHash:hash,reds,greens,blues,uploads:{...uploads},firstRenderMs,statistics,warnings});
  }finally{
   try{world.dispose();disposal={owner:w.bitmapUploads?.stats(),textures:renderer.info.memory.textures,geometries:renderer.info.memory.geometries,objects:w.objects.size};}finally{for(const [name,original]of originalMethods)(gl as unknown as Record<string,unknown>)[name]=original;renderer.forceContextLoss();host.remove();}
  }
  Object.assign(reports[reports.length-1]!,{disposal});
 }
 return{reports,width:4096,height:4096,qualityChanged:false};
}
