// SPDX-License-Identifier: Apache-2.0
// Decode ordinary native meshes with bundled Google WASM; historical custom
// HFM semantics use a separately pinned, compatible Google decoder worker.
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { LinearSRGBColorSpace, type BufferGeometry } from 'three';
import wrapperURL from 'three/examples/jsm/libs/draco/draco_wasm_wrapper.js?url';
import wasmURL from 'three/examples/jsm/libs/draco/draco_decoder.wasm?url';
import type { DecodedBakedGeometry } from './baked-fbx';
interface NativeDracoLoader extends DRACOLoader {
  decodeDracoFile(buffer: ArrayBuffer, callback: (geometry: BufferGeometry) => void, attributes: Record<string, number> | null,
    types: Record<string, string> | null, colorSpace: typeof LinearSRGBColorSpace, onError: (error: unknown) => void): Promise<unknown>;
}
let loader: NativeDracoLoader | undefined;
function decode(bytes: ArrayBuffer, attributes: Record<string, number> | null = null, types: Record<string, string> | null = null): Promise<BufferGeometry> {
  loader ??= new DRACOLoader().setDecoderPath({ js: wrapperURL, wasm: wasmURL }).setWorkerLimit(2) as NativeDracoLoader;
  const active = loader;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      if (loader === active) { active.dispose(); loader = undefined; }
      reject(Error('The baked model Draco decoder exceeded its 30-second limit'));
    }, 30000);
    const failed = (error: unknown) => { clearTimeout(timer); reject(error); };
    active.decodeDracoFile(bytes, geometry => { clearTimeout(timer); resolve(geometry); }, attributes, types, LinearSRGBColorSpace, failed).catch(failed);
  });
}
export async function decodeBakedDraco(bytes: ArrayBuffer, options: { materialIDs: boolean; uv1: boolean; originalIndices: boolean }): Promise<DecodedBakedGeometry> {
  if (options.materialIDs || options.uv1 || options.originalIndices) return (await import('./baked-draco-legacy')).decodeLegacyBakedDraco(bytes, options);
  let geometry: BufferGeometry;
  try { geometry = await decode(bytes.slice(0)); } catch {
    // Native meshes can also carry original-index attributes for deformation.
    // Never modify their encoded bytes to bypass newer semantic validation.
    return (await import('./baked-draco-legacy')).decodeLegacyBakedDraco(bytes, options);
  }
  try {
    const position = geometry.getAttribute('position'), index = geometry.getIndex(); if (!position || !index) throw Error('Native Draco data has no triangular position mesh');
    const result: DecodedBakedGeometry = { positions: position.array, indices: index.array, normals: geometry.getAttribute('normal')?.array, uv: geometry.getAttribute('uv')?.array, colors: geometry.getAttribute('color')?.array };
    return result;
  } finally { geometry.dispose(); }
}
export function disposeBakedDracoDecoder(): void { loader?.dispose(); loader = undefined; }
