// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { BufferAttribute, BufferGeometry, InstancedMesh, Mesh, SkinnedMesh, type Object3D } from 'three';
import { WorkerTaskYield } from './worker-task-yield';

export interface NativeWindingOptions { signal?: AbortSignal; maxIndexBytes?: number; onUnsupported?: (message: string) => void }
export interface NativeWindingScope { convertedMeshes: number; createdGeometries: number; unsupportedMeshes: number; assertStatic(): void }
const aborted = () => new DOMException('Native model winding preparation was cancelled', 'AbortError');
const prepared = new WeakMap<Object3D, NativeWindingScope>();
function parity(mesh: Mesh): number { const determinant = mesh.matrixWorld.determinant(); if (!Number.isFinite(determinant)) throw Error('Native model winding requires a finite world transform'); return Math.sign(determinant); }
function supported(mesh: Mesh): boolean { return !(mesh instanceof SkinnedMesh || mesh instanceof InstancedMesh || (mesh as Mesh & { isBatchedMesh?: boolean }).isBatchedMesh); }
function aligned(geometry: BufferGeometry): boolean {
  const range = geometry.drawRange;
  return range.start % 3 === 0 && (range.count === Infinity || range.count % 3 === 0) && geometry.groups.every(group => group.start % 3 === 0 && group.count % 3 === 0);
}
function shallowGeometry(source: BufferGeometry): BufferGeometry {
  // Only the new index belongs to this clone. All unchanged attribute buffers
  // stay shared within the caller's one freshly parsed model resource scope.
  const geometry = new BufferGeometry(); geometry.name = source.name;
  for (const [name, attribute] of Object.entries(source.attributes)) geometry.setAttribute(name, attribute);
  for (const [name, attributes] of Object.entries(source.morphAttributes)) geometry.morphAttributes[name as keyof typeof geometry.morphAttributes] = [...attributes];
  geometry.morphTargetsRelative = source.morphTargetsRelative;
  geometry.groups = source.groups.map(group => ({ ...group })); geometry.setDrawRange(source.drawRange.start, source.drawRange.count);
  geometry.boundingBox = source.boundingBox?.clone() ?? null; geometry.boundingSphere = source.boundingSphere?.clone() ?? null;
  geometry.userData = { ...source.userData }; return geometry;
}

/** Prepare native fixed-CCW winding before any GPU upload, BVH or batching.
 * Three implicitly flips its front-face definition for a negative object
 * determinant. Reversing each triangle's index order neutralizes that flip,
 * retaining native face/normal classification and the authored draw order.
 * The caller must capture model resources before/after and releaseKeeping(root)
 * to free replaced originals. No global geometry/source cache is involved.
 * Only a static owned model is supported; verify its world parity after any
 * transform change, including normalizer/entity-parent changes.
 */
