// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    AnimationClip, BatchedMesh, BufferAttribute, BufferGeometry, Group, InstancedMesh, Matrix3, Matrix4, Mesh, MeshBasicMaterial,
    MeshStandardMaterial, ShaderMaterial, SkinnedMesh, Texture, Vector3,
} from 'three';
import { batchStaticModel, inspectStaticModel } from '../src/static-model-batch';
import { applyNativeMaterialAlpha, cloneNativeMaterial } from '../src/native-alpha-material';

function geometry(): BufferGeometry {
    const result = new BufferGeometry();
    result.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3));
    result.setAttribute('normal', new BufferAttribute(new Float32Array([Math.SQRT1_2, 0, Math.SQRT1_2, Math.SQRT1_2, 0, Math.SQRT1_2, Math.SQRT1_2, 0, Math.SQRT1_2]), 3));
    result.setAttribute('uv', new BufferAttribute(new Float32Array([0, 0, 1, 0, 0, 1]), 2));
    result.setIndex([0, 1, 2]); return result;
}
function fixture(): { root: Group; meshes: Mesh[]; material: MeshBasicMaterial } {
    const root = new Group(); root.position.set(154, -98, -397); root.rotation.y = .7;
    const material = new MeshBasicMaterial({ color: 0x22cc88 });
    const meshes = [new Mesh(geometry(), material), new Mesh(geometry(), material), new Mesh(geometry(), material)];
    const parent = new Group(); parent.position.set(0, 2, 1); parent.rotation.z = .4;
    parent.add(meshes[0], meshes[1]); meshes[0].position.x = -2; meshes[1].position.x = 1; meshes[1].scale.set(2, 1, 1);
    root.add(parent, meshes[2]); meshes[2].position.set(2, -1, 0); root.updateMatrixWorld(true);
    return { root, meshes, material };
}
function worldCorners(meshes: readonly Mesh[]): string[] {
    const result: string[] = [];
    for (const mesh of meshes) {
        const geometry = mesh.geometry, position = geometry.getAttribute('position'), uv = geometry.getAttribute('uv'), normal = geometry.getAttribute('normal');
        const count = geometry.index?.count ?? position.count;
        for (let i = 0; i < count; i++) {
            const index = geometry.index?.getX(i) ?? i;
            const p = new Vector3().fromBufferAttribute(position, index).applyMatrix4(mesh.matrixWorld);
            const n = new Vector3().fromBufferAttribute(normal, index).applyNormalMatrix(new Matrix3().getNormalMatrix(mesh.matrixWorld));
            result.push(JSON.stringify({ p: p.toArray().map(x => Math.round(x * 1e4)), n: n.toArray().map(x => Math.round(x * 1e4)), uv: [uv.getX(index), uv.getY(index)] }));
        }
    }
    return result;
}
test('same-material static batches preserve actual world winding, UVs, normals, hierarchy and reversible selectors', () => {
    const { root, meshes, material } = fixture();
    const before = worldCorners(meshes), parents = meshes.map(mesh => mesh.parent), sourceGeometry = meshes.map(mesh => mesh.geometry);
    let materialDisposals = 0, generatedDisposals = 0; material.addEventListener('dispose', () => materialDisposals++);
    const result = batchStaticModel(root);
    assert.equal(result.savedDrawCalls, 2); assert.equal(result.batches.length, 1);
    root.updateMatrixWorld(true);
    assert.deepEqual(worldCorners(result.batches), before);
    assert.ok(meshes.every(mesh => !mesh.visible));
    assert.equal(result.batches[0].material, material);
    assert.equal(result.batches[0].userData.browserStaticBatch, true);
    for (const batch of result.batches) batch.geometry.addEventListener('dispose', () => generatedDisposals++);
    assert.deepEqual(meshes.map(mesh => mesh.parent), parents);
    assert.deepEqual(meshes.map(mesh => mesh.geometry), sourceGeometry);
    result.restore(); result.restore();
    assert.ok(meshes.every(mesh => mesh.visible)); assert.equal(generatedDisposals, 1); assert.equal(materialDisposals, 0);
    assert.ok(result.batches.every(batch => !batch.parent));
});
test('different material identities and incompatible layouts stay distinct even when materials look equal', () => {
    const { root, meshes, material } = fixture();
    meshes[2].material = material.clone();
    const result = batchStaticModel(root);
    assert.equal(result.savedDrawCalls, 1); assert.equal(result.batches.length, 2);
    assert.ok(result.batches.some(batch => batch.material === meshes[2].material)); result.restore();
    meshes[1].geometry.deleteAttribute('normal');
    assert.equal(batchStaticModel(root).savedDrawCalls, 0);
});
test('uncertain native material, animation, skin, morph, mirror and callback semantics retain original meshes', () => {
    const mutations: ((root: Group, meshes: Mesh[]) => void)[] = [
        (_, meshes) => { meshes.forEach(mesh => { mesh.material = new MeshStandardMaterial({ transparent: true, opacity: .5 }); }); },
        (_, meshes) => { meshes.forEach(mesh => { mesh.material = new ShaderMaterial(); }); },
        (root) => { root.animations.push(new AnimationClip('Actual animation', 1, [])); },
        (_, meshes) => { meshes.forEach(mesh => { mesh.geometry.morphAttributes.position = [mesh.geometry.attributes.position]; }); },
        (_, meshes) => { meshes.forEach(mesh => { mesh.scale.x = -1; }); },
        (_, meshes) => { meshes.forEach(mesh => { mesh.onBeforeRender = () => {}; }); },
    ];
    for (const mutate of mutations) {
        const { root, meshes } = fixture(); mutate(root, meshes);
        assert.equal(batchStaticModel(root).savedDrawCalls, 0); assert.ok(meshes.every(mesh => mesh.visible));
    }
    const { root, meshes } = fixture();
    assert.equal(batchStaticModel(root, { materialChildren: true }).savedDrawCalls, 0); assert.ok(meshes.every(mesh => mesh.visible));
    const skin = new SkinnedMesh(geometry(), meshes[0].material); root.add(skin); meshes[0].visible = meshes[1].visible = false;
    assert.equal(batchStaticModel(root).savedDrawCalls, 0);
});
test('geometry corruption cannot leave hidden originals or a partial generated scene', () => {
    const { root, meshes } = fixture(); meshes[1].geometry.getAttribute('position').setX(0, NaN);
    assert.equal(batchStaticModel(root).savedDrawCalls, 0); assert.ok(meshes.every(mesh => mesh.visible));
    assert.equal(root.children.length, 2);
});

