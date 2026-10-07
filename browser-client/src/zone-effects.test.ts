// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {UnsignedByteType,AmbientLight,CubeTexture,DataTexture,DirectionalLight,MeshPhongMaterial,PerspectiveCamera,Quaternion,Scene,ShaderLib,Vector3,type WebGLProgramParametersWithUniforms,type WebGLRenderer} from 'three';
import {NativeZoneEnvironment,decodeNativeSkyBounded,createNativeHazeUniforms,evaluateNativeAmbientSH,hasNativeHazeShader,installNativeZoneHaze,integrateNativeAmbientSH,loadNativeSkyTexture,nativeSHCubeDirection,restoreNativeHazeShader,sampleNativeAmbient,nativeHazeParameters,nativeKeyLightAttenuation,nativeSkyColor,nativeSkyDirection,nativeSkyLayout,nativeZoneAmbientLight,nativeZoneKeyLight,resolveZoneEnvironment,sampleNativeHaze,zoneContains} from './zone-effects';
import type {Entity} from './world-data';
import {decodeNativeSky} from './zone-texture-worker';
const zone=(id:string,dimensions={x:10,y:10,z:10},extras:Partial<Entity>={}):Entity=>({id,type:'Zone',dimensions,position:{x:0,y:0,z:0},...extras});
const scene=(...entities:Entity[])=>new Map(entities.map(entity=>[entity.id,entity]));
const near=(actual:number,expected:number,tolerance=1e-10)=>assert(Math.abs(actual-expected)<tolerance,`${actual} differs from ${expected}`);