export async function prepareNativeStaticWinding(root: Object3D, options: NativeWindingOptions = {}): Promise<NativeWindingScope> {
  const maxIndexBytes = options.maxIndexBytes ?? 64 * 1024 * 1024;
  if (!Number.isSafeInteger(maxIndexBytes) || maxIndexBytes <= 0) throw Error('Native winding index budget must be a positive safe integer');
  if (options.signal?.aborted) throw aborted();
  const prior = prepared.get(root); if (prior) { prior.assertStatic(); return prior; }
  root.updateWorldMatrix(true, true);
  const meshStates: Array<{ mesh: Mesh; parity: number; geometry: BufferGeometry }> = [], candidates: Mesh[] = [];
  let unsupportedMeshes = 0, indexBytes = 0;
  root.traverse(object => {
    if (!(object instanceof Mesh)) return;
    const sign = parity(object); meshStates.push({ mesh: object, parity: sign, geometry: object.geometry });
    if (sign >= 0) return;
    if (!supported(object) || !aligned(object.geometry)) { unsupportedMeshes++; return; }
    candidates.push(object);
  });
  if (unsupportedMeshes) options.onUnsupported?.('Mirrored skinned, instanced or unaligned meshes retain their prior winding; native fixed-CCW parity is not verified for them.');
  const clones = new Map<BufferGeometry, BufferGeometry>(), replacements: Array<{ mesh: Mesh; geometry: BufferGeometry }> = [];
  const tasks = new WorkerTaskYield({ signal: options.signal });
  try {
    for (const mesh of candidates) {
      if (options.signal?.aborted) throw aborted();
      let geometry = clones.get(mesh.geometry);
      if (!geometry) {
        const source = mesh.geometry, position = source.getAttribute('position'), oldIndex = source.index;
        if (!position || position.itemSize !== 3 || position.count % 1 !== 0 || oldIndex && (oldIndex.itemSize !== 1 || oldIndex.normalized || !(oldIndex.array instanceof Uint8Array || oldIndex.array instanceof Uint16Array || oldIndex.array instanceof Uint32Array))) throw Error('Native winding requires valid triangle indices and positions');
        const count = oldIndex?.count ?? position.count;
        if (!Number.isSafeInteger(count) || count < 0 || count % 3 !== 0) throw Error('Native winding requires complete triangle groups');
        const IndexArray = oldIndex ? oldIndex.array.constructor as typeof Uint32Array : position.count > 65535 ? Uint32Array : Uint16Array;
        const bytes = count * IndexArray.BYTES_PER_ELEMENT; indexBytes += bytes;
        if (!Number.isSafeInteger(indexBytes) || indexBytes > maxIndexBytes) throw Error('Native winding indices exceed their owned preparation budget');
        const indices = new IndexArray(count);
        for (let start = 0; start < count; start += 32766) {
          const end = Math.min(count, start + 32766);
          for (let index = start; index < end; index += 3) {
            const a = oldIndex ? oldIndex.getX(index) : index, b = oldIndex ? oldIndex.getX(index + 1) : index + 1, c = oldIndex ? oldIndex.getX(index + 2) : index + 2;
            if (!Number.isInteger(a) || a < 0 || a >= position.count || !Number.isInteger(b) || b < 0 || b >= position.count || !Number.isInteger(c) || c < 0 || c >= position.count) throw Error('Native winding triangle references an invalid vertex');
            indices[index] = b; indices[index + 1] = a; indices[index + 2] = c;
          }
          if (end < count) await tasks.yield();
          if (options.signal?.aborted) throw aborted();
        }
        geometry = shallowGeometry(source); geometry.setIndex(new BufferAttribute(indices, 1)); clones.set(source, geometry);
      }
      replacements.push({ mesh, geometry });
    }
    root.updateWorldMatrix(true, true);
    if (options.signal?.aborted) throw aborted();
    const originalMeshes = new Set(meshStates.map(entry => entry.mesh)); let currentMeshes = 0;
    root.traverse(object => { if (object instanceof Mesh) { currentMeshes++; if (!originalMeshes.has(object)) throw Error('Native model graph changed during static preparation'); } });
    if (currentMeshes !== meshStates.length) throw Error('Native model graph changed during static preparation');
    for (const entry of meshStates) if (parity(entry.mesh) !== entry.parity || entry.mesh.geometry !== entry.geometry) throw Error('Native model winding or geometry changed during static preparation');
    // Commit only after every clone succeeds; failure preserves the input tree.
    for (const replacement of replacements) replacement.mesh.geometry = replacement.geometry;
    const geometries = new Map(meshStates.map(entry => [entry.mesh, entry.mesh.geometry]));
    const scope = { convertedMeshes: replacements.length, createdGeometries: clones.size, unsupportedMeshes,
      assertStatic() {
        root.updateWorldMatrix(true, true); let meshes = 0;
        root.traverse(object => { if (object instanceof Mesh) { meshes++; if (!geometries.has(object)) throw Error('Native static winding model graph changed; reload before rendering'); } });
        if (meshes !== meshStates.length) throw Error('Native static winding model graph changed; reload before rendering');
        for (const entry of meshStates) if (parity(entry.mesh) !== entry.parity || geometries.get(entry.mesh) !== entry.mesh.geometry) throw Error('Native model winding parity or geometry changed; reload this static model before rendering');
      },
    };
    prepared.set(root, scope); return scope;
  } catch (error) { for (const geometry of clones.values()) geometry.dispose(); throw error; }
  finally { tasks.close(); }
}
