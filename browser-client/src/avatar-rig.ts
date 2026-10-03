// SPDX-License-Identifier: Apache-2.0
import {Bone, Group, Light, Vector3, type Object3D} from 'three';
import type {Avatar} from './world-data';
import {quaternion,vector} from './world-data';

export interface AvatarMapping {scale?:number; rotation?:{x:number;y:number;z:number}; root?:string}

/** The native skeleton is rotated 180 degrees and registered at its rest hips. */
export class AvatarRig {
    readonly root = new Group();
    private readonly bones = new Map<string,Bone[]>();
    constructor(readonly model:Object3D, format:'fbx'|'gltf'|'obj', mapping:AvatarMapping = {}) {
        model.traverse(object => {
            if (object instanceof Light) object.visible = false;
            if (!(object instanceof Bone)) return;
            // FBXLoader retains unsanitized names separately from animation-safe names.
            const name = String(object.userData.originalName || object.name);
            // Shared face/body clusters have an identity binding child carrying
            // the same FBX model ID. Its parent's pose already moves it; writing
            // the same native local transform twice would deform both skins.
            const parent = object.parent;
            const id = (object as Bone & {ID?:number}).ID;
            if (format === 'fbx' && parent instanceof Bone && id !== undefined
                && id === (parent as Bone & {ID?:number}).ID && !object.userData.transformData) return;
            const matches = this.bones.get(name) ?? [];
            matches.push(object); this.bones.set(name,matches);
        });
        const geometry = new Group();
        const scale = Number.isFinite(mapping.scale) && mapping.scale! > 0 ? mapping.scale! : 1;
        const units = format === 'fbx' ? Number(model.userData.unitScaleFactor ?? 1) * .01 : 1;
        if (!Number.isFinite(units) || units <= 0 || units * scale > 1000) throw Error('Unsupported avatar model units');
        geometry.scale.setScalar(units * scale);
        if (mapping.rotation) geometry.rotation.set(mapping.rotation.x,mapping.rotation.y,mapping.rotation.z);
        model.updateMatrixWorld(true);
        const hips = this.bones.get(mapping.root || 'Hips')?.[0];
        if (hips) {
            const registration = hips.getWorldPosition(new Vector3());
            geometry.position.copy(registration).applyQuaternion(geometry.quaternion).multiplyScalar(-units * scale);
        }
        geometry.add(model); this.root.add(geometry);
        this.root.rotation.y = Math.PI;
    }
    apply(avatar:Avatar):void {
        this.root.position.copy(vector(avatar.skeletonOffset)).applyAxisAngle(new Vector3(0,1,0),Math.PI);
        const names = avatar.jointNames;
        if (!names) return;
        for (let index = 0; index < names.length; index++) {
            for (const bone of this.bones.get(names[index]) ?? []) {
                if (avatar.jointRotations?.[index]) bone.quaternion.copy(quaternion(avatar.jointRotations[index]));
                if (avatar.jointTranslations?.[index]) bone.position.copy(vector(avatar.jointTranslations[index]));
            }
        }
    }
    get boneCount():number { return [...this.bones.values()].reduce((count,bones) => count + bones.length,0); }
    inspect() {
        const joints:Record<string,{orientation:{x:number;y:number;z:number;w:number};position:{x:number;y:number;z:number}}> = {};
        for (const name of ['Hips','Head','LeftArm','RightArm','LeftUpLeg','RightUpLeg','LeftLeg','RightLeg','LeftFoot','RightFoot']) {
            const bone = this.bones.get(name)?.[0];
            if (!bone) continue;
            joints[name] = {orientation:{x:bone.quaternion.x,y:bone.quaternion.y,z:bone.quaternion.z,w:bone.quaternion.w},
                position:{x:bone.position.x,y:bone.position.y,z:bone.position.z}};
        }
        return {boneCount:this.boneCount,joints};
    }
}
