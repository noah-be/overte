// SPDX-License-Identifier: Apache-2.0
// Native FBXSerializer expands each original vertex to all Draco split vertices.
const MAX_VERTICES = 2_000_000;
export interface BakedIndexMap {
    expand(indices: ArrayLike<number>, values: ArrayLike<number>, width: number): { indices: Int32Array; values: Float64Array };
}
export function bakedIndexMap(vertices: number, original?: ArrayLike<number>, budget = { generatedBytes: 0 }): BakedIndexMap {
    if (!Number.isInteger(vertices) || vertices <= 0 || vertices > MAX_VERTICES || (original && original.length !== vertices)) {
        throw Error('Invalid baked deformation vertex count');
    }
    let maximum = vertices - 1;
    if (original) {
        maximum = 0;
        for (let i = 0; i < vertices; i++) {
            const index = original[i];
            if (!Number.isInteger(index) || index < 0 || index >= MAX_VERTICES) throw Error('Invalid baked original vertex index');
            maximum = Math.max(maximum, index);
        }
    }
    const offsets = new Uint32Array(maximum + 2);
    for (let i = 0; i < vertices; i++) offsets[(original ? original[i] : i) + 1]++;
    for (let i = 1; i < offsets.length; i++) offsets[i] += offsets[i - 1];
    const cursor = offsets.slice(), targets = new Uint32Array(vertices);
    for (let i = 0; i < vertices; i++) targets[cursor[original ? original[i] : i]++] = i;
    // Bound the aggregate generated arrays for every cluster and blendshape in
    // this geometry before allocating each result, including repeated weights.
    return { expand(indices, values, width) {
        if (!Number.isInteger(width) || width < 1 || width > 4 || indices.length > MAX_VERTICES || values.length !== indices.length * width) {
            throw Error('Invalid baked deformation array shape');
        }
        let count = 0;
        for (let i = 0; i < indices.length; i++) {
            const index = indices[i];
            if (!Number.isInteger(index) || index < 0 || index >= MAX_VERTICES) throw Error('Invalid baked deformation source index');
            if (index <= maximum) count += offsets[index + 1] - offsets[index];
        }
        budget.generatedBytes += count * (4 + width * 8);
        if (!Number.isSafeInteger(budget.generatedBytes) || budget.generatedBytes > 128 * 1024 * 1024) throw Error('Baked deformation exceeds output limits');
        const expandedIndices = new Int32Array(count), expandedValues = new Float64Array(count * width);
        let out = 0;
        for (let i = 0; i < indices.length; i++) {
            for (let component = 0; component < width; component++) {
                if (!Number.isFinite(values[i * width + component])) throw Error('Non-finite baked deformation value');
            }
            const index = indices[i]; if (index > maximum) continue;
            for (let at = offsets[index]; at < offsets[index + 1]; at++) {
                expandedIndices[out] = targets[at];
                for (let component = 0; component < width; component++) expandedValues[out * width + component] = values[i * width + component];
                out++;
            }
        }
        return { indices: expandedIndices, values: expandedValues };
    } };
}
