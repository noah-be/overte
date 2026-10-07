// SPDX-License-Identifier: Apache-2.0
import {
    BufferAttribute, BufferGeometry, Material, Matrix4, Mesh, Object3D,
    MeshBasicMaterial, MeshLambertMaterial, MeshPhongMaterial, MeshStandardMaterial,
    type MeshPhysicalMaterial,
} from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { hasNativeAlphaShader } from './native-alpha-material';
import { hasNativeZeroLightShader } from './native-zero-lights';

interface Part { mesh: Mesh; material: Material; start: number; count: number; transform: Matrix4; key: string }
export interface StaticModelBatch {
    readonly savedDrawCalls: number;
    readonly batches: readonly Mesh[];
    readonly generatedBytes: number;
    restore(): void;
}
const allowedAttributes = new Set(['position', 'normal', 'tangent', 'uv', 'uv1', 'uv2', 'color']);
const MAX_PARTS = 10_000, MAX_VERTICES = 2_000_000, MAX_BYTES = 128 * 1024 * 1024;
function supportedMaterial(material: Material): boolean {
    return (material instanceof MeshBasicMaterial || material instanceof MeshLambertMaterial || material instanceof MeshPhongMaterial || material instanceof MeshStandardMaterial)
        && !material.alphaHash
        && !(material as MeshPhysicalMaterial).transmission
        && (material.onBeforeCompile === Material.prototype.onBeforeCompile
            && material.customProgramCacheKey === Material.prototype.customProgramCacheKey
            || hasNativeAlphaShader(material) || hasNativeZeroLightShader(material));
}
function eligibleMaterial(material: Material): boolean {
    return supportedMaterial(material) && material.visible && !material.transparent && material.opacity === 1;
}
function eligibleMesh(mesh: Mesh, root: Object3D): Part[] {
    if (mesh === root || mesh.userData.browserStaticBatch || (mesh as Mesh & { isSkinnedMesh?: boolean }).isSkinnedMesh
        || (mesh as Mesh & { isInstancedMesh?: boolean }).isInstancedMesh
        || (mesh as Mesh & { isBatchedMesh?: boolean }).isBatchedMesh
        || mesh.onBeforeRender !== Object3D.prototype.onBeforeRender || mesh.onAfterRender !== Object3D.prototype.onAfterRender
        || mesh.morphTargetInfluences?.length || Object.values(mesh.geometry.morphAttributes).some(values => values?.length)) return [];
    for (let parent: Object3D | null = mesh; parent && parent !== root; parent = parent.parent) {
        if (!parent.visible || (parent !== mesh && parent.renderOrder !== 0)) return [];
    }
    const attributes = Object.entries(mesh.geometry.attributes).sort(([a], [b]) => a.localeCompare(b));
    const position = mesh.geometry.getAttribute('position');
    if (!position || position.itemSize !== 3 || attributes.some(([name, attribute]) => !allowedAttributes.has(name)
        || attribute.count !== position.count || attribute.itemSize < 1 || attribute.itemSize > 4)) return [];
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    if (!materials.length || materials.some(material => !supportedMaterial(material))) return [];
    const transform = root.matrixWorld.clone().invert().multiply(mesh.matrixWorld);
    // Keep mirrored or singular child transforms on the original path. Baking
    // them would require changing front-face winding and tangent handedness.
    if (!transform.elements.every(Number.isFinite) || transform.determinant() <= 1e-12) return [];
    const indexCount = mesh.geometry.index?.count ?? position.count;
    const draw = mesh.geometry.drawRange;
    const start = Math.max(0, draw.start), end = Math.min(indexCount, draw.start + draw.count);
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start % 3 || end % 3 || start > end) return [];
    const groups = Array.isArray(mesh.material) ? mesh.geometry.groups : [{ start, count: end - start, materialIndex: 0 }];
    const layout = attributes.map(([name, attribute]) => `${name}:${attribute.itemSize}`).join(',');
    const key = [layout, mesh.layers.mask, mesh.renderOrder, mesh.castShadow, mesh.receiveShadow, mesh.frustumCulled].join('|');
    const parts: Part[] = [];
    for (const group of groups) {
        const first = Math.max(start, group.start), last = Math.min(end, group.start + group.count);
        const material = materials[group.materialIndex ?? 0];
        if (!material || !Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first % 3 || last % 3) return [];
        if (last > first && eligibleMaterial(material)) parts.push({ mesh, material, start: first, count: last - first, transform, key });
    }
    return parts;
}
function geometryFor(part: Part): BufferGeometry {
    const source = part.mesh.geometry, geometry = new BufferGeometry();
    for (const [name, attribute] of Object.entries(source.attributes)) {
        const data = new Float32Array(part.count * attribute.itemSize);
        for (let at = 0; at < part.count; at++) {
            const index = source.index ? source.index.getX(part.start + at) : part.start + at;
            if (!Number.isSafeInteger(index) || index < 0 || index >= attribute.count) throw Error('Invalid static model batch index');
            for (let component = 0; component < attribute.itemSize; component++) {
                const value = attribute.getComponent(index, component);
                if (!Number.isFinite(value)) throw Error('Non-finite static model batch attribute');
                data[at * attribute.itemSize + component] = value;
            }
        }
        geometry.setAttribute(name, new BufferAttribute(data, attribute.itemSize));
    }
    geometry.applyMatrix4(part.transform);
    return geometry;
}
export interface StaticModelBatchInspection {
    readonly sourceDrawCalls: number;
    readonly batchedDrawCalls: number;
    readonly savedDrawCalls: number;
    readonly generatedBytes: number;
    readonly withinBudget: boolean;
}
function collectParts(root: Object3D) {
    const byMaterial = new Map<Material, Map<string, Part[]>>();
    const residuals = new Map<Mesh, BufferGeometry['groups']>();
    let partCount = 0, vertices = 0, bytes = 0;
    root.traverse(object => {
        if (!(object instanceof Mesh)) return;
        const meshParts = eligibleMesh(object, root);
        if (meshParts.length && Array.isArray(object.material)) {
            const materials: Material[] = object.material;
            const source: BufferGeometry = object.geometry;
            const residual = source.groups.filter(group => !eligibleMaterial(materials[group.materialIndex ?? 0]));
            if (residual.length) {
                residuals.set(object, residual);
                vertices += source.getAttribute('position').count;
                bytes += Object.values(source.attributes).reduce((sum, attribute) => sum + ('data' in attribute ? attribute.data.array.byteLength : attribute.array.byteLength), 0) + (source.index?.array.byteLength ?? 0);
            }
        }
        for (const part of meshParts) {
            partCount++; vertices += part.count;
            bytes += part.count * Object.values(part.mesh.geometry.attributes).reduce((sum, attribute) => sum + attribute.itemSize * 4, 0);
            const layouts = byMaterial.get(part.material) ?? new Map<string, Part[]>();
            const group = layouts.get(part.key) ?? []; group.push(part); layouts.set(part.key, group); byMaterial.set(part.material, layouts);
        }
    });
    const groups = [...byMaterial.values()].flatMap(layouts => [...layouts.values()]);
    const savedDrawCalls = partCount - groups.length;
    return { groups, partCount, vertices, bytes, savedDrawCalls, residuals };
}
/** Inspect the exact optimization buckets without changing visibility, hierarchy,
 * materials or geometry. Matrix updates match normal Three world traversal. */
