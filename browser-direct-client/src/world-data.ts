// Modified for Overte direct browser compatibility: preserve native joint
// default flags, hierarchy and source defaults at the renderer boundary.
// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { Quaternion, Vector3 } from 'three';

export interface Vec3 { x: number; y: number; z: number }
export interface Quat extends Vec3 { w: number }
export interface Pose { position: Vec3; orientation: Quat; velocity: Vec3 }
export interface Avatar {
  id:string; displayName?:string; position:Vec3; orientation?:Quat; scale?:number;
  skeletonModelURL?:string; skeletonOffset?:Vec3;
  jointNames?:string[]; jointParents?:number[];
  /** Absolute rig-frame rotations; null selects the native skeleton default. */
  jointRotations?:(Quat|null)[];
  /** Parent-relative model units, deliberately independent of world metres. */
  jointTranslations?:(Vec3|null)[];
  jointDefaultRotations?:Quat[]; jointDefaultTranslations?:Vec3[]; jointDefaultScales?:number[];
}
export interface Entity {
  id: string; type: string; name?: string; position?: Vec3; rotation?: Quat;
  localPosition?: Vec3; localRotation?: Quat; parentID?: string;
  dimensions?: Vec3; registrationPoint?: Vec3; visible?: boolean; collisionless?: boolean;
  shapeType?: string; shape?: string; color?: { red: number; green: number; blue: number };
  alpha?: number; unlit?: boolean; modelURL?: string; textures?: string; imageURL?: string;
  materialURL?: string; materialData?: string; parentMaterialName?: string;
  text?: string; textColor?: { red: number; green: number; blue: number };
  href?: string; description?: string; userData?: string;
  [key: string]: unknown;
}
export interface Collider { id: string; center: Vec3; rotation: Quat; half: Vec3 }
export const PLAYER_RADIUS = 0.28;
export const PLAYER_HALF_HEIGHT = 0.85;

/** Return protocol records: THREE.Quaternion serializes as an array rather than an object. */
export function poseRecord(position: Vec3, orientation: Quat, velocity: Vec3): Pose {
  return {
    position: { x: position.x, y: position.y, z: position.z },
    orientation: { x: orientation.x, y: orientation.y, z: orientation.z, w: orientation.w },
    velocity: { x: velocity.x, y: velocity.y, z: velocity.z },
  };
}

export function vector(value: Partial<Vec3> | undefined, fallback = 0): Vector3 {
  return new Vector3(...(['x', 'y', 'z'] as const).map(axis => Number.isFinite(value?.[axis]) ? value![axis]! : fallback) as [number, number, number]);
}
export function quaternion(value?: Quat): Quaternion {
  if (!value || ![value.x, value.y, value.z, value.w].every(Number.isFinite)) return new Quaternion();
  const q = new Quaternion(value.x, value.y, value.z, value.w);
  return q.lengthSq() > 0.000001 ? q.normalize() : new Quaternion();
}
export function entityTransform(entity: Entity, entities: ReadonlyMap<string, Entity>, visited = new Set<string>()): { position: Vector3; rotation: Quaternion } {
  // getEntityProperties returns world position and rotation. Only local-only snapshots need parent composition.
  if (entity.position) return { position: vector(entity.position), rotation: quaternion(entity.rotation) };
  const position = vector(entity.localPosition);
  const rotation = quaternion(entity.localRotation ?? entity.rotation);
  if (!entity.parentID || visited.has(entity.id)) return { position, rotation };
  const parent = entities.get(entity.parentID);
  if (!parent) return { position, rotation };
  visited.add(entity.id);
  const transform = entityTransform(parent, entities, visited);
  position.applyQuaternion(transform.rotation).add(transform.position);
  rotation.premultiply(transform.rotation);
  return { position, rotation };
}
export function entityCollider(entity: Entity, entities: ReadonlyMap<string, Entity>): Collider | undefined {
  if (entity.collisionless || entity.shapeType === 'none' || !['Box', 'Sphere', 'Shape', 'Model'].includes(entity.type)) return;
  const dimensions = vector(entity.dimensions, 1);
  dimensions.set(Math.abs(dimensions.x), Math.abs(dimensions.y), Math.abs(dimensions.z));
  const { position, rotation } = entityTransform(entity, entities);
  const offset = new Vector3(0.5, 0.5, 0.5).sub(vector(entity.registrationPoint, 0.5)).multiply(dimensions);
  position.add(offset.applyQuaternion(rotation));
  return { id: entity.id, center: position, rotation, half: dimensions.multiplyScalar(0.5) };
}

/** Distance to actual oriented bounds, including large floors whose centers are far away. */
export function colliderDistance(position: Vec3, collider: Collider): number {
  const local = vector(position).sub(vector(collider.center)).applyQuaternion(quaternion(collider.rotation).invert());
  return Math.hypot(Math.max(0, Math.abs(local.x) - collider.half.x), Math.max(0, Math.abs(local.y) - collider.half.y), Math.max(0, Math.abs(local.z) - collider.half.z));
}