test('readonly candidate inspection uses exactly the render buckets and keeps source selectors intact', () => {
    const { root, meshes } = fixture();
    const children = [...root.children], parents = meshes.map(mesh => mesh.parent), geometry = meshes.map(mesh => mesh.geometry);
    const inspection = inspectStaticModel(root);
    assert.equal(inspection.sourceDrawCalls, 3); assert.equal(inspection.batchedDrawCalls, 1); assert.equal(inspection.savedDrawCalls, 2);
    assert.ok(inspection.withinBudget && inspection.generatedBytes > 0);
    assert.ok(meshes.every(mesh => mesh.visible)); assert.deepEqual(root.children, children);
    assert.deepEqual(meshes.map(mesh => mesh.parent), parents); assert.deepEqual(meshes.map(mesh => mesh.geometry), geometry);
    const batch = batchStaticModel(root); assert.equal(batch.savedDrawCalls, inspection.savedDrawCalls);
    assert.equal(batch.generatedBytes, inspection.generatedBytes); batch.restore();
});

test('native material groups, clipped draw ranges, tangents and normalized secondary UVs preserve each oriented corner', () => {
    const root = new Group(), red = new MeshBasicMaterial({ color: 0xaa2200 }), blue = new MeshBasicMaterial({ color: 0x0022aa });
    const source = new BufferGeometry();
    source.setAttribute('position', new BufferAttribute(new Float32Array([0,0,0, 1,0,0, 0,1,0, 2,0,0, 3,0,0, 2,1,0]),3));
    source.setAttribute('normal', new BufferAttribute(new Float32Array([0,0,1, 0,0,1, 0,0,1, 0,0,1, 0,0,1, 0,0,1]),3));
    source.setAttribute('tangent', new BufferAttribute(new Float32Array(Array.from({length:6},()=>[1,0,0,-1]).flat()),4));
    source.setAttribute('uv2', new BufferAttribute(new Uint8Array([0,0, 255,0, 0,255, 0,0, 255,0, 0,255]),2,true));
    source.setIndex([0,1,2,3,4,5,0,1,2]);source.addGroup(0,3,0);source.addGroup(3,3,1);source.addGroup(6,3,0);source.setDrawRange(0,6);
    const meshes=[new Mesh(source,[red,blue]),new Mesh(source,[red,blue])];meshes[1].position.set(10,0,0);root.add(...meshes);
    const result=batchStaticModel(root);assert.equal(result.savedDrawCalls,2);assert.equal(result.batches.length,2);
    assert.equal(result.batches.reduce((sum,mesh)=>sum+mesh.geometry.attributes.position.count,0),12);
    for(const batch of result.batches){
        const uv=batch.geometry.getAttribute('uv2'),tangent=batch.geometry.getAttribute('tangent');
        assert.deepEqual(Array.from({length:uv.count},(_,index)=>[uv.getX(index),uv.getY(index)]),[[0,0],[1,0],[0,1],[0,0],[1,0],[0,1]]);
        assert.ok(Array.from({length:tangent.count},(_,index)=>tangent.getW(index)).every(value=>value===-1));
        assert.ok([red,blue].includes(batch.material as MeshBasicMaterial));
    }
    result.restore();assert.deepEqual(source.groups.map(group=>group.materialIndex),[0,1,0]);assert.equal(source.drawRange.count,6);
});

