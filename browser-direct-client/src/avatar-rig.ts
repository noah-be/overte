// SPDX-License-Identifier: Apache-2.0
// Modified for Overte direct browser compatibility: convert native absolute
// rig poses to parent-relative model poses and retain authored default flags.
// Copyright 2026 Overte contributors
import {Bone, Group, Light, Quaternion, Vector3, type Object3D} from 'three';
import type {Avatar} from './world-data';
import {quaternion,vector} from './world-data';

export interface AvatarMapping {scale?:number; rotation?:{x:number;y:number;z:number}; root?:string}

/** The native skeleton is rotated 180 degrees and registered at its rest hips. */
export class AvatarRig {
    readonly root = new Group();
    private readonly bones = new Map<string,Bone[]>();
    private readonly defaults = new Map<Object3D,{local:Quaternion;absolute:Quaternion;position:Vector3}>();
    private readonly rigToGeometry = new Quaternion();
    constructor(readonly model:Object3D, format:'fbx'|'gltf'|'obj', mapping:AvatarMapping = {}) {
        model.traverse(object => {
            // The loader's original hierarchy defines absolute model space;
            // an external parse SceneGraph or a later avatar owner is excluded.
            const local=object.quaternion.clone();
            const parentRest=object===model?undefined:this.defaults.get(object.parent!);
            this.defaults.set(object,{local,absolute:parentRest?parentRest.absolute.clone().multiply(local):local.clone(),position:object.position.clone()});
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
        this.rigToGeometry.copy(geometry.quaternion).invert();
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
        const absolute=new Map<Object3D,Quaternion>();
        const driven:Array<{bone:Bone;index:number}>=[];
        for (let index = 0; index < names.length; index++) {
            for (const bone of this.bones.get(names[index]) ?? []) {
                const value=avatar.jointRotations?.[index];
                const valid=value&&[value.x,value.y,value.z,value.w].every(Number.isFinite)
                    &&value.x*value.x+value.y*value.y+value.z*value.z+value.w*value.w>0.000001;
                // Rig::copyJointsFromJointData uses the loaded skeleton's model
                // default for null/invalid rotations, not identity or old pose.
                absolute.set(bone,valid?quaternion(value).premultiply(this.rigToGeometry):this.defaults.get(bone)!.absolute.clone());
                driven.push({bone,index});
            }
        }
        const parentAbsolute=(object:Object3D):Quaternion=>{
            const assigned=absolute.get(object);if(assigned)return assigned;
            const rest=this.defaults.get(object)!;
            const value=object===this.model?rest.local.clone():parentAbsolute(object.parent!).clone().multiply(rest.local);
            absolute.set(object,value);return value;
        };
        for(const {bone,index} of driven){
            const value=absolute.get(bone)!;
            // Native rotations already include every parent. Convert using the
            // actual loaded hierarchy, including fixed FBX intermediary nodes.
            const parent=bone===this.model?new Quaternion():parentAbsolute(bone.parent!);
            bone.quaternion.copy(parent).invert().multiply(value).normalize();
            const translation=avatar.jointTranslations?.[index];
            bone.position.copy(translation&&[translation.x,translation.y,translation.z].every(Number.isFinite)
                ?vector(translation):this.defaults.get(bone)!.position);
            // Translation stays in the original model units. Native defaultScale
            // is a trait scalar, not a local Bone.scale; loaded scales stay intact.
        }
    }
    get boneCount():number { return [...this.bones.values()].reduce((count,bones) => count + bones.length,0); }
    inspect() {
        const joints:Record<string,{orientation:{x:number;y:number;z:number;w:number};position:{x:number;y:number;z:number}}> = {};
        for (const name of ['Hips','Head','LeftArm','RightArm']) {
            const bone = this.bones.get(name)?.[0];
            if (!bone) continue;
            joints[name] = {orientation:{x:bone.quaternion.x,y:bone.quaternion.y,z:bone.quaternion.z,w:bone.quaternion.w},
                position:{x:bone.position.x,y:bone.position.y,z:bone.position.z}};
        }
        return {boneCount:this.boneCount,joints};
    }
    /** Explicit bounded observer only; these are original loader-owned defaults. */
    inspectPoseDefaults(){
        const rotation=(q:Quaternion)=>({x:q.x,y:q.y,z:q.z,w:q.w});
        const joints=[];
        for(const [name,bones] of this.bones){
            const bone=bones[0],rest=this.defaults.get(bone)!;
            if(joints.length===256)break;
            joints.push({name:name.slice(0,128),orientation:rotation(rest.local),absoluteModelOrientation:rotation(rest.absolute),
                position:{x:rest.position.x,y:rest.position.y,z:rest.position.z},scale:{x:bone.scale.x,y:bone.scale.y,z:bone.scale.z}});
        }
        return{rigToModelOrientation:rotation(this.rigToGeometry),translationUnits:'Loaded parent-relative model units',
            boneScales:'Preserved from the loaded model',joints,partial:this.bones.size>256};
    }
}
