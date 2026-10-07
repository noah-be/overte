// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Native containment/layering semantics reviewed against EntityItem.cpp.in and
// EntityTreeRenderer.{h,cpp}; native implementations retain Apache-2.0 notices.
import { Vector3 } from 'three';
import { entityTransform, vector, type Entity, type Vec3 } from './world-data';

export type ZoneMode = 'inherit' | 'disabled' | 'enabled';
export interface ZoneSkyboxSelection {
    entity: Entity;
    mode: Exclude<ZoneMode, 'inherit'>;
    source: string;
    color: [number, number, number];
}

export function zoneMode(value: unknown): ZoneMode {
    if (value === 'enabled' || value === 2) return 'enabled';
    if (value === 'disabled' || value === 1) return 'disabled';
    return 'inherit';
}

/** Compound convex hulls need their actual shape model; never pretend their
 * bounding box is equivalent. Native simple volumes are evaluated in the
 * normalized entity frame, including rotation and registration point. */
export function zoneContains(entity: Entity, entities: ReadonlyMap<string, Entity>, point: Vec3): boolean {
    if (entity.type !== 'Zone' || entity.visible === false) return false;
    const dimensions = vector(entity.dimensions, 0.1);
    if (![dimensions.x, dimensions.y, dimensions.z].every(value => Number.isFinite(value) && value > 0)) return false;
    const shape = entity.shapeType ?? 'box';
    if (shape === 'none' || shape === 'compound' || shape === 'simple-compound' || shape === 'static-mesh') return false;
    const transform = entityTransform(entity, entities);
    const registration = vector(entity.registrationPoint, 0.5);
    registration.clampScalar(0, 1);
    const local = vector(point).sub(transform.position).applyQuaternion(transform.rotation.clone().invert()).divide(dimensions)
        .sub(new Vector3(0.5, 0.5, 0.5).sub(registration));
    if (shape === 'sphere' || shape === 'ellipsoid') return local.lengthSq() <= 0.25;
    const cylinders: Record<string, 'x' | 'y' | 'z'> = { 'cylinder-x': 'x', 'cylinder-y': 'y', 'cylinder-z': 'z' };
    const axis = cylinders[shape];
    if (axis) return Math.abs(local[axis]) <= 0.5 && local.lengthSq() - local[axis] * local[axis] <= 0.25;
    if (shape !== 'box') return false;
    return Math.abs(local.x) <= 0.5 && Math.abs(local.y) <= 0.5 && Math.abs(local.z) <= 0.5;
}

/** Native Zones have no arbitrary priority integer. Smaller volumes win;
 * canonical UUID order breaks equal-volume ties consistently between clients.
 * Each component inherits independently from the first non-inherited Zone. */
export function selectZoneSkybox(entities: ReadonlyMap<string, Entity>, point: Vec3): ZoneSkyboxSelection | undefined {
    const volume = (entity: Entity): number => { const size = vector(entity.dimensions, 0.1); return size.x * size.y * size.z; };
    const id = (entity: Entity): string => entity.id.replace(/[{}]/g, '').toLowerCase();
    const ranked = [...entities.values()].filter(entity => zoneContains(entity, entities, point))
        .sort((left, right) => volume(left) - volume(right) || (id(left) < id(right) ? -1 : id(left) > id(right) ? 1 : 0));
    for (const entity of ranked) {
        const mode = zoneMode(entity.skyboxMode);
        if (mode === 'inherit') continue;
        const skybox = entity.skybox && typeof entity.skybox === 'object' ? entity.skybox as Record<string, unknown> : {};
        const source = typeof skybox.url === 'string' ? skybox.url : '';
        const color = skybox.color && typeof skybox.color === 'object' ? skybox.color as Record<string, unknown> : {};
        const channels = ['red', 'green', 'blue'].map(key => typeof color[key] === 'number' && Number.isFinite(color[key])
            ? Math.max(0, Math.min(255, color[key])) / 255 : 0) as [number, number, number];
        return { entity, mode, source, color: channels };
    }
}
