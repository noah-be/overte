// SPDX-License-Identifier: Apache-2.0
// Full binary/native-material preparation stays off the visitor's render thread.
import { adaptBakedFbx, normalizeNativeFbxTransparency, extractEmbeddedFbxImages } from './baked-fbx';
import { decodePreparedBakedDraco } from './model-fbx-decoder';

interface Request { type: 'prepare' | 'cancel'; id: number; buffer?: ArrayBuffer }
const scope = self as unknown as { onmessage: ((event: MessageEvent<Request>) => void) | null; postMessage(value: unknown, transfer: Transferable[]): void };
let active: { id: number; cancelled: boolean } | undefined;
scope.onmessage = async ({ data }) => {
  if (!data || !Number.isSafeInteger(data.id) || data.id <= 0) return;
  if (data.type === 'cancel') {
    if (active?.id === data.id) { active.cancelled = true; }
    return;
  }
  if (data.type !== 'prepare') return;
  if (active || !(data.buffer instanceof ArrayBuffer) || data.buffer.byteLength <= 0 || data.buffer.byteLength > 32 * 1024 * 1024) {
    scope.postMessage({ id: data.id, error: 'Invalid or overlapping FBX preparation request' }, []); return;
  }
  const owned = { id: data.id, cancelled: false }; active = owned;
  try {
    const normalizeStarted = performance.now();
    const normalized = normalizeNativeFbxTransparency(data.buffer);
    const materialBindingsMs = performance.now() - normalizeStarted;
    if (owned.cancelled) return;
    scope.postMessage({id:owned.id,type:'decodeStarted'},[]);
    const decodeStarted = performance.now();
    const embedded=await extractEmbeddedFbxImages(normalized);
    if(owned.cancelled||active!==owned)return;
    const buffer = await adaptBakedFbx(embedded.buffer, decodePreparedBakedDraco);
    const decodeMs = performance.now() - decodeStarted;
    if (owned.cancelled || active !== owned) return;
    if (buffer.byteLength+embedded.counts.rawBytes > 256 * 1024 * 1024) throw Error('Prepared FBX exceeds the 256 MiB output limit');
    scope.postMessage({ id: owned.id, buffer, embeddedImages:embedded.images, embeddedCounts:embedded.counts, phases: { materialBindingsMs, decodeMs } }, [buffer,...embedded.images.map(image=>image.bytes)]);
  } catch (error) {
    if (!owned.cancelled && active === owned) scope.postMessage({ id: owned.id, error: error instanceof Error ? error.message.slice(0, 8192) : 'Native FBX preparation failed' }, []);
  } finally { if (active === owned) active = undefined; }
};