export function inspectStaticModel(root: Object3D, options: { materialChildren?: boolean } = {}): StaticModelBatchInspection {
    let animated = false; root.traverse(object => { if (object.animations.length) animated = true; });
    if (options.materialChildren || animated) return { sourceDrawCalls: 0, batchedDrawCalls: 0, savedDrawCalls: 0, generatedBytes: 0, withinBudget: true };
    root.updateWorldMatrix(true, true);
    const { groups, partCount, vertices, bytes, savedDrawCalls } = collectParts(root);
    const withinBudget = partCount <= MAX_PARTS && vertices <= MAX_VERTICES && bytes <= MAX_BYTES;
    return { sourceDrawCalls: partCount, batchedDrawCalls: withinBudget ? groups.length : partCount, savedDrawCalls: withinBudget ? savedDrawCalls : 0, generatedBytes: bytes, withinBudget };
}
/** Merge only compatible opaque parts sharing the exact material object.
 * Originals remain available for native material selectors and collision data.
 * Mixed groups keep their original Mesh identity/transform/material array and
 * exact transparent group order, with a reversible cloned residual geometry.
 * This preserves Three's transparent depth + original object-ID tie breaking.
 * Source geometry bytes remain intact; collision reads full unchanged indices.
 * Call restore() before material attachment/edit or disposing/replacing the model.
 */
