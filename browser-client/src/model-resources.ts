// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { BufferGeometry, Line, Material, Mesh, Texture, type Object3D } from 'three';

interface Resources {
  geometries: Set<BufferGeometry>;
  materials: Set<Material>;
  textures: Set<Texture>;
}
function resources(): Resources {
  return { geometries: new Set(), materials: new Set(), textures: new Set() };
}
function materialResources(material: Material, into: Resources): void {
  into.materials.add(material);
  // Three's FBX/glTF/OBJ material map fields are direct Texture references.
  // Asset userData is not an ownership declaration and is deliberately ignored.
  for (const value of Object.values(material)) if (value instanceof Texture) into.textures.add(value);
}
function objectResources(root: Object3D, into: Resources): void {
  root.traverse(object => {
    if (!(object instanceof Mesh || object instanceof Line)) return;
    into.geometries.add(object.geometry);
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) materialResources(material, into);
  });
}
function bitmaps(textures: Iterable<Texture>): Set<ImageBitmap> {
  const result = new Set<ImageBitmap>();
  if (typeof ImageBitmap === 'undefined') return result;
  for (const texture of textures) {
    // Cube textures may own several image bitmaps; texture clones may share them.
    const image: unknown = texture.image;
    for (const item of Array.isArray(image) ? image : [image]) if (item instanceof ImageBitmap) result.add(item);
  }
  return result;
}

/** Own the resources created while a model mapping replaces its materials.
 * Capture before replacements and after adding clones, then releaseKeeping the
 * successful model. On failure capture its current state and releaseKeeping().
 * Only the caller's model resources belong here; other scenes must not share
 * them unless they are included in the retained root.
 */
export class ModelResources {
  private readonly owned = resources();
  private readonly released = resources();
  private readonly closedBitmaps = new Set<ImageBitmap>();

  capture(root: Object3D): void { objectResources(root, this.owned); }
  captureMaterial(material: Material): void { materialResources(material, this.owned); }

  releaseKeeping(root?: Object3D): void {
    // A captured material may receive its asynchronously loaded texture later.
    for (const material of this.owned.materials) materialResources(material, this.owned);
    const retained = resources();
    if (root) objectResources(root, retained);
    const retainedBitmaps = bitmaps(retained.textures), ownedBitmaps = bitmaps(this.owned.textures);
    this.dispose(this.owned.geometries, retained.geometries, this.released.geometries);
    this.dispose(this.owned.textures, retained.textures, this.released.textures);
    this.dispose(this.owned.materials, retained.materials, this.released.materials);
    for (const image of ownedBitmaps) {
      if (retainedBitmaps.has(image) || this.closedBitmaps.has(image)) continue;
      this.closedBitmaps.add(image);
      try { image.close(); } catch { /* Cleanup cannot replace the original mapping error. */ }
    }
  }

  private dispose<T extends { dispose(): void }>(owned: Set<T>, retained: Set<T>, released: Set<T>): void {
    for (const resource of owned) {
      if (retained.has(resource) || released.has(resource)) continue;
      released.add(resource);
      try { resource.dispose(); } catch { /* Continue releasing the remaining owned resources. */ }
    }
  }
}