test('Zone precedence is native bounding volume, then canonical UUID; every component inherits independently',()=>{
  const outer=zone('ffffffff-ffff-ffff-ffff-ffffffffffff',{x:100,y:100,z:100},{keyLightMode:'enabled',ambientLightMode:'enabled',skyboxMode:'enabled',hazeMode:'enabled'});
  const equalLater=zone('{00000000-0000-0000-0000-000000000002}',undefined,{keyLightMode:'disabled',hazeMode:'inherit'});
  const equalFirst=zone('00000000-0000-0000-0000-000000000001',undefined,{skyboxMode:'disabled',keyLightMode:'inherit'});
  const smaller=zone('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',{x:2,y:2,z:2},{ambientLightMode:'disabled'});
  const result=resolveZoneEnvironment(scene(outer,equalLater,equalFirst,smaller),{x:0,y:0,z:0});
  assert.deepEqual(result.zones.map(entity=>entity.id),[smaller.id,equalFirst.id,equalLater.id,outer.id]);
  assert.equal(result.keyLight?.entity,equalLater);assert.equal(result.keyLight?.mode,'disabled');
  assert.equal(result.skybox?.entity,equalFirst);assert.equal(result.skybox?.mode,'disabled');
  assert.equal(result.ambientLight?.entity,smaller);assert.equal(result.haze?.entity,outer);
});
test('Invisible and outside Zones never change lighting; malformed component modes inherit',()=>{
  const hidden=zone('hidden',undefined,{visible:false,keyLightMode:'enabled'}),outside=zone('outside',undefined,{position:{x:30,y:0,z:0},skyboxMode:'enabled'}),invalid=zone('invalid',undefined,{hazeMode:'other'});
  const result=resolveZoneEnvironment(scene(hidden,outside,invalid),{x:0,y:0,z:0});
  assert.deepEqual(result.zones,[invalid]);assert.equal(result.keyLight,undefined);assert.equal(result.haze,undefined);assert.equal(result.skybox,undefined);
});
test('Native normalized containment respects rotation and registration without center-distance shortcuts',()=>{
  const rotation=new Quaternion().setFromAxisAngle(new Vector3(0,1,0),Math.PI/2);
  const entity=zone('rotated',{x:1000,y:2,z:4},{position:{x:2,y:0,z:5},registrationPoint:{x:0,y:.5,z:.5},rotation:{x:rotation.x,y:rotation.y,z:rotation.z,w:rotation.w}});
  const entities=scene(entity);
  assert(zoneContains(entity,{x:2,y:0,z:-994},entities));
  assert(!zoneContains(entity,{x:4.1,y:0,z:-100},entities));
  assert(!zoneContains(entity,{x:2,y:1.1,z:-100},entities));
});
test('Local-only Zone snapshots compose their actual parent transform',()=>{
  const parent:Entity={id:'parent',type:'Box',position:{x:100,y:0,z:0}},child:Entity={id:'child',type:'Zone',parentID:'parent',localPosition:{x:3,y:0,z:0},dimensions:{x:2,y:2,z:2}};
  assert(zoneContains(child,{x:103,y:0,z:0},scene(parent,child)));
  assert(!zoneContains(child,{x:3,y:0,z:0},scene(parent,child)));
});
test('Native sphere strict boundary and ellipsoid inclusive boundary are preserved',()=>{
  const sphere=zone('sphere',{x:2,y:2,z:2},{shapeType:'sphere'}),ellipsoid=zone('ellipse',{x:4,y:2,z:2},{shapeType:'ellipsoid'});
  assert(!zoneContains(sphere,{x:1,y:0,z:0},scene(sphere)));
  assert(zoneContains(sphere,{x:.999,y:0,z:0},scene(sphere)));
  assert(zoneContains(ellipsoid,{x:2,y:0,z:0},scene(ellipsoid)));
  assert(!zoneContains(ellipsoid,{x:1.9,y:.5,z:0},scene(ellipsoid)));
});
test('Each native cylinder tests its correct radial plane and height axis',()=>{
  for(const axis of ['x','y','z'] as const){
    const entity=zone(axis,{x:2,y:2,z:2},{shapeType:'cylinder-'+axis}),point={x:.8,y:.8,z:.8};point[axis]=0;
    assert(!zoneContains(entity,point,scene(entity)));
    point.x=point.y=point.z=0;point[axis]=1;
    assert(zoneContains(entity,point,scene(entity)));point[axis]=1.01;assert(!zoneContains(entity,point,scene(entity)));
  }
});
test('A loaded native compound uses supplied real geometry rather than a bounding-box substitute',()=>{
  const entity=zone('compound',undefined,{shapeType:'compound'}),entities=scene(entity);
  assert(zoneContains(entity,{x:0,y:0,z:0},entities,()=>undefined),'Native uses bounds while the actual resource is unloaded');
  assert(!zoneContains(entity,{x:0,y:0,z:0},entities,()=>false),'Loaded concave gaps are not falsely included');
  assert(zoneContains(entity,{x:100,y:0,z:0},entities,()=>true),'The actual compound resource owns its result');
  assert(!zoneContains(zone('none',undefined,{shapeType:'none'}),{x:0,y:0,z:0},entities));
});
test('Native haze reaches 95 percent at the authored range, unlike squared-distance FogExp2',()=>{
  const haze=nativeHazeParameters(zone('haze',undefined,{haze:{hazeRange:120}}));
  near(sampleNativeHaze(haze,{x:0,y:0,z:0},{x:0,y:0,z:120}).amount,.95);
  near(sampleNativeHaze(haze,{x:0,y:0,z:0},{x:0,y:0,z:60}).amount,1-Math.sqrt(.05));
  near(sampleNativeHaze(haze,{x:0,y:0,z:0},{x:0,y:0,z:0}).amount,0);
});
test('Native altitude haze follows its integrated exponential density and remains finite for horizontal rays',()=>{
  const haze=nativeHazeParameters(zone('haze',undefined,{haze:{hazeRange:100,hazeAltitudeEffect:true,hazeBaseRef:10,hazeCeiling:210}}));
  const elevated=sampleNativeHaze(haze,{x:0,y:210,z:0},{x:100,y:210,z:0});
  near(elevated.amount,1-Math.exp(Math.log(.05)*.05));
  const rising=sampleNativeHaze(haze,{x:0,y:10,z:0},{x:0,y:210,z:0});
  // Integral over a 200 m vertical segment: density falls from 1 to .05.
  near(rising.amount,1-Math.exp(-1.9));
  const reverse=nativeHazeParameters(zone('inverted',undefined,{haze:{hazeAltitudeEffect:true,hazeBaseRef:200,hazeCeiling:0}}));
  assert(reverse.heightFactor<0);
});
test('Native glare half-angle and sky-distance background multiplier use actual authored properties',()=>{
  const haze=nativeHazeParameters(zone('haze',undefined,{haze:{hazeEnableGlare:true,hazeColor:{red:0,green:0,blue:0},hazeGlareColor:{red:255,green:0,blue:0},hazeGlareAngle:20,hazeBackgroundBlend:.25}}));
  const ray={x:100*Math.sin(Math.PI/9),y:100*Math.cos(Math.PI/9),z:0};
  near(sampleNativeHaze(haze,{x:0,y:0,z:0},ray).color.x,.5);
  near(sampleNativeHaze(haze,{x:0,y:0,z:0},{x:32000,y:0,z:0}).amount,.25);
  near(sampleNativeHaze(haze,{x:0,y:0,z:0},{x:27000,y:0,z:0}).amount,1);
});
test('Native key-light attenuation is separate from haze color and uses the protected shallow-light denominator',()=>{
  const haze=nativeHazeParameters(zone('haze',undefined,{haze:{hazeAttenuateKeyLight:true,hazeKeyLightRange:1000,hazeKeyLightAltitude:200}}));
  const actual=nativeKeyLightAttenuation(haze,{x:0,y:0,z:0},{x:1,y:0,z:0});
  assert(actual>=0&&actual<1);assert(Number.isFinite(actual));
  haze.attenuateKeyLight=false;assert.equal(nativeKeyLightAttenuation(haze,{x:0,y:0,z:0},{x:1,y:0,z:0}),1);
});
test('Native sky orientation negates the Zone rotation; texture tint multiplies and black is neutral only with a map',()=>{
  const q=new Quaternion().setFromAxisAngle(new Vector3(0,1,0),Math.PI/2);
  const direction=nativeSkyDirection({x:1,y:0,z:0},{x:q.x,y:q.y,z:q.z,w:q.w});near(direction.z,1);near(direction.x,0);
  assert.deepEqual(nativeSkyColor({x:.3,y:.4,z:.5},{x:0,y:0,z:0}).toArray(),[.3,.4,.5]);
  assert.deepEqual(nativeSkyColor(undefined,{x:0,y:0,z:0}).toArray(),[0,0,0]);
  assert.deepEqual(nativeSkyColor({x:.3,y:.4,z:.5},{x:.5,y:1,z:.2}).toArray(),[.15,.4,.1]);
});
test('Native sky atlas detection preserves face order and distinct cross orientation flips',()=>{
  assert.equal(nativeSkyLayout(2048,1024).kind,'equirectangular');
  assert.deepEqual(nativeSkyLayout(4,24).faces?.map(face=>[face.column,face.row]),[[0,0],[0,1],[0,2],[0,3],[0,4],[0,5]]);
  assert.deepEqual(nativeSkyLayout(16,12).faces?.map(face=>[face.column,face.row]),[[2,1],[0,1],[1,0],[1,2],[3,1],[1,1]]);
  assert.deepEqual(nativeSkyLayout(12,16).faces?.[4],{column:1,row:3,flipX:false,flipY:true});
  assert.throws(()=>nativeSkyLayout(100,100),/layout/);assert.throws(()=>nativeSkyLayout(100000,50000),/dimensions/);
});
test('Native light defaults, rotated direction and independent ambient-map fallback preserve real properties',()=>{
  const q=new Quaternion().setFromAxisAngle(new Vector3(0,1,0),Math.PI/2);
  const entity=zone('lighting',undefined,{rotation:{x:q.x,y:q.y,z:q.z,w:q.w},keyLight:{direction:{x:0,y:0,z:1},intensity:3,color:{red:255,green:128,blue:0}},ambientLight:{ambientIntensity:.75},skybox:{url:'atp:/sky.png'}}),entities=scene(entity);
  const key=nativeZoneKeyLight(entity,entities);near(key.direction.x,1);near(key.direction.z,0);assert.equal(key.intensity,3);assert.equal(key.castShadows,false);
  const ambient=nativeZoneAmbientLight(entity,entities);assert.equal(ambient.url,'atp:/sky.png');assert.equal(ambient.intensity,.75);assert.deepEqual(ambient.color.toArray(),[0,0,0]);
  entity.ambientLight={ambientURL:'https://assets.invalid/actual-light.hdr'};assert.equal(nativeZoneAmbientLight(entity,entities).url,'https://assets.invalid/actual-light.hdr');
});

