// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { type Material } from 'three';
import { applyNativeRenderState, nativeCullFaceMode, type NativeCullFaceMode } from './native-render-state';

export type NativeCullSource = 'solid-primitive' | 'native-material' | 'fbx-import' | 'gltf-import' | 'image' | 'text-background' | 'unsupported-flat-shape';
/** Omitted native material cull means BACK; unknown values preserve prior state.
 * Imported glTF already declares its own double-sided choice. Existing flat
 * browser shape approximations are excluded until native geometry is restored.
 */
export function applyNativeDefaultCull(material: Material, source: NativeCullSource, declaredCull?: unknown): void {
  let mode: NativeCullFaceMode | undefined;
  if (declaredCull !== undefined) { mode = nativeCullFaceMode(declaredCull); if (!mode) return; }
  else if (source === 'gltf-import' || source === 'unsupported-flat-shape') return;
  else mode = source === 'image' || source === 'text-background' ? 'CULL_NONE' : 'CULL_BACK';
  applyNativeRenderState(material, { cullFaceMode: mode });
}
