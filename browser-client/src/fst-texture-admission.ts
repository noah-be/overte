// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type {FstGraphCache} from './fst-graph-cache';
import {Material,MeshBasicMaterial,MeshStandardMaterial} from 'three';
import {inspectFbxOriginalTextures,type EmbeddedFbxImage,type FbxTextureAdmissionResult} from './baked-fbx';

export interface ResolvedFstReplacement {
  selector:string;
  definition:unknown;
  /** Actual successfully loaded native/FST template; borrowed, never disposed
   * here. Caller owns its resources until normal ordered model assignments. */
  template:Material;
}
const properties=new Set(['name','model','defaultFallthrough','albedo','albedoMap','normalMap','roughness','roughnessMap','metallic','metallicMap','opacity','opacityMap','opacityMapMode','opacityCutoff','emissive','emissiveMap','unlit','cullFaceMode']);
const mapFields=['albedoMap','normalMap','roughnessMap','metallicMap','opacityMap','emissiveMap'];
function completeDefinition(value:unknown):boolean{
  if(!value||typeof value!=='object'||Array.isArray(value))return false;
  const data=value as Record<string,unknown>;
  // Native false is the default. Unknown/custom/partial properties preserve the
  // existing original admission, rather than inferring a replacement from an
  // ignored or unsupported field. In particular all fallthrough stays intact.
  if(Object.keys(data).some(key=>!properties.has(key)))return false;
  if(data.defaultFallthrough!==undefined&&data.defaultFallthrough!==false)return false;
  if(data.model!==undefined&&data.model!=='hifi_pbr')return false;
  if(data.name!==undefined&&(typeof data.name!=='string'||data.name.length>1024))return false;
  if(data.unlit!==undefined&&typeof data.unlit!=='boolean')return false;
  for(const field of ['roughness','metallic','opacity','opacityCutoff'])if(data[field]!==undefined&&(typeof data[field]!=='number'||!Number.isFinite(data[field])||(data[field] as number)<0||(data[field] as number)>1))return false;
  for(const field of mapFields)if(data[field]!==undefined&&(typeof data[field]!=='string'||!(data[field] as string).length||(data[field] as string).length>4096||data[field]==='fallthrough'))return false;
  if(data.opacityMapMode!==undefined&&!['OPACITY_MAP_OPAQUE','OPACITY_MAP_MASK','OPACITY_MAP_BLEND'].includes(String(data.opacityMapMode)))return false;
  if(data.cullFaceMode!==undefined&&!['CULL_NONE','CULL_FRONT','CULL_BACK'].includes(String(data.cullFaceMode)))return false;
  // Separate opacity images and explicit native transform/layer semantics are
  // outside the current makeMaterial implementation and never admitted here.
  if(data.opacityMap!==undefined&&data.opacityMap!==data.albedoMap)return false;
  for(const field of ['albedo','emissive'])if(data[field]!==undefined){
    const color=data[field],channels=Array.isArray(color)?color:color&&typeof color==='object'?[ (color as Record<string,unknown>).red,(color as Record<string,unknown>).green,(color as Record<string,unknown>).blue ]:undefined;
    if(!channels||channels.length!==3||channels.some(channel=>typeof channel!=='number'||!Number.isFinite(channel)||channel<0||channel>(field==='albedo'?1:65536)))return false;
  }
  return true;
}
/** Metadata-only preflight. Actual templates/images must still succeed before
 * prepareFstTextureAdmission permits omission. No parse buffer is allocated. */
