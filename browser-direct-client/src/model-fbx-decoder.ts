// SPDX-License-Identifier: Apache-2.0
// Decode inside the owned preparation worker: no unowned nested worker lifetime.
import createLegacyDecoder from 'draco3d/draco_decoder_nodejs.js';
import createModernDecoder from 'three/examples/jsm/libs/draco/draco_wasm_wrapper.js';
import wasmURL from 'three/examples/jsm/libs/draco/draco_decoder.wasm?url';
import type { BakedDracoDecoder, DecodedBakedGeometry } from './baked-fbx';
import { boundDecoderHeap } from './model-fbx-decoder-memory';
let legacy: any, modern: Promise<any> | undefined;
function legacyModule() {
  if (!legacy) legacy = createLegacyDecoder({ ENVIRONMENT: 'WORKER', TOTAL_MEMORY: 64 * 1024 * 1024,
    reallocBuffer: (size: number) => { if (size > 256 * 1024 * 1024) return null;
      const replacement = new ArrayBuffer(size); new Uint8Array(replacement).set(legacy.HEAPU8); return replacement; },
    print: () => {}, printErr: () => {} });
  return legacy;
}
function extract(draco: any, bytes: ArrayBuffer, options: Parameters<BakedDracoDecoder>[1]): DecodedBakedGeometry {
  if (!(bytes instanceof ArrayBuffer) || bytes.byteLength > 32 * 1024 * 1024) throw Error('Invalid native Draco input length');
  const owned: any[] = [], make = (value: any) => { owned.push(value); return value; };
  try {
  const decoder = make(new draco.Decoder()), buffer = make(new draco.DecoderBuffer());
  buffer.Init(new Int8Array(bytes), bytes.byteLength);
  const mesh = make(new draco.Mesh()), status = make(decoder.DecodeBufferToMesh(buffer, mesh));
  if (!status.ok()) throw Error(status.error_msg());
  const points = mesh.num_points(), faces = mesh.num_faces();
  if (!Number.isInteger(points) || points <= 0 || points > 2_000_000 || !Number.isInteger(faces) || faces <= 0 || faces > 4_000_000) throw Error('Native Draco mesh exceeds geometry limits');
  const attribute = (semantic: number, width: number, unique = false): Float32Array | undefined => {
    const id = unique ? semantic : decoder.GetAttributeId(mesh, semantic);
    if (id < 0) return undefined;
    const value = unique ? decoder.GetAttributeByUniqueId(mesh, id) : decoder.GetAttribute(mesh, id);
    if (!value || !value.ptr) return undefined;
    if (value.num_components() !== width) throw Error('Invalid native Draco attribute width');
    const values = new draco.DracoFloat32Array();
    try {
      if (!decoder.GetAttributeFloatForAllPoints(mesh, value, values) || values.size() !== points * width) throw Error('Invalid native Draco attribute length');
      const result = new Float32Array(points * width);
      for (let i = 0; i < result.length; i++) { const number = values.GetValue(i); if (!Number.isFinite(number)) throw Error('Non-finite native Draco attribute'); result[i] = number; }
      return result;
    } finally { draco.destroy(values); }
  };
  const positions = attribute(draco.POSITION, 3); if (!positions) throw Error('Native Draco mesh has no positions');
  const indices = new Uint32Array(faces * 3), face = make(new draco.DracoInt32Array());
  for (let i = 0; i < faces; i++) { if (!decoder.GetFaceFromMesh(mesh, i, face)) throw Error('Invalid native Draco face'); for (let j = 0; j < 3; j++) { const index = face.GetValue(j); if (!Number.isInteger(index) || index < 0 || index >= points) throw Error('Invalid native Draco vertex index'); indices[i * 3 + j] = index; } }
  const meshData: DecodedBakedGeometry = { positions, indices, normals: attribute(draco.NORMAL, 3), uv: attribute(draco.TEX_COORD, 2), colors: attribute(draco.COLOR, 3) };
  if (options.materialIDs) { const values = attribute(1000, 1, true); if (!values) throw Error('Native Draco mesh has no material IDs'); const ids = new Uint32Array(points); for (let i = 0; i < points; i++) { if (!Number.isInteger(values[i]) || values[i] < 0 || values[i] > 65535) throw Error('Invalid native Draco material ID'); ids[i] = values[i]; } meshData.materialIDs = ids; }
  if (options.uv1) meshData.uv1 = attribute(1001, 2, true);
  if (options.originalIndices) {
    const attribute = decoder.GetAttributeByUniqueId(mesh, 1002);
    if (attribute && attribute.ptr) {
      if (attribute.num_components() !== 1) throw Error('Invalid native Draco original-index width');
      const values = new draco.DracoInt32Array();
      try {
    if (!decoder.GetAttributeIntForAllPoints(mesh, attribute, values) || values.size() !== points) throw Error('Invalid native Draco original-index length');
    const original = new Uint32Array(points);
    for (let i = 0; i < points; i++) { const index = values.GetValue(i); if (!Number.isInteger(index) || index < 0 || index >= 2_000_000) throw Error('Invalid native Draco original index'); original[i] = index; }
    meshData.originalIndices = original;
      } finally { draco.destroy(values); }
    }
  }
    return meshData;
  } finally { for (const value of owned.reverse()) draco.destroy(value); }
}
export const decodePreparedBakedDraco: BakedDracoDecoder = async (bytes, options) => {
  if (options.materialIDs || options.uv1 || options.originalIndices) return extract(legacyModule(), bytes, options);
  try {
    modern ??= new Promise((resolve, reject) => {
      const ready = createModernDecoder({
        instantiateWasm: (imports: WebAssembly.Imports, receive: (instance: WebAssembly.Instance, module: WebAssembly.Module) => void) => {
          void fetch(wasmURL).then(async response => {
            if (!response.ok) throw Error('Bundled Draco WASM decoder could not be loaded');
            const bytes = await response.arrayBuffer();
            if (!bytes.byteLength || bytes.byteLength > 8 * 1024 * 1024) throw Error('Bundled Draco WASM exceeds its 8 MiB limit');
            const compiled = await WebAssembly.instantiate(bytes, imports);
            const heaps = Object.values(compiled.instance.exports).filter(value => value instanceof WebAssembly.Memory);
            if (heaps.length !== 1) throw Error('Bundled Draco WASM has an unexpected heap contract');
            boundDecoderHeap(heaps[0] as WebAssembly.Memory);
            receive(compiled.instance, compiled.module);
          }).catch(reject);
          return {};
        }, print: () => {}, printErr: () => {},
      });
      Promise.resolve(ready).then(resolve, reject);
    });
    return extract(await modern, bytes, options);
  } catch {
    // Retain the existing historical-semantic fallback; encoded bytes are never patched.
    return extract(legacyModule(), bytes, options);
  }
};
