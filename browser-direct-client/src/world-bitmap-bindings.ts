// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {Material,Mesh,MeshBasicMaterial,MeshLambertMaterial,MeshPhongMaterial,MeshStandardMaterial,MeshPhysicalMaterial,Object3D,Texture,NoColorSpace,SRGBColorSpace,LinearSRGBColorSpace} from 'three';
import {hasNativeAlphaShader} from './native-alpha-material';
import {hasNativeZeroLightShader} from './native-zero-lights';
import {ModelResources} from './model-resources';
import {WorldBitmapUpload,SessionUploadTexture,BitmapUploadCapacityError,BitmapUploadUnsupportedVariantError} from './world-bitmap-upload';
interface Binding{mesh:Mesh;slot:number|null;field:string;material:Material;texture:Texture;version:number;signature:unknown[]}
export class BitmapBindingsCapacityError extends Error{}
const fields=['map','alphaMap','aoMap','bumpMap','normalMap','displacementMap','emissiveMap','metalnessMap','roughnessMap','specularMap','lightMap','clearcoatMap','clearcoatNormalMap','clearcoatRoughnessMap','iridescenceMap','iridescenceThicknessMap','sheenColorMap','sheenRoughnessMap','specularColorMap','specularIntensityMap','transmissionMap','thicknessMap','anisotropyMap'] as const;
const types=new Set<Function>([MeshBasicMaterial,MeshLambertMaterial,MeshPhongMaterial,MeshStandardMaterial,MeshPhysicalMaterial]);
function safe(material:Material){return types.has(material.constructor)&&material.onBeforeRender===Material.prototype.onBeforeRender&&(material.onBeforeCompile===Material.prototype.onBeforeCompile&&material.customProgramCacheKey===Material.prototype.customProgramCacheKey||hasNativeAlphaShader(material)||hasNativeZeroLightShader(material));}
function signature(t:Texture):unknown[]{return[t.source,t.source.version,t.image,t.version,t.onUpdate,t.mapping,t.channel,t.wrapS,t.wrapT,t.magFilter,t.minFilter,t.anisotropy,t.format,t.internalFormat,t.type,t.generateMipmaps,t.flipY,t.premultiplyAlpha,t.colorSpace,t.unpackAlignment,t.matrixAutoUpdate,...t.offset.toArray(),...t.repeat.toArray(),...t.center.toArray(),t.rotation,...t.matrix.elements];}
function matches(t:Texture,s:unknown[]){const next=signature(t);return next.length===s.length&&next.every((value,index)=>Object.is(value,s[index]));}
function ordinaryMesh(object:Object3D):object is Mesh{return object instanceof Mesh&&(object.constructor as Function)===Mesh&&object.onBeforeRender===Object3D.prototype.onBeforeRender&&object.onAfterRender===Object3D.prototype.onAfterRender&&object.onBeforeShadow===Object3D.prototype.onBeforeShadow&&object.onAfterShadow===Object3D.prototype.onAfterShadow;}
/** A transaction borrows exact current maps until successful atomic publication.
 * It never overwrites a replacement material or closes another model's bitmap.
 * Approval/root lifecycle is supplied by the existing private World publisher.
 */