/** Resolve a vertical character capsule against oriented entity bounds. Models use conservative bounds. */
export function resolveCollision(position: Vec3, collider: Collider): { position: Vec3; normal: Vec3 } | undefined {
  const inverse = quaternion(collider.rotation).invert();
  const local = vector(position).sub(vector(collider.center)).applyQuaternion(inverse);
  const axis = new Vector3(0, PLAYER_HALF_HEIGHT - PLAYER_RADIUS, 0).applyQuaternion(inverse);
  const extent = vector(collider.half).add(new Vector3(Math.abs(axis.x), Math.abs(axis.y), Math.abs(axis.z))).addScalar(PLAYER_RADIUS);
  const depth = [extent.x - Math.abs(local.x), extent.y - Math.abs(local.y), extent.z - Math.abs(local.z)];
  if (depth.some(value => value <= 0)) return;
  const index = depth.indexOf(Math.min(...depth));
  const normal = new Vector3();
  normal.setComponent(index, local.getComponent(index) < 0 ? -1 : 1);
  local.addScaledVector(normal, depth[index] + 0.00001);
  local.applyQuaternion(quaternion(collider.rotation)).add(vector(collider.center));
  normal.applyQuaternion(quaternion(collider.rotation));
  return { position: { x: local.x, y: local.y, z: local.z }, normal: { x: normal.x, y: normal.y, z: normal.z } };
}

/** Shorten a camera boom before real world bounds, including near-plane clearance. */
export function constrainCamera(anchor: Vec3, desired: Vec3, colliders: readonly Collider[], clearance = 0.08): Vector3 {
  const start = vector(anchor), end = vector(desired), direction = end.clone().sub(start);
  let nearest = 1;
  for (const collider of colliders) {
    const inverse = quaternion(collider.rotation).invert();
    const origin = start.clone().sub(vector(collider.center)).applyQuaternion(inverse);
    const ray = direction.clone().applyQuaternion(inverse);
    const half = vector(collider.half).addScalar(clearance);
    let entry = 0, exit = 1;
    for (const axis of ['x', 'y', 'z'] as const) {
      if (Math.abs(ray[axis]) < 0.000001) {
        if (Math.abs(origin[axis]) > half[axis]) { entry = 2; break; }
      } else {
        const a = (-half[axis] - origin[axis]) / ray[axis];
        const b = (half[axis] - origin[axis]) / ray[axis];
        entry = Math.max(entry, Math.min(a, b));
        exit = Math.min(exit, Math.max(a, b));
      }
    }
    if (entry <= exit && entry < nearest) nearest = Math.max(0, entry);
  }
  return start.addScaledVector(direction, nearest);
}

/** Make relative model dependencies resolve against the source asset before the gateway rewrites it. */
export function assetDependency(source: string, dependency: string): string {
  if (/^(?:https?:|atp:|data:|blob:)/i.test(dependency)) return dependency;
  if (/^atp:/i.test(source)) {
    const base = source.slice(4).replace(/^\/\//, '/');
    const path = new URL(dependency, `https://assets.invalid${base.startsWith('/') ? '' : '/'}${base}`).pathname;
    return `atp:${path}`;
  }
  return new URL(dependency, source).href;
}

export type MaterialColor = number[] | { red: number; green: number; blue: number };
export interface MaterialData { cullFaceMode?: string; albedo?: MaterialColor; albedoMap?: string; normalMap?: string; roughness?: number; roughnessMap?: string; metallic?: number; metallicMap?: string; opacity?: number; opacityMap?: string; opacityMapMode?: string; opacityCutoff?: number; emissive?: MaterialColor; emissiveMap?: string; unlit?: boolean; name?: string; model?: string; procedural?: unknown; }

/** Native baked materials encode normalized RGB records; authored materials also use arrays. */
export function materialRGB(value: MaterialColor): [number, number, number] {
  const values = Array.isArray(value) ? value.slice(0, 3) : value && [value.red, value.green, value.blue];
  if (!values || values.length !== 3 || !values.every(channel => typeof channel === 'number' && Number.isFinite(channel) && channel >= 0)) throw new Error('Invalid native material color');
  return values as [number, number, number];
}

export function unsupportedEntityEffects(entity: Entity): string[] {
  const effects: string[] = [];
  if (entity.type === 'Zone') {
    if (entity.skyboxMode === 'enabled') effects.push('zone skybox');
    if (entity.hazeMode === 'enabled') effects.push('zone haze');
  }
  if (entity.userData) {
    try {
      const data = JSON.parse(entity.userData);
      const definition = data?.ProceduralEntity ?? data;
      if (definition && ['shaderUrl', 'vertexShaderURL', 'fragmentShaderURL'].some(key => typeof definition[key] === 'string' && definition[key])) effects.push('procedural shader');
    } catch { /* Other entity user data is optional and unrelated to rendering. */ }
  }
  return effects;
}
export function parseMaterialData(data: string): MaterialData[] {
  const parsed = JSON.parse(data) as { materials?: MaterialData[] | MaterialData };
  if (!parsed || !parsed.materials) throw new Error('Material data has no materials');
  return Array.isArray(parsed.materials) ? parsed.materials : [parsed.materials];
}