test('native instanced and already batched meshes retain all instance transforms and original draw semantics', () => {
    const { root, material } = fixture();
    const instances = new InstancedMesh(geometry(), material, 2);
    instances.setMatrixAt(0, new Matrix4().makeTranslation(4,5,6)); instances.setMatrixAt(1, new Matrix4().makeTranslation(7,8,9));
    const batched = new BatchedMesh(2, 6, 6, material); const geometryID = batched.addGeometry(geometry());
    const instanceID = batched.addInstance(geometryID); batched.setMatrixAt(instanceID, new Matrix4().makeTranslation(10,11,12));
    root.add(instances, batched);
    const inspection = inspectStaticModel(root); assert.equal(inspection.sourceDrawCalls,3);
    const result = batchStaticModel(root); assert.equal(result.savedDrawCalls,2);
    assert.ok(instances.visible && batched.visible); assert.equal(instances.count,2);
    const transform = new Matrix4(); instances.getMatrixAt(1,transform); assert.deepEqual(transform.elements.slice(12,15),[7,8,9]);
    batched.getMatrixAt(instanceID,transform); assert.deepEqual(transform.elements.slice(12,15),[10,11,12]);
    result.restore();
});

test('mixed opacity groups keep the original Mesh identity and full collision geometry while saving only opaque calls',()=>{
    const root=new Group(),material=new MeshBasicMaterial(),glass=new MeshBasicMaterial({transparent:true,opacity:.2805755138397217});
    const source=geometry();source.setIndex([0,1,2,0,1,2,0,1,2]);source.addGroup(0,3,0);source.addGroup(3,3,1);source.addGroup(6,3,0);
    const original=new Mesh(source,[material,glass]);const id=original.id,indices=Array.from(source.index!.array),groups=source.groups.map(group=>({...group}));root.add(original);
    const inspection=inspectStaticModel(root);const result=batchStaticModel(root);assert.equal(result.savedDrawCalls,1);assert.equal(inspection.generatedBytes,result.generatedBytes);
    assert.equal(original.id,id);assert.equal(original.parent,root);assert.ok(original.visible);assert.notEqual(original.geometry,source);
    assert.deepEqual(original.geometry.groups,[{start:3,count:3,materialIndex:1}]);assert.deepEqual(Array.from(original.geometry.index!.array),indices);
    assert.deepEqual(source.groups,groups);assert.equal(original.material[1],glass);
    let disposal=0;original.geometry.addEventListener('dispose',()=>disposal++);
    result.restore();result.restore();assert.equal(original.geometry,source);assert.deepEqual(source.groups,groups);assert.equal(disposal,1);
});

test('a failed residual clone disposes earlier generated geometry and leaves every original reference visible',()=>{
    const root=new Group(),opaque=new MeshBasicMaterial(),transparent=new MeshBasicMaterial({transparent:true,opacity:.3});
    const sources=[geometry(),geometry()];for(const source of sources){source.setIndex([0,1,2,0,1,2,0,1,2]);source.addGroup(0,3,0);source.addGroup(3,3,1);source.addGroup(6,3,0);}
    const meshes=sources.map(source=>new Mesh(source,[opaque,transparent]));root.add(...meshes);
    let residualDisposals=0;const clone=sources[0].clone.bind(sources[0]);sources[0].clone=()=>{const result=clone();result.addEventListener('dispose',()=>residualDisposals++);return result;};
    sources[1].clone=()=>{throw Error('Injected actual geometry allocation failure');};
    const result=batchStaticModel(root);assert.equal(result.savedDrawCalls,0);assert.equal(residualDisposals,1);
    assert.deepEqual(meshes.map(mesh=>mesh.geometry),sources);assert.ok(meshes.every(mesh=>mesh.visible));assert.deepEqual(root.children,meshes);
});