export async function prepareWorldBitmapBindings(root:Object3D,owner:WorldBitmapUpload,signal:AbortSignal,assertCurrent:()=>void){
 const bindings:Binding[]=[],textures=new Map<Texture,Binding[]>(),stack=[root];let nodes=0,unsupported=0;
 assertCurrent();signal.throwIfAborted();
 while(stack.length){const object=stack.pop()!;if(++nodes>100000)throw new BitmapBindingsCapacityError('Bitmap preparation object budget reached');
  if(ordinaryMesh(object)){const mesh=object as Mesh,materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];
   for(let index=0;index<materials.length;index++){const material=materials[index];if(!safe(material)){unsupported++;continue;}
    for(const field of fields){const descriptor=Object.getOwnPropertyDescriptor(material,field);if(!descriptor||!('value'in descriptor)||descriptor.writable!==true||!(descriptor.value instanceof Texture))continue;
     const texture=descriptor.value as Texture;
     // Specialized and already managed images preserve their established path.
     if(texture.constructor!==Texture||texture.onUpdate!==null||texture.isRenderTargetTexture||texture.mipmaps.length||!(typeof HTMLImageElement!=='undefined'&&texture.image instanceof HTMLImageElement)||!([NoColorSpace,SRGBColorSpace,LinearSRGBColorSpace] as string[]).includes(texture.colorSpace)||!Number.isSafeInteger(texture.image.naturalWidth)||!Number.isSafeInteger(texture.image.naturalHeight)||texture.image.naturalWidth<1||texture.image.naturalHeight<1||texture.image.naturalWidth*texture.image.naturalHeight>64*1024*1024){unsupported++;continue;}
     if(bindings.length>=8192||(!textures.has(texture)&&textures.size>=1024))throw new BitmapBindingsCapacityError('Bitmap preparation binding budget reached');
     const binding:Binding={mesh,slot:Array.isArray(mesh.material)?index:null,field,material,texture,version:material.version,signature:signature(texture)};
     bindings.push(binding);let list=textures.get(texture);if(!list)textures.set(texture,list=[]);list.push(binding);
    }
   }
  }
  for(const child of object.children)stack.push(child);
 }
 const work=[...textures.keys()],prepared=new Map<Texture,SessionUploadTexture>();let next=0,fallbacks=0,failure:unknown;
 const abort=new AbortController(),onAbort=()=>abort.abort();signal.addEventListener('abort',onAbort,{once:true});
 const timer=setTimeout(()=>{failure??=new BitmapBindingsCapacityError('Bitmap preparation transaction exceeded its bounded deadline');abort.abort();},30000);
 const current=()=>{signal.throwIfAborted();abort.signal.throwIfAborted();assertCurrent();};
 try{
  // At most two readers from one root; global owner bounds still govern roots.
  const worker=async()=>{while(next<work.length){current();const original=work[next++];try{const texture=await owner.prepare(original,abort.signal);prepared.set(original,texture);current();}catch(error){current();if(!(error instanceof BitmapUploadCapacityError||error instanceof BitmapUploadUnsupportedVariantError))throw error;fallbacks++;}}};
  const guarded=()=>worker().catch(error=>{failure??=error;abort.abort();throw error;});
  await Promise.allSettled([guarded(),guarded()]);if(failure!==undefined)throw failure;
  current();
  // Validate every borrowed descriptor before any map is changed. Never infer
  // current ownership from imported userData or from a still-live original URL.
  const contains=new Set<Object3D>(),todo=[root];let visited=0;
  while(todo.length){const o=todo.pop()!;if(++visited>100000)throw new BitmapBindingsCapacityError('Bitmap publication object budget reached');contains.add(o);for(const child of o.children)todo.push(child);}
  for(const b of bindings){const m=b.slot===null?b.mesh.material:Array.isArray(b.mesh.material)?b.mesh.material[b.slot]:undefined;const d=Object.getOwnPropertyDescriptor(b.material,b.field);
   if(!contains.has(b.mesh)||b.mesh.onBeforeRender!==Object3D.prototype.onBeforeRender||b.mesh.onAfterRender!==Object3D.prototype.onAfterRender||b.mesh.onBeforeShadow!==Object3D.prototype.onBeforeShadow||b.mesh.onAfterShadow!==Object3D.prototype.onAfterShadow||m!==b.material||!safe(b.material)||b.material.version!==b.version||!d||!('value'in d)||d.writable!==true||d.value!==b.texture||!matches(b.texture,b.signature))throw new DOMException('Bitmap material owner changed during preparation','AbortError');
  }
  for(const [original,texture] of prepared)if(!owner.isCompatible(original,texture))throw new DOMException('Bitmap decoded input or texture authority changed during preparation','AbortError');
  current();const resources=new ModelResources();resources.capture(root);const changed=new Set<Material>();
  for(const b of bindings){const texture=prepared.get(b.texture);if(texture){(b.material as Material&Record<string,unknown>)[b.field]=texture;changed.add(b.material);}}
  for(const material of changed)material.needsUpdate=true;
  resources.capture(root);resources.releaseKeeping(root);
  // Textures now belong to the current root, not to this temporary transaction.
  const converted=prepared.size;prepared.clear();return{nodes,bindings:bindings.length,textures:textures.size,converted,fallbacks,unsupported};
 }finally{
  clearTimeout(timer);abort.abort();signal.removeEventListener('abort',onAbort);
  for(const texture of prepared.values()){try{texture.dispose();}catch{/* Continue releasing all transaction-owned leases. */}}
  prepared.clear();bindings.length=0;textures.clear();work.length=0;
 }
}
