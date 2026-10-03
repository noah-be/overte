// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { Material, type Texture } from 'three';
import { nativeTextureAlpha, type NativeTextureAlpha } from './texture-alpha';
import { nativeCompressedColorAlpha } from './native-compressed-color';

export type NativeOpacityMapMode = 'OPACITY_MAP_OPAQUE' | 'OPACITY_MAP_MASK' | 'OPACITY_MAP_BLEND';
export interface NativeAlphaOptions { useAlpha: boolean; mode?: NativeOpacityMapMode; cutoff?: number }
export type MappedMaterial = Material & { map?: Texture | null; alphaMap?: Texture | null };
const nativeShaders = new WeakMap<Material, { compile: Material['onBeforeCompile']; key: Material['customProgramCacheKey'] }>();
const nativeOptions = new WeakMap<Material, NativeAlphaOptions>();
export function getNativeAlphaOptions(material: Material): NativeAlphaOptions | undefined {
  const options = nativeOptions.get(material);
  return options ? { ...options } : undefined;
}

/** Only our exact per-material fragment hooks are safe for static batching.
 * Model/userData fields and copied foreign callback functions cannot claim it. */
export function hasNativeAlphaShader(material: Material): boolean {
  return matchesNativeAlphaHooks(material, material.onBeforeCompile, material.customProgramCacheKey);
}

/** A composed native effect must prove the exact captured parent shader pair. */
export function matchesNativeAlphaHooks(material: Material, compile: Material['onBeforeCompile'], key: Material['customProgramCacheKey']): boolean {
  const owned = nativeShaders.get(material);
  return Boolean(owned && owned.compile === compile && owned.key === key);
}

/** Native Material.cpp honors explicit modes before inspecting eligible albedo alpha. */
export async function applyNativeMaterialAlpha(material: MappedMaterial, options: NativeAlphaOptions, signal?: AbortSignal): Promise<void> {
  if (!hasNativeAlphaShader(material) && (material.onBeforeCompile !== Material.prototype.onBeforeCompile || material.customProgramCacheKey !== Material.prototype.customProgramCacheKey)) {
    throw Error('Native alpha conversion cannot replace an unsupported custom material shader');
  }
  let alpha: NativeTextureAlpha = 'opaque';
  if (options.mode === 'OPACITY_MAP_MASK') alpha = 'mask';
  else if (options.mode === 'OPACITY_MAP_BLEND') alpha = 'blend';
  else if (!options.mode && options.useAlpha && material.map) alpha = nativeCompressedColorAlpha(material.map) ?? await nativeTextureAlpha(material.map, signal);
  if (signal?.aborted) throw new DOMException('Material loading cancelled', 'AbortError');
  const cutoff = typeof options.cutoff === 'number' && Number.isFinite(options.cutoff) ? Math.max(0, Math.min(1, options.cutoff)) : 0.5;
  material.userData.nativeAlpha = { ...options, cutoff, classification: alpha };
  nativeOptions.set(material, { ...options, cutoff });
  // Native opacity is read from the ALPHA channel of the shared albedo map.
  // Three's separate alphaMap reads GREEN, so never multiply that same image again.
  material.alphaMap = null;
  material.alphaTest = alpha === 'mask' ? cutoff * material.opacity : 0;
  material.transparent = material.opacity < 1 || alpha === 'blend';
  // Native color textures retain RGBA even when automatic alpha flags are disabled.
  // Scalar translucency still multiplies that alpha; only masking needs a hook.
  if (material.map && alpha === 'mask') {
    material.onBeforeCompile = shader => {
      shader.uniforms.nativeOpacityCutoff = { value: cutoff };
      shader.fragmentShader = 'uniform float nativeOpacityCutoff;\n' + shader.fragmentShader.replace('#include <map_fragment>',
        '#include <map_fragment>\n#ifdef USE_MAP\n' +
        'diffuseColor.a = opacity * step(nativeOpacityCutoff, sampledDiffuseColor.a);\n#endif');
    };
    // Cutoff is a uniform; avoid recompiling for each authored material value.
    material.customProgramCacheKey = () => `native-material-alpha-${alpha}`;
    nativeShaders.set(material, { compile: material.onBeforeCompile, key: material.customProgramCacheKey });
  } else {
    material.onBeforeCompile = Material.prototype.onBeforeCompile;
    material.customProgramCacheKey = Material.prototype.customProgramCacheKey;
    nativeShaders.delete(material);
  }
  material.needsUpdate = true;
}

/** Three does not copy shader callbacks when cloning a Material. */
export function cloneNativeMaterial<T extends Material>(material: T): T {
  const clone = material.clone();
  const options = getNativeAlphaOptions(material);
  if (options) nativeOptions.set(clone, options);
  if (hasNativeAlphaShader(material)) {
    clone.onBeforeCompile = material.onBeforeCompile;
    clone.customProgramCacheKey = material.customProgramCacheKey;
    nativeShaders.set(clone, { compile: clone.onBeforeCompile, key: clone.customProgramCacheKey });
  }
  return clone;
}

export function nativeOpacityMapMode(value: unknown): NativeOpacityMapMode | undefined {
  return value === 'OPACITY_MAP_OPAQUE' || value === 'OPACITY_MAP_MASK' || value === 'OPACITY_MAP_BLEND' ? value : undefined;
}
