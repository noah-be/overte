// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { Bone, type Object3D } from 'three';
import type { AvatarRig } from './avatar-rig';
import type { Avatar, Vec3, Quat } from './world-data';

const point = (value: Vec3 | null | undefined) => value === null ? null : value ? { x: value.x, y: value.y, z: value.z } : undefined;
const rotation = (value: Quat | null | undefined) => value === null ? null : value ? { x: value.x, y: value.y, z: value.z, w: value.w } : undefined;

/** Read current source pose and real local bone transforms without changing
 * animation, matrices, material, camera or native state. Explicit observer only. */
export function captureAvatarPoseEvidence(owner: Object3D, rig: AvatarRig | undefined, avatar: Avatar | undefined) {
    const joints: Array<{ name: string; parent: string; position: Vec3; orientation: Quat }> = [];
    const stack: Object3D[] = rig ? [rig.model] : [];
    let nodes = 0, omitted = false;
    while (stack.length && nodes < 4096) {
        const object = stack.pop()!; nodes++;
        if (object instanceof Bone) {
            if (joints.length < 256) joints.push({ name: String(object.userData.originalName || object.name).slice(0, 128),
                parent: String(object.parent?.userData.originalName || object.parent?.name || '').slice(0, 128),
                position: point(object.position)!, orientation: rotation(object.quaternion)! });
            else omitted = true;
        }
        const available = 4096 - nodes - stack.length;
        if (object.children.length > available) omitted = true;
        for (const child of object.children.slice(0, Math.max(0, available))) stack.push(child);
    }
    return { capture: 'Before the explicit main-view draw observation',
        ownerPosition: point(owner.position), ownerOrientation: rotation(owner.quaternion), ownerScale: point(owner.scale),
        rigPosition: point(rig?.root.position), rigOrientation: rotation(rig?.root.quaternion),
        authoredDefaults: rig?.inspectPoseDefaults(),
        network: avatar ? { position: point(avatar.position), orientation: rotation(avatar.orientation),
            skeletonOffset: point(avatar.skeletonOffset), jointNames: avatar.jointNames?.slice(0, 256).map(name => name.slice(0, 128)),
            jointParents: avatar.jointParents?.slice(0, 256),
            jointRotations: avatar.jointRotations?.slice(0, 256).map(rotation), jointTranslations: avatar.jointTranslations?.slice(0, 256).map(point),
            jointDefaultRotations: avatar.jointDefaultRotations?.slice(0, 256).map(rotation),
            jointDefaultTranslations: avatar.jointDefaultTranslations?.slice(0, 256).map(point),
            jointDefaultScales: avatar.jointDefaultScales?.slice(0, 256) } : undefined,
        joints, partial: omitted || stack.length > 0 || (avatar?.jointNames?.length || 0) > 256,
        limits: { nodes: 4096, joints: 256, nameCharacters: 128 } };
}
