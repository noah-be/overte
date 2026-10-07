// SPDX-License-Identifier: Apache-2.0
// Exact65e22 original routine for a counterfactual negative control only.
import * as THREE from 'three';
import {isOwnedUploadBitmap} from '../../src/world-bitmap-upload';
export function disposeObject(root: THREE.Object3D): void {
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line)) return;
    object.geometry.dispose();
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) {
        value.dispose();
        if (typeof ImageBitmap !== 'undefined' && value.image instanceof ImageBitmap && !isOwnedUploadBitmap(value.image)) value.image.close();
      }
      material.dispose();
    }
  });
}
