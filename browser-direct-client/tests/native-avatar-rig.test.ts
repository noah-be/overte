// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Bone,Group,Quaternion,Vector3} from 'three';
import {AvatarRig} from '../src/avatar-rig.ts';

test('native absolute parent and child rotations become relative bone rotations', () => {
    const model=new Group(),hips=new Bone(),head=new Bone();hips.name='Hips';head.name='Head';
    hips.add(head);model.add(hips);const rig=new AvatarRig(model,'gltf');
    const absolute=new Quaternion().setFromAxisAngle(new Vector3(0,1,0),Math.PI/2);
    const record={x:absolute.x,y:absolute.y,z:absolute.z,w:absolute.w};
    rig.apply({id:'native',position:{x:0,y:0,z:0},jointNames:['Head','Hips'],jointParents:[1,-1],
        jointRotations:[record,record]});
    assert.ok(hips.quaternion.angleTo(absolute)<1e-7);
    assert.ok(head.quaternion.angleTo(new Quaternion())<1e-7,
        'The same absolute rotation on both joints must not be applied twice');
});

test('native default flags restore authored nonidentity rotations and model-unit translations', () => {
    const model=new Group(),hips=new Bone(),head=new Bone();hips.name='Hips';head.name='Head';
    hips.position.set(.25,101,.63);head.position.set(0,60,-.68);
    hips.quaternion.setFromAxisAngle(new Vector3(1,0,0),.35);
    head.quaternion.setFromAxisAngle(new Vector3(0,0,1),.6);head.scale.set(.9,1,.8);
    hips.add(head);model.add(hips);model.userData.unitScaleFactor=1;
    const parentDefault=hips.quaternion.clone(),childDefault=head.quaternion.clone();
    const childAbsolute=parentDefault.clone().multiply(childDefault);
    const record=(q:Quaternion)=>({x:q.x,y:q.y,z:q.z,w:q.w});
    const defaults={jointNames:['Hips','Head'],jointParents:[-1,0],
        jointDefaultRotations:[record(parentDefault),record(childAbsolute)],
        jointDefaultTranslations:[{x:.25,y:101,z:.63},{x:0,y:60,z:-.68}],jointDefaultScales:[100,100]};
    const rig=new AvatarRig(model,'fbx');
    rig.apply({id:'native',position:{x:0,y:0,z:0},...defaults,
        jointRotations:[{x:0,y:1,z:0,w:0},{x:1,y:0,z:0,w:0}],
        jointTranslations:[{x:4,y:99,z:2},{x:1,y:61,z:3}]});
    rig.apply({id:'native',position:{x:0,y:0,z:0},...defaults,
        jointRotations:[null,null],jointTranslations:[null,null]});
    assert.ok(hips.quaternion.angleTo(parentDefault)<1e-7);
    assert.ok(head.quaternion.angleTo(childDefault)<1e-7);
    assert.deepEqual(hips.position.toArray(),[.25,101,.63]);
    assert.deepEqual(head.position.toArray(),[0,60,-.68]);
    assert.deepEqual(head.scale.toArray(),[.9,1,.8],'Native trait scalar scale is not a local bone scale');
    rig.root.updateMatrixWorld(true);
    assert.ok(Math.abs(hips.getWorldPosition(new Vector3()).y)<1e-10);
});

test('known authoring geometry rotation is removed before absolute rig poses reach local bones', () => {
    const model=new Group(),hips=new Bone(),head=new Bone();hips.name='Hips';head.name='Head';
    hips.add(head);model.add(hips);
    const mapping={rotation:{x:0,y:0,z:.4}},rig=new AvatarRig(model,'gltf',mapping);
    const geometry=new Quaternion().setFromAxisAngle(new Vector3(0,0,1),.4);
    const parent=new Quaternion().setFromAxisAngle(new Vector3(1,0,0),.6);
    const child=new Quaternion().setFromAxisAngle(new Vector3(0,1,0),.3);
    const record=(q:Quaternion)=>({x:q.x,y:q.y,z:q.z,w:q.w});
    rig.apply({id:'native',position:{x:0,y:0,z:0},jointNames:['Hips','Head'],jointParents:[-1,0],
        jointRotations:[record(geometry.clone().multiply(parent)),record(geometry.clone().multiply(parent).multiply(child))]});
    assert.ok(hips.quaternion.angleTo(parent)<1e-7);
    assert.ok(head.quaternion.angleTo(child)<1e-7);
});