test('Native SH projection integrates a uniform linear cube to the analytic constant irradiance',async()=>{
  const sh=await integrateNativeAmbientSH({size:32,readPixel:(_face,_x,_y,out)=>out.set(.25,.5,1)});
  near(sh[0].x,.25*.28209479177*4*Math.PI,1e-9);
  for(const coefficient of sh.slice(1))assert(coefficient.length()<1e-9,'Isotropic input must cancel every directional band');
  const expected=.886227*.28209479177*4*Math.PI;
  const evaluated=evaluateNativeAmbientSH(sh,{x:0,y:1,z:0});near(evaluated.z,expected,1e-9);near(evaluated.x,expected*.25,1e-9);
});
test('Native SH cube orientation and signed basis preserve a one-face analytic impulse',async()=>{
  // A one-pixel +X storage face points towards -X in native Texture.cpp.
  const sh=await integrateNativeAmbientSH({size:1,readPixel:(face,_x,_y,out)=>out.set(face===0?1:0,0,0)});
  near(sh[3].x,.4886025119*4*Math.PI/6,1e-10);near(sh[1].x,0);near(sh[2].x,0);
  assert.deepEqual(nativeSHCubeDirection(0,0,0,1).toArray(),[-1,0,0]);
  assert.deepEqual(nativeSHCubeDirection(2,0,0,1).toArray(),[0,-1,0]);
  assert.deepEqual(nativeSHCubeDirection(4,0,0,1).toArray(),[0,0,1]);
});
test('Ambient constant color, textured black-neutral tint and inverse Zone rotation remain independent',()=>{
  const light=nativeZoneAmbientLight(zone('ambient',undefined,{ambientLight:{ambientColor:{red:128,green:0,blue:0},ambientIntensity:2}}),new Map());
  assert.deepEqual(sampleNativeAmbient(light,{x:0,y:1,z:0}).toArray(),[256/255,0,0]);
  light.url='atp:/actual.hdr';light.color.set(0,0,0);light.rotation.setFromAxisAngle(new Vector3(0,0,1),Math.PI/2);
  const impulse=Array.from({length:9},()=>new Vector3());impulse[3].set(1,0,0);
  near(sampleNativeAmbient(light,{x:0,y:1,z:0},impulse).x,4*.511664);
  assert.deepEqual(sampleNativeAmbient({...light,url:''},{x:0,y:1,z:0}).toArray(),[0,0,0],'Black without a map remains authored black');
});
test('Native SH work rejects unbounded/nonfinite input and stops during yielded work on cancellation',async()=>{
  await assert.rejects(integrateNativeAmbientSH({size:4096,readPixel:()=>{}}),/budget/);
  await assert.rejects(integrateNativeAmbientSH({size:1,readPixel:(_f,_x,_y,out)=>out.set(NaN,0,0)}),/non-finite/);
  const controller=new AbortController();let read=0;
  setTimeout(()=>controller.abort(new Error('revoked authority')),0);
  await assert.rejects(integrateNativeAmbientSH({size:256,readPixel:(_f,_x,_y,out)=>{read++;out.set(1,1,1);}},{signal:controller.signal}),/revoked authority/);
  assert(read>0&&read<256*256*6,'Cancellation must stop actual extraction before all faces are traversed');
});
test('Haze shader trust requires the exact private wrapper and its reviewed parent; restore never clobbers a foreign hook',()=>{
  const material=new MeshPhongMaterial(),parentCompile=material.onBeforeCompile,parentCache=material.customProgramCacheKey;
  material.userData.nativeHaze=true;assert(!hasNativeHazeShader(material,()=>true));
  const uniforms=createNativeHazeUniforms();installNativeZoneHaze(material,uniforms);
  assert(hasNativeHazeShader(material,(compile,cache)=>compile===parentCompile&&cache===parentCache));
  assert(!hasNativeHazeShader(material,()=>false),'A wrapper cannot make an untrusted parent safe');
  const installed=material.onBeforeCompile;installNativeZoneHaze(material,uniforms);assert.equal(material.onBeforeCompile,installed);
  assert.throws(()=>installNativeZoneHaze(material,createNativeHazeUniforms()),/another native Zone environment/);
  assert(restoreNativeHazeShader(material));assert.equal(material.onBeforeCompile,parentCompile);assert.equal(material.customProgramCacheKey,parentCache);
  installNativeZoneHaze(material,createNativeHazeUniforms());const foreign=()=>{};material.onBeforeCompile=foreign;
  assert(!hasNativeHazeShader(material,()=>true));assert(!restoreNativeHazeShader(material));assert.equal(material.onBeforeCompile,foreign);
  assert.throws(()=>installNativeZoneHaze(material,createNativeHazeUniforms()),/changed/);
});
test('Haze composes the parent once, uses post-skinning/projected position, attenuates only directional sources and precedes tone mapping',()=>{
  const material=new MeshPhongMaterial();let parentCalls=0;
  material.onBeforeCompile=()=>{parentCalls++;};material.customProgramCacheKey=()=> 'reviewed-native-alpha';
  installNativeZoneHaze(material,createNativeHazeUniforms());
  const shader={uniforms:{},vertexShader:ShaderLib.phong.vertexShader,fragmentShader:ShaderLib.phong.fragmentShader} as WebGLProgramParametersWithUniforms;
  material.onBeforeCompile(shader,{} as WebGLRenderer);assert.equal(parentCalls,1);
  assert(shader.vertexShader.includes('overteHazeWorldPosition=(nativeHazeCameraWorld*mvPosition).xyz'));
  assert(shader.fragmentShader.indexOf('gl_FragColor.rgb=mix')<shader.fragmentShader.indexOf('#include <tonemapping_fragment>'));
  assert(shader.fragmentShader.includes('getPointLightInfo( pointLight, geometryPosition, directLight );'));
  assert(shader.fragmentShader.includes('getDirectionalLightInfo( directionalLight, directLight );\nif(dot'));
  assert.equal(material.customProgramCacheKey(),'reviewed-native-alpha|overte-native-zone-haze-v1');
});
const tga=(width:number,height:number):Uint8Array<ArrayBuffer>=>{const data=new Uint8Array(18+width*height*3);data[2]=2;data[12]=width&255;data[13]=width>>8;data[14]=height&255;data[15]=height>>8;data[16]=24;data[17]=32;for(let i=18;i<data.length;i+=3)data[i+2]=255;return data;};
const withFetch=async(run:()=>Promise<void>,mock:typeof fetch)=>{const previous=globalThis.fetch;globalThis.fetch=mock;try{await run();}finally{globalThis.fetch=previous;}};
test('Native sky texmeta follows its actual ATP-relative original and cube disposal frees each owned decoded face',async()=>{
  const paths:string[]=[];
  await withFetch(async()=>{
    const texture=await loadNativeSkyTexture('atp:/sky/actual.texmeta.json',source=>{paths.push(source);return 'https://gateway.invalid/asset';});
    assert(texture instanceof CubeTexture);assert.deepEqual(paths,['atp:/sky/actual.texmeta.json','atp:/sky/color.tga']);
    let disposed=0;for(const face of texture.images)assert(face instanceof DataTexture),face.addEventListener('dispose',()=>disposed++);
    texture.dispose();assert.equal(disposed,6);
  },async()=>paths.length===1?new Response(JSON.stringify({original:'color.tga'})):new Response(tga(1,6)));
});
test('A stalled sky stream is cancelled at its deadline and oversized image headers fail before decoding',async()=>{
  let cancelled=false;
  await withFetch(async()=>{await assert.rejects(loadNativeSkyTexture('atp:/sky.tga',source=>source,{timeoutMs:10}),/deadline/);assert(cancelled);},async()=>new Response(new ReadableStream({cancel(){cancelled=true;}})));
  const header=tga(1,1).slice(0,18);header[12]=255;header[13]=255;header[14]=255;header[15]=255;
  await withFetch(async()=>{await assert.rejects(loadNativeSkyTexture('atp:/oversized.tga',source=>source),/dimensions/);},async()=>new Response(header));
});
test('Closing a Zone environment cancels pending loads, restores original fallback visibility and removes owned scene resources',async()=>{
  const previousFetch=globalThis.fetch;let aborted=0;globalThis.fetch=async(_url,options)=>new Promise((_resolve,reject)=>{options?.signal?.addEventListener('abort',()=>{aborted++;reject(options.signal?.reason);},{once:true});});
  try{
    const scene=new Scene(),visible=new DirectionalLight(),hidden=new AmbientLight();hidden.visible=false;scene.add(visible,hidden);
    const effects=new NativeZoneEnvironment(scene,{resolveAsset:source=>source,onStatus:()=>{},fallbackKeyLights:[visible],fallbackAmbientLights:[hidden]});
    const material=new MeshPhongMaterial(),original=material.onBeforeCompile;effects.attachMaterial(material);
    const entity=zone('actual',undefined,{keyLightMode:'enabled',keyLight:{castShadows:true},skyboxMode:'enabled',skybox:{url:'https://assets.invalid/actual.tga'}});
    effects.setEntities(new Map([[entity.id,entity]]));effects.update({x:0,y:0,z:0},new PerspectiveCamera());
    assert.equal(effects.keyLight.castShadow,false,'No unvalidated native-to-Three shadow bias conversion');
    assert.equal(effects.keyLight.visible,true);assert.equal(visible.visible,true);assert.equal(visible.intensity,0,'Disabling a fallback preserves the scene light count');
    effects.dispose();effects.dispose();await new Promise(resolve=>setTimeout(resolve,0));
    assert.equal(material.onBeforeCompile,original);assert.equal(aborted,1);assert.equal(visible.visible,true);assert.equal(hidden.visible,false);assert.deepEqual(scene.children,[visible,hidden]);
  }finally{globalThis.fetch=previousFetch;}
});

