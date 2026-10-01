// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual public Three/GPU fidelity. Candidate remains default-off in World.
import * as THREE from 'three';
import {prepareGraphicsYielding} from '../src/graphics-warmup';
import {GraphicsWarmupOwner} from '../src/graphics-warmup-owner';
import {WorkerTaskYield} from '../src/worker-task-yield';
import {applyNativeMaterialAlpha,hasNativeAlphaShader} from '../src/native-alpha-material';
import {applyNativeRenderState} from '../src/native-render-state';
import {warmupNativeAlphaContract} from './graphics-warmup-native-alpha';

async function authoredScene(){
 const scene=new THREE.Scene(),root=new THREE.Group();scene.add(root);scene.background=new THREE.Color(.025,.035,.045);
 const camera=new THREE.OrthographicCamera(-3,3,3,-3,.1,30);camera.position.z=8;
 scene.add(new THREE.AmbientLight(0xffffff,.5));const sun=new THREE.DirectionalLight(0xffffff,2);sun.position.set(2,3,6);sun.castShadow=true;sun.shadow.mapSize.set(64,64);scene.add(sun);
 // Target-scene visible/excluded layers and root-local hidden light must retain
 // exact original public compile light collection; no copied/reparented light.
 const point=new THREE.PointLight(0x68b4ef,.3,10);point.position.set(-2,2,3);scene.add(point);
 const excluded=new THREE.PointLight(0xff0000,4,20);excluded.layers.set(3);scene.add(excluded);
 const hidden=new THREE.SpotLight(0x00ff00,3,20);hidden.visible=false;root.add(hidden);
 const geometry=new THREE.BoxGeometry(.7,.7,.3),plane=new THREE.PlaneGeometry(.7,.7);
 const alpha=new THREE.DataTexture(new Uint8Array([255,255,255,0,255,255,255,255,255,255,255,255,255,255,255,0]),2,2);
 alpha.magFilter=alpha.minFilter=THREE.NearestFilter;alpha.needsUpdate=true;
 const opaque=new THREE.MeshStandardMaterial({color:0x91ca44,roughness:.65}),mask=new THREE.MeshStandardMaterial({color:0xeb6148,map:alpha});
 const blend=new THREE.MeshPhongMaterial({color:0x689cfa,map:alpha,opacity:.55});
 await applyNativeMaterialAlpha(mask,{useAlpha:true,mode:'OPACITY_MAP_MASK',cutoff:.375});await applyNativeMaterialAlpha(blend,{useAlpha:true,mode:'OPACITY_MAP_BLEND'});
 for(const material of [opaque,mask,blend])applyNativeRenderState(material,{cullFaceMode:'CULL_NONE'});
 const owned=[opaque,mask,blend],renderables:THREE.Object3D[]=[];
 for(let index=0;index<9;index++){
  const mesh=new THREE.Mesh(index%3?plane:geometry,owned[index%3]);mesh.position.set((index%3-1)*1.5,(Math.floor(index/3)-1)*1.5,0);
  mesh.castShadow=true;mesh.receiveShadow=true;root.add(mesh);renderables.push(mesh);
 }
 // This material is shared across ordinary, skinned, instance, morph and
 // multi-material geometry variants. One material-currentProgram is not every
 // original binding; prototype views must preserve every such object input.
 const skinGeometry=geometry.clone(),count=skinGeometry.getAttribute('position').count;
 skinGeometry.setAttribute('skinIndex',new THREE.Uint16BufferAttribute(new Uint16Array(count*4),4));const weights=new Float32Array(count*4);for(let i=0;i<count;i++)weights[i*4]=1;
 skinGeometry.setAttribute('skinWeight',new THREE.Float32BufferAttribute(weights,4));
 const bone=new THREE.Bone(),skin=new THREE.SkinnedMesh(skinGeometry,opaque);skin.add(bone);skin.bind(new THREE.Skeleton([bone]));skin.position.set(-2.4,2.4,.5);root.add(skin);renderables.push(skin);
 const instances=new THREE.InstancedMesh(geometry,opaque,2);instances.setMatrixAt(0,new THREE.Matrix4().makeTranslation(2.2,2.4,0));instances.setMatrixAt(1,new THREE.Matrix4().makeTranslation(2.8,2.4,0));root.add(instances);renderables.push(instances);
 const morphGeometry=geometry.clone(),targetPositions=new Float32Array(morphGeometry.getAttribute('position').array);for(let i=1;i<targetPositions.length;i+=3)targetPositions[i]*=1.3;
 morphGeometry.morphAttributes.position=[new THREE.Float32BufferAttribute(targetPositions,3)];const morph=new THREE.Mesh(morphGeometry,opaque);morph.updateMorphTargets();morph.morphTargetInfluences![0]=.6;morph.position.set(0,2.4,0);root.add(morph);renderables.push(morph);
 const groups=geometry.clone();groups.clearGroups();groups.addGroup(0,18,0);groups.addGroup(18,18,1);
 const array=[opaque,mask],multi=new THREE.Mesh(groups,array);multi.position.set(-2.4,-2.4,.1);root.add(multi);renderables.push(multi);
 scene.updateMatrixWorld(true);
 const versions=owned.map(material=>material.version),hooks=owned.map(material=>[material.onBeforeCompile,material.customProgramCacheKey]);
 const originals=renderables.map(object=>({object,parent:object.parent,material:(object as THREE.Mesh).material,geometry:(object as THREE.Mesh).geometry,matrix:object.matrix.clone(),matrixWorld:object.matrixWorld.clone()}));
 const attributes=[...new Set(originals.map(value=>value.geometry))].map(value=>({geometry:value,attributes:Object.entries(value.attributes).map(([name,attribute])=>({name,array:Array.from(attribute.array)})),index:value.index?Array.from(value.index.array):null,groups:value.groups.map(group=>({...group}))}));
 const unchangedWarmInputs=()=>originals.every(v=>v.object.parent===v.parent&&(v.object as THREE.Mesh).material===v.material&&(v.object as THREE.Mesh).geometry===v.geometry&&v.object.matrix.equals(v.matrix)&&v.object.matrixWorld.equals(v.matrixWorld))&&
  attributes.every(v=>v.attributes.every(a=>Array.from(v.geometry.getAttribute(a.name).array).every((n,i)=>n===a.array[i]))&&JSON.stringify(v.geometry.groups)===JSON.stringify(v.groups)&&JSON.stringify(v.geometry.index?Array.from(v.geometry.index.array):null)===JSON.stringify(v.index));
 const renderer=new THREE.WebGLRenderer({antialias:false});renderer.setPixelRatio(1);renderer.setSize(96,96);renderer.toneMapping=THREE.NoToneMapping;renderer.shadowMap.enabled=true;
 const gl=renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 required');
 // Diagnostic-only GL identity accounting. Delegate every actual driver call;
 // do not delete unknown handles, adjust memory counters, or alter rendering.
 const createTexture=gl.createTexture,deleteTexture=gl.deleteTexture;
 const textureIds=new Map<WebGLTexture,number>(),aliveTextures=new Set<WebGLTexture>();let createdTextures=0,deletedTextures=0;
 gl.createTexture=function(){const value=createTexture.call(gl);if(value){textureIds.set(value,++createdTextures);aliveTextures.add(value);}return value;};
 gl.deleteTexture=function(value){if(value&&aliveTextures.delete(value))deletedTextures++;return deleteTexture.call(gl,value);};
 const textureHandle=(texture:THREE.Texture|null|undefined)=>texture?(renderer.properties.get(texture) as {__webglTexture?:WebGLTexture}).__webglTexture:undefined;

 const target=new THREE.WebGLRenderTarget(96,96);target.texture.colorSpace=THREE.LinearSRGBColorSpace;renderer.setRenderTarget(target);
 function animate(frame:number){
  camera.position.x=.012*frame;camera.position.y=.004*frame;camera.lookAt(0,0,0);camera.updateProjectionMatrix();
  bone.rotation.z=.013*frame;skin.updateMatrixWorld(true);morph.morphTargetInfluences![0]=.25+.02*frame;
  instances.setMatrixAt(1,new THREE.Matrix4().makeRotationZ(.009*frame).setPosition(2.8,2.4+.006*frame,0));instances.instanceMatrix.needsUpdate=true;
 }
 function draw(){renderer.render(scene,camera);const output=new Uint8Array(96*96*4);renderer.readRenderTargetPixels(target,0,0,96,96,output);return {output,calls:renderer.info.render.calls,triangles:renderer.info.render.triangles};}
 const ownedGeometry=[...new Set(originals.map(v=>v.geometry))];
 const lifecycle={closed:false,geometryDisposals:0,expectedGeometryDisposals:ownedGeometry.length,materialDisposals:0,expectedMaterialDisposals:owned.length,
  targetDisposals:0,geometriesAfterClose:-1,texturesAfterClose:-1,textureReleaseSteps:[] as {stage:string,textures:number,remaining:number[]}[],textureIdentity:{created:0,deleted:0,bindings:[] as {name:string,id:number|null}[],dfg:null as null|{name:string,width:number,height:number,isDataTexture:boolean}}};
 for(const value of ownedGeometry)value.addEventListener('dispose',()=>lifecycle.geometryDisposals++);
 for(const value of owned)value.addEventListener('dispose',()=>lifecycle.materialDisposals++);target.addEventListener('dispose',()=>lifecycle.targetDisposals++);
 let borrowedDFG:THREE.DataTexture|undefined,rendererClosed=false;
 const released=(stage:string)=>lifecycle.textureReleaseSteps.push({stage,textures:renderer.info.memory.textures,remaining:[...aliveTextures].map(value=>textureIds.get(value)!)});
 function releaseResources(){if(lifecycle.closed)return undefined;lifecycle.closed=true;
  // Preserve actual zero-resource assertions. Record each release boundary so
  // a driver/Three-owned texture is identified rather than counted away.
  // Read actual already-bound uniforms before material disposal removes their
  // properties. This inspection is restricted to the authored fixture.
  const dfg=(renderer.properties.get(opaque) as {uniforms?:{dfgLUT?:{value?:THREE.DataTexture}}}).uniforms?.dfgLUT?.value;borrowedDFG=dfg;
  if(dfg)lifecycle.textureIdentity.dfg={name:dfg.name,width:dfg.image.width,height:dfg.image.height,isDataTexture:dfg.isDataTexture};
  for(const [name,texture] of [['target',target.texture],['alpha',alpha],['bone',skin.skeleton.boneTexture],['shadow-color',sun.shadow.map?.texture],['shadow-depth',sun.shadow.map?.depthTexture],['pbr-dfg',dfg]] as const){
   const handle=textureHandle(texture);lifecycle.textureIdentity.bindings.push({name,id:handle?textureIds.get(handle)??null:null});
  }
  released('before');renderer.setRenderTarget(null);target.dispose();released('target');
  for(const material of owned)material.dispose();released('materials');
  for(const g of ownedGeometry)g.dispose();released('geometry-and-morph');
  skin.skeleton.dispose();released('skeleton');instances.dispose();released('instances');
  alpha.dispose();released('alpha');sun.shadow.dispose();released('shadow');return borrowedDFG;
 }
 function finalizeRenderer(){if(rendererClosed)return;rendererClosed=true;released('shared-dfg');renderer.dispose();released('renderer');
  lifecycle.geometriesAfterClose=renderer.info.memory.geometries;lifecycle.texturesAfterClose=renderer.info.memory.textures;lifecycle.textureIdentity.created=createdTextures;lifecycle.textureIdentity.deleted=deletedTextures;gl.createTexture=createTexture;gl.deleteTexture=deleteTexture;renderer.forceContextLoss();}
 const getDFG=()=>(renderer.properties.get(opaque) as {uniforms?:{dfgLUT?:{value?:THREE.DataTexture}}}).uniforms?.dfgLUT?.value;
 const lease={releaseResources,finalizeRenderer};const close=()=>{if(!rendererClosed)closeWarmupFixtureResources([lease]);};
 return {renderer,scene,root,camera,owned,sun,mask,blend,versions,hooks,originals,unchangedWarmInputs,animate,draw,close,lifecycle,lease,getDFG};
}
/** Test-only teardown of a blank authored page's complete renderer set.
 * Three r186's module-global DFG lookup is shared by those renderers. Release
 * that exact already-bound Texture once, before renderer.dispose erases the
 * property registries needed by its actual texture-disposal listeners. This
 * must never be used to dispose a borrowed global in a live BrowserWorld. */