test('mixed shader callbacks and alpha-hashed materials remain wholly on the original render path',()=>{
    for(const uncertain of [new ShaderMaterial({transparent:true}),new MeshStandardMaterial({alphaHash:true}),Object.assign(new MeshBasicMaterial({transparent:true}),{onBeforeCompile(){}})]){
        const source=geometry();source.setIndex([0,1,2,0,1,2,0,1,2]);source.addGroup(0,3,0);source.addGroup(3,3,1);source.addGroup(6,3,0);
        const original=new Mesh(source,[new MeshBasicMaterial(),uncertain]),root=new Group();root.add(original);
        assert.equal(batchStaticModel(root).savedDrawCalls,0);assert.equal(original.geometry,source);assert.ok(original.visible);
    }
});

test('genuine native alpha shaders and their registered clones retain same-material batching and original geometry',async()=>{
    const {root,meshes,material}=fixture();material.map=new Texture();
    await applyNativeMaterialAlpha(material,{useAlpha:true,mode:'OPACITY_MAP_MASK',cutoff:.5});
    assert.notEqual(material.onBeforeCompile,MeshBasicMaterial.prototype.onBeforeCompile);
    const originals=meshes.map(mesh=>mesh.geometry),corners=worldCorners(meshes);
    const result=batchStaticModel(root);assert.equal(result.savedDrawCalls,2);assert.equal(result.batches[0].material,material);
    root.updateMatrixWorld(true);assert.deepEqual(worldCorners(result.batches),corners);result.restore();assert.deepEqual(meshes.map(mesh=>mesh.geometry),originals);
    const clone=cloneNativeMaterial(material);assert.equal(clone.onBeforeCompile,material.onBeforeCompile);assert.equal(clone.customProgramCacheKey,material.customProgramCacheKey);
    meshes.forEach(mesh=>{mesh.material=clone;});const cloned=batchStaticModel(root);assert.equal(cloned.savedDrawCalls,2);assert.equal(cloned.batches[0].material,clone);cloned.restore();
});
test('native fractional-alpha residual groups keep original mesh identity and selectors while opaque groups batch',async()=>{
    const opaque=new MeshBasicMaterial({map:new Texture()}),glass=new MeshBasicMaterial({map:new Texture(),opacity:.3});
    await applyNativeMaterialAlpha(opaque,{useAlpha:true,mode:'OPACITY_MAP_MASK'});
    await applyNativeMaterialAlpha(glass,{useAlpha:true,mode:'OPACITY_MAP_MASK'});
    const source=geometry();source.setIndex([0,1,2,0,1,2,0,1,2]);source.addGroup(0,3,0);source.addGroup(3,3,1);source.addGroup(6,3,0);
    const original=new Mesh(source,[opaque,glass]),root=new Group();root.add(original);const id=original.id;
    const result=batchStaticModel(root);assert.equal(result.savedDrawCalls,1);assert.equal(original.id,id);assert.ok(original.visible);
    assert.deepEqual(original.geometry.groups,[{start:3,count:3,materialIndex:1}]);assert.equal(original.material[1],glass);assert.equal(result.batches[0].material,opaque);
    result.restore();assert.equal(original.geometry,source);assert.equal(original.id,id);assert.deepEqual(source.groups.map(group=>group.materialIndex),[0,1,0]);
});
test('forged alpha metadata, copied shader pairs and modified registered callbacks cannot bypass static shader guards',async()=>{
    const trusted=new MeshBasicMaterial({map:new Texture()});await applyNativeMaterialAlpha(trusted,{useAlpha:true,mode:'OPACITY_MAP_MASK'});
    const forged=new MeshBasicMaterial({map:trusted.map});forged.userData.nativeAlpha={...trusted.userData.nativeAlpha};
    forged.onBeforeCompile=trusted.onBeforeCompile;forged.customProgramCacheKey=trusted.customProgramCacheKey;
    const changedCallback=cloneNativeMaterial(trusted);changedCallback.onBeforeCompile=()=>{};
    const changedKey=cloneNativeMaterial(trusted);changedKey.customProgramCacheKey=()=>trusted.customProgramCacheKey();
    for(const candidate of [forged,changedCallback,changedKey]){
        const {root,meshes}=fixture();meshes.forEach(mesh=>{mesh.material=candidate;});const originals=meshes.map(mesh=>mesh.geometry);
        assert.equal(inspectStaticModel(root).savedDrawCalls,0);assert.equal(batchStaticModel(root).savedDrawCalls,0);
        assert.ok(meshes.every(mesh=>mesh.visible));assert.deepEqual(meshes.map(mesh=>mesh.geometry),originals);
    }
});
