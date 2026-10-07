// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import type { Entity } from './world-data';

function geometryDrawRange(value: unknown): value is { start: number; count: number } {
    return Boolean(value && typeof value === 'object' && 'start' in value && 'count' in value
        && typeof value.start === 'number' && typeof value.count === 'number');
}

function safeSource(source: string): string {
    if (source.startsWith('data:')) return `data:${source.slice(5).split(/[;,]/, 1)[0]};[embedded]`;
    if (/^https?:/i.test(source)) {
        try { const url = new URL(source); url.username = ''; url.password = ''; url.search = ''; url.hash = ''; return url.href.slice(0, 2048); }
        catch { return '[invalid URL]'; }
    }
    return source.replace(/[?#].*$/, '').slice(0, 2048);
}

/** Explicit, bounded observation of an already-loaded entity's actual main-view
 * draw submissions. It changes no geometry/material/visibility/camera setting.
 * onAfterRender proves submission, not visibility of every fragment. */
export async function observeEntityRendering(entities: ReadonlyMap<string, Entity>, objects: ReadonlyMap<string, THREE.Group>, camera: THREE.Camera,
    requestedIDs: readonly string[], signal: AbortSignal, assertCurrent: () => void, maximumMs = 2000) {
    if (!Number.isSafeInteger(maximumMs) || maximumMs < 100 || maximumMs > 5000 || !Array.isArray(requestedIDs)
        || requestedIDs.length < 1 || requestedIDs.length > 8 || !requestedIDs.every(id => typeof id === 'string' && id.length <= 128)) throw Error('Invalid entity draw observation bounds');
    signal.throwIfAborted(); assertCurrent();
    const ids = [...new Set(requestedIDs)];
    if (objects.size > 16384) throw Error('Entity draw owner collection exceeds its bound');
    const canonical = (id: string) => id.replace(/[{}]/g, '').toLowerCase();
    const undo: Array<() => void> = [];
    const output = ids.map(id => {
        const ownerID = objects.has(id) ? id : [...objects.keys()].find(key => canonical(key) === canonical(id)) || id;
        const entity = entities.get(ownerID), root = objects.get(ownerID), textures = new Set<THREE.Texture>();
        const value = { id, name: entity?.name?.slice(0, 256), modelURL: entity?.modelURL ? safeSource(entity.modelURL) : undefined, loaded: root?.userData.modelLoaded === true,
            shadersReady: root?.userData.shadersReady === true, ownerVisible: root?.visible === true,
            meshes: 0, triangles: 0, submittedDraws: 0, submittedTriangles: 0, partial: false,
            textures: [] as Array<{ source: string; width: number; height: number; colorSpace: string; type: number }>,
            ownerPosition: root ? { ...root.position } : undefined,
            bounds: undefined as { min: { x: number; y: number; z: number }; max: { x: number; y: number; z: number } } | undefined };
        if (!root) return value;
        root.updateWorldMatrix(true, true);
        const bounds = entity?.type === 'Avatar' ? new THREE.Box3() : new THREE.Box3().setFromObject(root);
        root.traverse(object => {
            if (!(object instanceof THREE.Mesh)) return;
            if (entity?.type === 'Avatar' && object === root.userData.avatarLabel) return;
            if (value.meshes >= 4096) { value.partial = true; return; }
            value.meshes++;
            if (entity?.type === 'Avatar') bounds.union(new THREE.Box3().setFromObject(object));
            const available = object.geometry.index?.count ?? object.geometry.getAttribute('position')?.count ?? 0;
            const first = Math.max(0, object.geometry.drawRange.start), end = Math.min(available, first + object.geometry.drawRange.count);
            value.triangles += Math.max(0, end - first) / 3;
            for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
                for (const item of Object.values(material)) if (item instanceof THREE.Texture) textures.add(item);
            }
            const previous = object.onAfterRender;
            const observer: typeof previous = function (this: THREE.Object3D, renderer, scene, currentCamera, geometry, material, group) {
                previous.call(this, renderer, scene, currentCamera, geometry, material, group);
                if (currentCamera !== camera || signal.aborted || objects.get(ownerID) !== root) return;
                value.submittedDraws++;
                const range = geometryDrawRange(group) ? group : undefined;
                const begin = Math.max(first, range?.start ?? first), finish = Math.min(end, range ? range.start + range.count : end);
                value.submittedTriangles += Math.max(0, finish - begin) / 3;
            };
            object.onAfterRender = observer;
            undo.push(() => { if (object.onAfterRender === observer) object.onAfterRender = previous; });
        });
        if (!bounds.isEmpty()) value.bounds = { min: { ...bounds.min }, max: { ...bounds.max } };
        for (const texture of textures) {
            if (value.textures.length >= 128) { value.partial = true; break; }
            const image = texture.image as { width?: number; height?: number; currentSrc?: string; src?: string } | undefined;
            const source = typeof texture.userData.assetSource === 'string' ? texture.userData.assetSource : image?.currentSrc || image?.src || '';
            value.textures.push({ source: safeSource(source), width: image?.width || 0, height: image?.height || 0,
                colorSpace: texture.colorSpace, type: texture.type });
        }
        return value;
    });
    try {
        await new Promise<void>((resolve, reject) => {
            const cancel = () => { clearTimeout(timer); signal.removeEventListener('abort', cancel); reject(new DOMException('Entity draw observation ended', 'AbortError')); };
            const timer = setTimeout(() => { signal.removeEventListener('abort', cancel); resolve(); }, maximumMs);
            signal.addEventListener('abort', cancel, { once: true }); if (signal.aborted) cancel();
        });
        signal.throwIfAborted(); assertCurrent();
        return { maximumMs, mainViewDrawSubmission: true, provesEveryFragmentVisible: false, entities: output };
    } finally { for (const restore of undo) restore(); }
}