export function closeWarmupFixtureResources(leases:readonly {releaseResources():THREE.DataTexture|undefined;finalizeRenderer():void}[]){
 if(leases.length<1||leases.length>2)throw Error('Invalid authored renderer ownership bound');
 const textures=new Set<THREE.DataTexture>();let failure:unknown;
 for(const lease of leases){try{const texture=lease.releaseResources();if(texture)textures.add(texture);}catch(error){failure??=error;}}
 try{
  if(failure!==undefined)throw failure;
  if(textures.size>1)throw Error('Authored renderer set does not share the same Three DFG lookup');
  for(const texture of textures){
   if(!texture.isDataTexture||texture.name!=='DFG_LUT'||texture.image.width!==16||texture.image.height!==16||texture.format!==THREE.RGFormat||texture.type!==THREE.HalfFloatType)
    throw Error('Unrecognized borrowed renderer texture must not be disposed');
   texture.dispose();
  }
 }catch(error){failure??=error;}
 finally{for(const lease of leases){try{lease.finalizeRenderer();}catch(error){failure??=error;}}}
 if(failure!==undefined)throw failure;
}
function rgbaDifference(a:Uint8Array,b:Uint8Array){let maximum=0,changed=0;for(let i=0;i<a.length;i++){const delta=Math.abs(a[i]-b[i]);maximum=Math.max(maximum,delta);if(delta)changed++;}return {maximum,changed};}
export async function auditGraphicsWarmup(){
 // Independent graphs also own independent shadow/skin/texture resources; a
 // shared cold reference graph could accidentally reuse the candidate's state.
 const candidate=await authoredScene(),reference=await authoredScene();
 try{
  const nativeAlphaInitiallyCorrect=warmupNativeAlphaContract(candidate.mask,candidate.blend)&&warmupNativeAlphaContract(reference.mask,reference.blend);
  const nativeAlphaHooksBefore={mask:hasNativeAlphaShader(candidate.mask),blend:hasNativeAlphaShader(candidate.blend)};
  if(!nativeAlphaInitiallyCorrect)throw Error('Authored native MASK/BLEND setup is invalid before shader preparation');
  let finalRootExact=false,finalCameraExact=false,finalSceneExact=false;const publicCompiler={compile:(root:THREE.Object3D,camera:THREE.Camera,scene:THREE.Scene)=>candidate.renderer.compile(root,camera,scene),
   compileAsync:(root:THREE.Object3D,camera:THREE.Camera,scene:THREE.Scene)=>{finalRootExact=root===candidate.root;finalCameraExact=camera===candidate.camera;finalSceneExact=scene===candidate.scene;return candidate.renderer.compileAsync(root,camera,scene);}};
  const statistics=await prepareGraphicsYielding(publicCompiler,candidate.camera,candidate.scene,candidate.root);
  await reference.renderer.compileAsync(reference.root,reference.camera,reference.scene);
  const warmInputs=candidate.unchangedWarmInputs();let maximum=0,changed=0,changedAnimationComponents=0,previous:Uint8Array|undefined;
  let callsEqual=true,trianglesEqual=true,coldProgramCountsEqual=true,stableCalls=true,stablePrograms=true;const frames=[];
  let initialPrograms:number|undefined,initialCalls:number|undefined;
  for(let frame=0;frame<21;frame++){
   candidate.animate(frame);reference.animate(frame);const a=candidate.draw(),b=reference.draw(),difference=rgbaDifference(a.output,b.output);
   maximum=Math.max(maximum,difference.maximum);changed+=difference.changed;callsEqual&&=a.calls===b.calls;trianglesEqual&&=a.triangles===b.triangles;
   const programs=candidate.renderer.info.programs?.length;initialPrograms??=programs;initialCalls??=a.calls;
   stablePrograms&&=programs===initialPrograms;stableCalls&&=a.calls===initialCalls;coldProgramCountsEqual&&=programs===reference.renderer.info.programs?.length;
   if(previous)changedAnimationComponents+=rgbaDifference(previous,a.output).changed;previous=a.output;
   frames.push({frame,maximum:difference.maximum,changed:difference.changed,calls:a.calls,directCalls:b.calls,triangles:a.triangles,directTriangles:b.triangles,programs,directPrograms:reference.renderer.info.programs?.length});
  }
  const sharedRendererDFG=!!candidate.getDFG()&&candidate.getDFG()===reference.getDFG();
  if(!sharedRendererDFG)throw Error('Actual independent renderers must bind the same Three-owned DFG lookup');
  return {webgl2:true,sharedRendererDFG,cleanup:[candidate.lifecycle,reference.lifecycle],statistics,maximum,changed,components:96*96*4,frames,changedAnimationComponents,nonBackground:previous!.filter((value,index)=>index%4!==3&&value>80).length,
   finalRootExact,finalCameraExact,finalSceneExact,warmInputs,callsEqual,trianglesEqual,stableCalls,stablePrograms,coldProgramCountsEqual,
   stableVersions:candidate.owned.every((material,index)=>material.version===candidate.versions[index]),
   retainedHooks:candidate.owned.every((material,index)=>material.onBeforeCompile===candidate.hooks[index][0]&&material.customProgramCacheKey===candidate.hooks[index][1]),
   nativeAlphaInitiallyCorrect,nativeAlphaHooksBefore,
   nativeAlphaHooksAfter:{mask:hasNativeAlphaShader(candidate.mask),blend:hasNativeAlphaShader(candidate.blend)},
   nativeAlphaRetained:warmupNativeAlphaContract(candidate.mask,candidate.blend)&&warmupNativeAlphaContract(reference.mask,reference.blend),actualShadowMap:!!candidate.sun.shadow.map,
   retainedInputs:candidate.originals.every(v=>v.object.parent===v.parent&&(v.object as THREE.Mesh).material===v.material&&(v.object as THREE.Mesh).geometry===v.geometry)};
 }finally{closeWarmupFixtureResources([candidate.lease,reference.lease]);}
}

