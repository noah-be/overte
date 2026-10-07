// SPDX-License-Identifier: Apache-2.0
/** Bound heap growth used by the pinned Emscripten JS decoder wrapper.
 * This is not a general sandbox for arbitrary WebAssembly: the shipped codec
 * grows its exported heap through this JS method, not a guest-supplied module.
 */
export function boundDecoderHeap(memory: WebAssembly.Memory, maximumBytes = 256 * 1024 * 1024): void {
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes <= 0 || maximumBytes % 65536 || memory.buffer.byteLength > maximumBytes) throw Error('Invalid Draco decoder heap limit');
  const grow = memory.grow.bind(memory);
  Object.defineProperty(memory, 'grow', { value: (pages: number) => {
    if (!Number.isSafeInteger(pages) || pages < 0 || pages > (maximumBytes - memory.buffer.byteLength) / 65536) throw new RangeError('Draco decoder heap exceeds its bounded limit');
    return grow(pages);
  } });
}
