// SPDX-License-Identifier: Apache-2.0
// Read actual alpha bytes away from rendering and native-network event loops.
import {WorkerTaskYield} from './worker-task-yield';
const cancelled = new Set<number>();
const processing = new Set<number>();
const controllers = new Map<number,AbortController>();
const worker = self as unknown as { onmessage: ((event: MessageEvent<{ id: number; cancel?: boolean; bitmap?: ImageBitmap }>) => void) | null; postMessage(value: unknown): void };
worker.onmessage = async ({ data }: MessageEvent<{ id: number; cancel?: boolean; bitmap?: ImageBitmap }>) => {
  if (data.cancel) { if (processing.has(data.id)) { cancelled.add(data.id); controllers.get(data.id)?.abort(); } return; }
  const bitmap = data.bitmap;
  if (!bitmap) return;
  processing.add(data.id);
  const controller=new AbortController();controllers.set(data.id,controller);
  const continuation=new WorkerTaskYield({signal:controller.signal});
  let opaque = 0, intermediate = 0;
  try {
    const canvas = new OffscreenCanvas(256, 256);
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw Error('Texture alpha inspection requires a readable 2D canvas');
    for (let y = 0; y < bitmap.height; y += 256) for (let x = 0; x < bitmap.width; x += 256) {
      if (cancelled.has(data.id)) throw Error('Texture alpha inspection cancelled');
      const width = Math.min(256, bitmap.width - x), height = Math.min(256, bitmap.height - y);
      context.clearRect(0, 0, 256, 256);
      context.drawImage(bitmap, x, y, width, height, 0, 0, width, height);
      const bytes = context.getImageData(0, 0, width, height).data;
      for (let at = 3; at < bytes.length; at += 4) {
        if (bytes[at] === 255) opaque++;
        else if (bytes[at] !== 0) intermediate++;
      }
      // Preserve a real cancellable task boundary after each unchanged 256KiB
      // read, without the measured 1.1s/256 tiles timer scheduling delay.
      await continuation.yield();
    }
    worker.postMessage({ id: data.id, total: bitmap.width * bitmap.height, opaque, intermediate });
  } catch (error) {
    worker.postMessage({ id: data.id, error: error instanceof Error ? error.message : 'Texture alpha bytes could not be read' });
  } finally { continuation.close();bitmap.close(); cancelled.delete(data.id); processing.delete(data.id); controllers.delete(data.id); }
};