test('The actual decoder parses native TGA pixels and rejects oversized headers before pixel allocation',()=>{
  const image=decodeNativeSky('tga',tga(2,1).buffer);assert.equal(image.width,2);assert.equal(image.height,1);
  assert.deepEqual([...image.data],[255,0,0,255,255,0,0,255]);
  const header=tga(1,1).slice(0,18);header[12]=255;header[13]=255;header[14]=255;header[15]=255;
  assert.throws(()=>decodeNativeSky('tga',header.buffer),/pixel budget/);
});
test('Large or highly compressed HDR/TGA decoding owns and terminates a worker on completion, failure and revocation',async()=>{
  const previous=globalThis.Worker;const workers:FakeWorker[]=[];
  class FakeWorker {
    onmessage:((event:MessageEvent)=>void)|null=null;onerror:(()=>void)|null=null;terminated=0;posted=0;
    constructor(){workers.push(this);}
    terminate(){this.terminated++;}
    postMessage(){this.posted++;}
  }
  globalThis.Worker=FakeWorker as unknown as typeof Worker;
  try{
    // Only a tiny RLE-capable header is needed: dimensions, not compressed
    // source length, determine whether parsing could monopolize the UI thread.
    const header=tga(1,1).slice(0,18);header[12]=0;header[13]=2;header[14]=0;header[15]=1;
    const signal=new AbortController();
    const complete=decodeNativeSkyBounded('tga',header.buffer.slice(0),signal.signal);
    assert.equal(workers[0].posted,1);
    workers[0].onmessage!({data:{image:{width:512,height:256,data:new Uint8Array(512*256*4),type:UnsignedByteType}}} as MessageEvent);
    assert.equal((await complete).width,512);assert.equal(workers[0].terminated,1);
    const cancel=decodeNativeSkyBounded('tga',header.buffer.slice(0),signal.signal);signal.abort(new Error('session revoked'));
    await assert.rejects(cancel,/session revoked/);assert.equal(workers[1].terminated,1);
    const failure=decodeNativeSkyBounded('tga',header.buffer.slice(0),new AbortController().signal);workers[2].onerror!();
    await assert.rejects(failure,/worker failed/);assert.equal(workers[2].terminated,1);
    const invalid=decodeNativeSkyBounded('tga',header.buffer.slice(0),new AbortController().signal);
    workers[3].onmessage!({data:{image:{width:999999,height:999999,data:new Uint8Array(4)}}} as MessageEvent);
    await assert.rejects(invalid,/oversized pixels/);assert.equal(workers[3].terminated,1);
  }finally{globalThis.Worker=previous;}
});
test('Late browser bitmap completion after revocation is closed and cannot become a displayed sky',async()=>{
  const previous=globalThis.createImageBitmap;let complete!:(image:ImageBitmap)=>void,closed=0;
  globalThis.createImageBitmap=(()=>new Promise<ImageBitmap>(resolve=>{complete=resolve;})) as typeof createImageBitmap;
  try{
    await withFetch(async()=>{
      const controller=new AbortController(),pending=loadNativeSkyTexture('atp:/actual.png',source=>source,{signal:controller.signal});
      while(!complete)await new Promise(resolve=>setTimeout(resolve,0));
      controller.abort(new Error('closed session'));await assert.rejects(pending,/closed session/);
      complete({width:2,height:1,close:()=>closed++} as ImageBitmap);await new Promise(resolve=>setTimeout(resolve,0));assert.equal(closed,1);
    },async()=>new Response(new Uint8Array([1,2,3])));
  }finally{globalThis.createImageBitmap=previous;}
});
test('Sky HTTP error bodies obey the same deadline while preserving readable authorized gateway errors',async()=>{
  await withFetch(async()=>{await assert.rejects(loadNativeSkyTexture('atp:/blocked.tga',source=>source),/HTTP 502: Asset origin is not enabled/);},async()=>new Response(JSON.stringify({error:'Asset origin is not enabled'}),{status:502,headers:{'content-type':'application/json'}}));
  await withFetch(async()=>{await assert.rejects(loadNativeSkyTexture('atp:/stalled.tga',source=>source,{timeoutMs:10}),/deadline/);},async()=>new Response(new ReadableStream(),{status:502,headers:{'content-type':'application/json'}}));
});
