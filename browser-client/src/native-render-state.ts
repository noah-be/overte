// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { BackSide, DoubleSide, FrontSide, Material, Mesh, type BufferGeometry, type Object3D } from 'three';
import { cloneNativeMaterial, hasNativeAlphaShader } from './native-alpha-material';

export type NativeCullFaceMode = 'CULL_NONE' | 'CULL_FRONT' | 'CULL_BACK';
export function nativeCullFaceMode(value: unknown): NativeCullFaceMode | undefined {
  return value === 'CULL_NONE' || value === 'CULL_FRONT' || value === 'CULL_BACK' ? value : undefined;
}

/** Reproduce native standard mesh pipeline state, without rewriting shaders.
 * RenderPipelinesInit.cpp.in uses one indexed draw, the selected cull mode and
 * disabled depth writes for translucent items. Omitted cull mode preserves an
 * imported model's side; opting into native CULL_BACK defaults is separate.
 * This helper is prepared for integration, not applied globally by importing it.
 */
export function applyNativeRenderState(material: Material, options: { cullFaceMode?: NativeCullFaceMode } = {}): void {
  const custom = material as Material & { isShaderMaterial?: boolean; isRawShaderMaterial?: boolean; isNodeMaterial?: boolean };
  if (custom.isShaderMaterial || custom.isRawShaderMaterial || custom.isNodeMaterial
      || !hasNativeAlphaShader(material) && (material.onBeforeCompile !== Material.prototype.onBeforeCompile
        || material.customProgramCacheKey !== Material.prototype.customProgramCacheKey)) {
    throw Error('Native render state cannot alter an unsupported custom material shader');
  }
  if (options.cullFaceMode !== undefined && nativeCullFaceMode(options.cullFaceMode) === undefined) {
    throw Error('Unsupported native cull face mode');
  }
  const side = options.cullFaceMode === 'CULL_NONE' ? DoubleSide
    : options.cullFaceMode === 'CULL_FRONT' ? BackSide
    : options.cullFaceMode === 'CULL_BACK' ? FrontSide : material.side;
  const single = side === DoubleSide;
  const shaderChanged = material.side !== side || material.forceSinglePass !== single;
  material.side = side;
  material.forceSinglePass = single;
  material.depthWrite = !material.transparent;
  if (shaderChanged) material.needsUpdate = true;
}

/** A native material override does not remove a mesh's authored RGB stream.
 * Geometry.cpp adds fallback white only when COLOR is absent, independently
 * of the material layer. Keep each geometry's vertex-color choice separate.
 */
export function cloneNativeMaterialForGeometry<T extends Material>(material: T, geometry: BufferGeometry): T {
  const clone = cloneNativeMaterial(material);
  const vertexColors = Boolean(geometry.getAttribute('color'));
  if (clone.vertexColors !== vertexColors) { clone.vertexColors = vertexColors; clone.needsUpdate = true; }
  return clone;
}

/** Only call for native-loaded models; arbitrary user shaders remain refused. */
export function applyNativeModelRenderState(root: Object3D): void {
  const materials = new Set<Material>();
  root.traverse(object => { if (object instanceof Mesh) for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material); });
  for (const material of materials) applyNativeRenderState(material);
}
