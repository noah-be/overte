// SPDX-License-Identifier: Apache-2.0
// Google Draco 1.3.4 preserves historical HFM custom semantics rejected by newer
// decoders. The unmodified, pinned Google codec runs in a bounded worker.
import decoderSource from 'draco3d/draco_decoder_nodejs.js?raw';
import type { DecodedBakedGeometry } from './baked-fbx';
interface Request { bytes: ArrayBuffer; options: { materialIDs: boolean; uv1: boolean; originalIndices: boolean }; resolve: (mesh: DecodedBakedGeometry) => void; reject: (error: Error) => void }
let worker: Worker | undefined, active: Request | undefined, timer: ReturnType<typeof setTimeout> | undefined;
const queue: Request[] = [];
function nativeWorker(): void {
  const draco = (globalThis as any).module.exports({ ENVIRONMENT: 'WORKER', TOTAL_MEMORY: 64 * 1024 * 1024, reallocBuffer: (size: number) => { if (size > 256 * 1024 * 1024) return null; const replacement = new ArrayBuffer(size); new Uint8Array(replacement).set(draco.HEAPU8); return replacement; }, print: () => {}, printErr: () => {} });
  self.onmessage = event => {
    const owned: any[] = [], make = (value: any) => { owned.push(value); return value; };
    try {
      const { bytes, options } = event.data;
      if (!(bytes instanceof ArrayBuffer) || bytes.byteLength > 32 * 1024 * 1024) throw Error('Invalid native Draco input length');
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
      const transfers = Object.values(meshData).filter(value => value !== undefined).map(value => (value as Float32Array | Uint32Array).buffer);
      self.postMessage({ mesh: meshData }, { transfer: transfers });
    } catch (error) { self.postMessage({ error: error instanceof Error ? error.message : String(error) }); }
    finally { for (const value of owned.reverse()) draco.destroy(value); }
  };
}
function finish(error?: Error, mesh?: DecodedBakedGeometry): void {
  clearTimeout(timer); timer = undefined;
  const request = active; active = undefined;
  if (error) request?.reject(error); else if (mesh) request?.resolve(mesh);
  pump();
}
function pump(): void {
  if (active || !queue.length) return;
  if (!worker) {
    const url = URL.createObjectURL(new Blob(['var module={exports:{}};self.module=module;\n', decoderSource, '\n(', nativeWorker.toString(), ')();'], { type: 'text/javascript' }));
    const created = new Worker(url); worker = created; URL.revokeObjectURL(url);
    created.onmessage = event => { if (worker !== created) return; if (event.data.error) { created.terminate(); worker = undefined; } finish(event.data.error ? Error(event.data.error) : undefined, event.data.mesh); };
    created.onerror = event => { if (worker !== created) return; created.terminate(); worker = undefined; finish(Error(event.message || 'Native Draco worker failed')); };
  }
  active = queue.shift();
  timer = setTimeout(() => { worker?.terminate(); worker = undefined; finish(Error('The native Draco decoder exceeded its 30-second limit')); }, 30_000);
  worker.postMessage({ bytes: active!.bytes, options: active!.options }, [active!.bytes]);
}
export function decodeLegacyBakedDraco(bytes: ArrayBuffer, options: Request['options']): Promise<DecodedBakedGeometry> {
  if (queue.length >= 32) return Promise.reject(Error('The native Draco decoder queue is full'));
  if (bytes.byteLength > 32 * 1024 * 1024) return Promise.reject(Error('Invalid native Draco input length'));
  return new Promise((resolve, reject) => { queue.push({ bytes, options, resolve, reject }); pump(); });
}
export function disposeLegacyBakedDraco(): void {
  clearTimeout(timer); timer = undefined; worker?.terminate(); worker = undefined;
  active?.reject(Error('The native Draco decoder was disposed')); active = undefined;
  for (const request of queue.splice(0)) request.reject(Error('The native Draco decoder was disposed'));
}