export function batchStaticModel(root: Object3D, options: { materialChildren?: boolean } = {}): StaticModelBatch {
    const empty: StaticModelBatch = { savedDrawCalls: 0, batches: [], generatedBytes: 0, restore() {} };
    if (options.materialChildren) return empty;
    let animated = false;
    root.traverse(object => { if (object.animations.length) animated = true; });
    if (animated) return empty;
    root.updateWorldMatrix(true, true);
    const { groups, partCount, vertices, bytes, savedDrawCalls, residuals } = collectParts(root);
    if (!savedDrawCalls || partCount > MAX_PARTS || vertices > MAX_VERTICES || bytes > MAX_BYTES) return empty;
    const batches: Mesh[] = [], originals = new Map<Mesh, { visible: boolean; geometry: BufferGeometry }>();
    const residualGeometry = new Map<Mesh, BufferGeometry>();
    try {
        for (const parts of groups) {
            const inputs: BufferGeometry[] = [];
            let geometry: BufferGeometry | null;
            try { for (const part of parts) inputs.push(geometryFor(part)); geometry = mergeGeometries(inputs); }
            finally { for (const input of inputs) input.dispose(); }
            if (!geometry) throw Error('Incompatible static model batch geometry');
            geometry.computeBoundingBox(); geometry.computeBoundingSphere();
            const sample = parts[0].mesh, batch = new Mesh(geometry, parts[0].material);
            batch.userData.browserStaticBatch = true;
            batch.layers.mask = sample.layers.mask; batch.renderOrder = sample.renderOrder;
            batch.castShadow = sample.castShadow; batch.receiveShadow = sample.receiveShadow; batch.frustumCulled = sample.frustumCulled;
            batches.push(batch);
            for (const part of parts) originals.set(part.mesh, { visible: part.mesh.visible, geometry: part.mesh.geometry });
        }
        for (const [mesh, groups] of residuals) {
            const geometry = mesh.geometry.clone();
            geometry.clearGroups();
            for (const group of groups) geometry.addGroup(group.start, group.count, group.materialIndex);
            residualGeometry.set(mesh, geometry);
        }
    } catch {
        // Optimization is optional: invalid/uncertain content retains the actual
        // original render path and never leaves a partial transformed scene.
        for (const batch of batches) batch.geometry.dispose();
        for (const geometry of residualGeometry.values()) geometry.dispose();
        return empty;
    }
    for (const mesh of originals.keys()) {
        const residual = residualGeometry.get(mesh);
        if (residual) mesh.geometry = residual;
        else mesh.visible = false;
    }
    for (const batch of batches) root.add(batch);
    let restored = false;
    return { savedDrawCalls, batches, generatedBytes: bytes, restore() {
        if (restored) return; restored = true;
        for (const [mesh, original] of originals) { mesh.visible = original.visible; mesh.geometry = original.geometry; }
        for (const geometry of residualGeometry.values()) geometry.dispose();
        for (const batch of batches) { root.remove(batch); batch.geometry.dispose(); }
    } };
}