export function canFstDefinitionsReplaceOriginalTextures(inspection:NonNullable<ReturnType<typeof inspectFbxOriginalTextures>>,
  replacements:readonly {selector:string;definition:unknown}[]):boolean{
  if(!Array.isArray(replacements)||!replacements.length||replacements.length>256)return false;
  const current=inspection.materials.map(material=>({...material,replaced:false}));
  for(const replacement of replacements){
    if(typeof replacement.selector!=='string'||replacement.selector.length>1024||!(replacement.selector==='all'||replacement.selector.startsWith('mat::'))||!completeDefinition(replacement.definition))return false;
    const data=replacement.definition as Record<string,unknown>;
    for(const material of current){
      if(replacement.selector!=='all'&&replacement.selector!==`mat::${material.name}`)continue;
      material.replaced=true;material.name=typeof data.name==='string'?data.name:'';
    }
  }
  return inspection.hasRemovableTextures(new Set(current.filter(material=>material.replaced).map(material=>material.id)));
}
export interface FstTextureAdmission extends FbxTextureAdmissionResult {
  replacedMaterialCount:number;
  embeddedImages:readonly EmbeddedFbxImage[];
}
/** Call only after exact visitor-authorized definitions AND their templates
 * succeeded. Authority is checked before/after proof; abort never falls back.
 * Uncertain formats/mappings return undefined and keep the ordinary FBX path.
 * It does not replace material application or mutate any borrowed resource. */
export function prepareFstTextureAdmission(input:ArrayBuffer,replacements:readonly ResolvedFstReplacement[],
  embeddedImages:readonly EmbeddedFbxImage[],signal:AbortSignal,assertCurrent:()=>void,cache?:FstGraphCache):FstTextureAdmission|undefined{
  signal.throwIfAborted();assertCurrent();
  if(!Array.isArray(replacements)||!replacements.length||replacements.length>256||!Array.isArray(embeddedImages)||embeddedImages.length>64)return undefined;
  for(const item of replacements){
    if(!item||typeof item.selector!=='string'||item.selector.length>1024||!(item.selector==='all'||item.selector.startsWith('mat::'))||!completeDefinition(item.definition))return undefined;
    if(!(item.template instanceof MeshBasicMaterial||item.template instanceof MeshStandardMaterial))return undefined;
    const data=item.definition as Record<string,unknown>;
    if(item.template.name!==(typeof data.name==='string'?data.name:''))return undefined;
    const fields=[['albedoMap','map'],['normalMap','normalMap'],['roughnessMap','roughnessMap'],['metallicMap','metalnessMap'],['emissiveMap','emissiveMap']] as const;
    for(const [declared,field]of fields){
      if(data[declared]===undefined)continue;
      if(field!=='map'&&item.template instanceof MeshBasicMaterial)continue;
      const texture=(item.template as unknown as Record<string,unknown>)[field];
      if(!texture||typeof texture!=='object'||!(texture as {isTexture?:boolean}).isTexture||!(texture as {image?:unknown}).image)return undefined;
    }
  }
  const inspection=cache?cache.inspect(input):inspectFbxOriginalTextures(input);if(!inspection)return undefined;
  const current=inspection.materials.map(material=>({...material,replaced:false}));
  // Apply selector/name effects in the same source order as actual FST
  // assignments. Later selectors operate on replacement names, not stale IDs.
  for(const replacement of replacements)for(const material of current){
    if(replacement.selector!=='all'&&replacement.selector!==`mat::${material.name}`)continue;
    material.replaced=true;material.name=replacement.template.name;
  }
  const covered=new Set(current.filter(material=>material.replaced).map(material=>material.id));
  const derived=inspection.derive(covered);signal.throwIfAborted();assertCurrent();
  if(!derived.removedTextures&&!derived.removedVideos)return undefined;
  const filtered=embeddedImages.filter(image=>derived.usedEmbeddedMarkers.has(`data:${image.mimeType};base64,overte-embedded-${image.digest}`));
  const described=new Set(filtered.map(image=>`data:${image.mimeType};base64,overte-embedded-${image.digest}`));
  if([...derived.usedEmbeddedMarkers].some(marker=>!described.has(marker)))return undefined;
  // Register filtered descriptors using ORIGINAL prepared-buffer identity, not
  // derived.buffer. That preserves per-world embedded leases across instances.
  return {...derived,replacedMaterialCount:covered.size,embeddedImages:filtered};
}
