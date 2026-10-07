// SPDX-License-Identifier: Apache-2.0
// Exact pre-observation production makeMaterial body; dependencies retain real identities.
import * as THREE from 'three';
import {assetDependency,materialRGB,type MaterialData} from '../../src/world-data';
import {ModelResources} from '../../src/model-resources';
import {nativeOpacityMapMode,type NativeAlphaOptions,type MappedMaterial} from '../../src/native-alpha-material';
import {applyNativeDefaultCull} from '../../src/native-default-cull';
import {applyNativeRenderState,nativeCullFaceMode} from '../../src/native-render-state';
import type {TextureRole} from '../../src/color-texture-metadata';
export class OriginalFstMaterial {
 abort!:AbortController;
 options!:{onStatus(text:string,kind:string):void};
 nativeCullDefaults!:boolean;
 texture!:(url:string,color:boolean,role:TextureRole,signal:AbortSignal)=>Promise<THREE.Texture>;
 configureAlpha!:(material:MappedMaterial,options:NativeAlphaOptions,signal:AbortSignal)=>Promise<void>;
  private async makeMaterial(data: MaterialData, source?: string,signal=this.abort.signal): Promise<THREE.MeshStandardMaterial | THREE.MeshBasicMaterial> {
    signal.throwIfAborted();
    if ((data.model && data.model !== 'hifi_pbr') || data.procedural) {
      this.options.onStatus('Custom shader or toon materials are not supported. Basic material colors and textures are used instead.', 'warning');
    }
    const common = {
      color: data.albedo ? new THREE.Color(...materialRGB(data.albedo)) : 0xffffff,
      opacity: data.opacity ?? 1, transparent: (data.opacity ?? 1) < 1,
      name: data.name, side: THREE.DoubleSide,
    };
    // Unlit materials keep their declared albedo colors without the scene's filmic light grading.
    const material = data.unlit ? new THREE.MeshBasicMaterial({ ...common, toneMapped: false }) : new THREE.MeshStandardMaterial({
      ...common, roughness: data.roughness ?? 0.7, metalness: data.metallic ?? 0,
      emissive: data.emissive ? new THREE.Color(...materialRGB(data.emissive)) : 0,
    });
    const resources = new ModelResources(); resources.captureMaterial(material);
    try {
      // Independent maps can fetch/decode concurrently; the session image cache
      // bounds actual requests to six. Wait for every result before cleanup so
      // a late successful map cannot escape a failed material's ownership.
      const maps = await Promise.allSettled(([ ['albedoMap', 'map', true], ['normalMap', 'normalMap', false], ['roughnessMap', 'roughnessMap', false], ['metallicMap', 'metalnessMap', false], ['emissiveMap', 'emissiveMap', true] ] as const).map(async ([key, field, color]) => {
        const url = data[key];
        if (url && (field === 'map' || material instanceof THREE.MeshStandardMaterial)) {
          const role:TextureRole=field==='map'?'albedo':field==='emissiveMap'?'emissive':'linear';
          const texture = await this.texture(source && source !== 'materialData' ? assetDependency(source, url) : url, color,role,signal);
          if (field === 'map') material.map = texture;
          else if (material instanceof THREE.MeshStandardMaterial) material[field] = texture;
        }
      }));
      const failedMap=maps.find((value):value is PromiseRejectedResult=>value.status==='rejected');
      if(failedMap)throw failedMap.reason;
      signal.throwIfAborted();
      const resolve = (url: string) => source && source !== 'materialData' ? assetDependency(source, url) : url;
      await this.configureAlpha(material, { useAlpha: Boolean(data.albedoMap && data.opacityMap && resolve(data.albedoMap) === resolve(data.opacityMap)),
        mode: nativeOpacityMapMode(data.opacityMapMode), cutoff: data.opacityCutoff },signal);
      if (this.nativeCullDefaults) applyNativeDefaultCull(material, 'native-material', data.cullFaceMode);
      else applyNativeRenderState(material, { cullFaceMode: nativeCullFaceMode(data.cullFaceMode) });
      return material;
    } catch (error) {
      resources.releaseKeeping(); throw error;
    }
  }

}
