// SPDX-License-Identifier: Apache-2.0
// Exact frozen World private cleanup binding; no alternate cleanup algorithm.
import * as THREE from 'three';
import {isOwnedUploadBitmap} from '../../src/world-bitmap-upload';
import {ownedGraphSkeletons,disposeOwnedSkeleton} from '../../src/owned-skeletons';
export function disposeObject(root: THREE.Object3D): void {
  // One owned graph may share geometry, material slots, maps and bitmap data.
  // Do not transfer disposal authority across graphs or suppress listener errors.
  const skeletons = ownedGraphSkeletons(root);
  const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>(), bitmaps = new Set<ImageBitmap>();
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line)) return;
    if (!geometries.has(object.geometry)) { geometries.add(object.geometry); object.geometry.dispose(); }
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (materials.has(material)) continue;
      materials.add(material);
      for (const value of Object.values(material)) if (value instanceof THREE.Texture && !textures.has(value)) {
        textures.add(value);
        value.dispose();
        if (typeof ImageBitmap !== 'undefined' && value.image instanceof ImageBitmap && !isOwnedUploadBitmap(value.image) && !bitmaps.has(value.image)) { bitmaps.add(value.image); value.image.close(); }
      }
      material.dispose();
    }
  });
  for (const skeleton of skeletons) disposeOwnedSkeleton(skeleton);
}