/** Actual GPU public compile submissions, real owned task yields and authority
 * revocation; no mock renderer, fake ready flag or delayed private GL API. */
export async function auditGraphicsWarmupCancellation(){
 const data=await authoredScene(),world=new AbortController(),owner=new GraphicsWarmupOwner(world.signal);
 let submitted=0,finalCalls=0,yields=0,closed=0;const bound={value:true};
 const compiler={compile:(root:THREE.Object3D,camera:THREE.Camera,scene:THREE.Scene)=>{submitted++;return data.renderer.compile(root,camera,scene);},
  compileAsync:(root:THREE.Object3D,camera:THREE.Camera,scene:THREE.Scene)=>{finalCalls++;return data.renderer.compileAsync(root,camera,scene);}};
 data.root.userData.shadersReady=false;let publishedReady=0;
 let failureName='';const promise=owner.run(data.root,()=>bound.value,async(signal,current)=>prepareGraphicsYielding(compiler,data.camera,data.scene,data.root,{signal,isCurrent:current,
  taskFactory:()=>{const task=new WorkerTaskYield({signal});return {async yield(){yields++;await task.yield();bound.value=false;owner.cancel(data.root);},close(){closed++;task.close();}};}})).then(value=>{publishedReady++;data.root.userData.shadersReady=true;return value;});
 try{await promise;}catch(error){failureName=(error as Error).name;}
 try{
  await new Promise(resolve=>setTimeout(resolve,30));const settledSubmitted=submitted;
  // Cleanup before disposing actual geometry/GL; no late next slice, final
  // exact-root compile, or success should occur after authority was revoked.
  owner.cancel(data.root);world.abort();await new Promise(resolve=>setTimeout(resolve,30));
  return {webgl2:true,cleanup:data.lifecycle,failureName,submitted,settledSubmitted,finalCalls,yields,closed,publishedReady,warmInputs:data.unchangedWarmInputs(),shadersReady:data.root.userData.shadersReady};
 }finally{data.close();}
}
