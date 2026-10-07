// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { BufferAttribute, Mesh, type BufferGeometry, type Object3D } from 'three';

/** Native GLTFSerializer accepts COLOR_0 VEC4 but stores only RGB in HFMMesh.
 * Use only for a freshly parsed, owned native glTF model, before GPU upload.
 * Material opacity and texture alpha remain independent of vertex RGB.
 */
export function normalizeNativeGltfVertexColor(geometry: BufferGeometry): boolean {
  const color = geometry.getAttribute('color');
  if (!color || color.itemSize !== 4) return false;
  const rgb = new Float32Array(color.count * 3);
  for (let index = 0; index < color.count; index++) {
    // Accessors preserve normalized integer and interleaved source semantics.
    // The native serializer also unpacks normalized values to float32.
    rgb[index * 3] = color.getX(index);
    rgb[index * 3 + 1] = color.getY(index);
    rgb[index * 3 + 2] = color.getZ(index);
  }
  const attribute = new BufferAttribute(rgb, 3);
  attribute.name = color.name;
  attribute.setUsage('data' in color ? color.data.usage : color.usage);
  geometry.setAttribute('color', attribute);
  return true;
}

/** Deduplicate geometry shared by meshes within this owned parsed scene. */
export function normalizeNativeGltfColors(root: Object3D): number {
  const geometries = new Set<BufferGeometry>();
  root.traverse(object => { if (object instanceof Mesh) geometries.add(object.geometry); });
  let converted = 0;
  for (const geometry of geometries) if (normalizeNativeGltfVertexColor(geometry)) converted++;
  return converted;
}
