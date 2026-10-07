// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {Mesh,type Object3D,type Texture} from 'three';

/** Match FBXSerializer_Material.cpp: nonpositive FBX opacity means opaque. */
export function applyNativeFbxOpacity(model:Object3D):void {
    model.traverse(object=>{
        if (!(object instanceof Mesh)) return;
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
            if (material.opacity<=0) {
                material.opacity=1;
                material.transparent=Boolean((material as typeof material & {alphaMap?:Texture|null}).alphaMap);
                material.needsUpdate=true;
            }
        }
    });
}
