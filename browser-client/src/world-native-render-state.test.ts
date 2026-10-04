// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry, BufferAttribute, DoubleSide, Mesh, MeshBasicMaterial, Object3D, Texture } from 'three';
import { BrowserWorld } from './world';
import type { Entity } from './world-data';
import type { MappedMaterial, NativeAlphaOptions } from './native-alpha-material';

function owner() {
  const world = Object.create(BrowserWorld.prototype) as BrowserWorld;
  const warnings: string[] = [];
  const state = world as unknown as { abort: AbortController; disposed: boolean; options: unknown; objects: Map<string,Object3D>; entities: Map<string,Entity>;
    restoreModelBatch(root: Object3D): void; prepareGraphics(root: Object3D): Promise<void>; recordLoadPhase(name: string, start: number): void;
    applyEntityMaterial(entity: Entity): Promise<void>; configureAlpha(material: MappedMaterial, options: NativeAlphaOptions): Promise<void>; makeMaterial(): Promise<MeshBasicMaterial> };
  state.abort = new AbortController(); state.disposed = false; state.options = { onStatus: (message: string) => warnings.push(message) };
  state.objects = new Map(); state.entities = new Map(); state.restoreModelBatch = () => {}; state.recordLoadPhase = () => {};
  state.prepareGraphics = async root => { root.userData.shadersReady = true; };
  return {state,warnings};
}
test('actual native Material entity overrides keep geometry RGB and separate uncolored mesh shader state', async () => {
  const {state,warnings} = owner(), root = new Object3D(), coloredGeometry = new BoxGeometry(), plainGeometry = new BoxGeometry();
  const colors = new BufferAttribute(new Float32Array(coloredGeometry.getAttribute('position').count * 3).fill(.25), 3); coloredGeometry.setAttribute('color', colors);
  const old = new MeshBasicMaterial(), colored = new Mesh(coloredGeometry, old), plain = new Mesh(plainGeometry, old); root.add(colored, plain);
  state.objects.set('parent', root); state.entities.set('parent', { id: 'parent', type: 'Model' });
  await state.applyEntityMaterial({ id: 'material', type: 'Material', parentID: 'parent', parentMaterialName: 'all', materialData: JSON.stringify({ materials: { name: 'Authored layer', unlit: true, opacity: .5, cullFaceMode: 'CULL_NONE' } }) });
  assert.equal(colored.material.vertexColors, true); assert.equal(plain.material.vertexColors, false); assert.equal(coloredGeometry.getAttribute('color'), colors);
  for (const material of [colored.material, plain.material]) { assert.equal(material.side, DoubleSide); assert.equal(material.forceSinglePass, true); assert.equal(material.depthWrite, false); assert.equal(material.opacity, .5); }
  assert.notEqual(colored.material, plain.material); assert.equal(root.visible, true); assert.deepEqual(warnings, []);
  colored.material.dispose(); plain.material.dispose(); old.dispose(); coloredGeometry.dispose(); plainGeometry.dispose();
});
test('failed actual image alpha inspection still applies scalar translucency while reporting the failure', async () => {
  const {state,warnings} = owner(), material = new MeshBasicMaterial({ map: new Texture(), transparent: true, opacity: .5, side: DoubleSide });
  await state.configureAlpha(material, { useAlpha: true });
  assert.equal(material.opacity, .5); assert.equal(material.transparent, true); assert.equal(material.depthWrite, false); assert.equal(material.forceSinglePass, true);
  assert.equal(warnings.length, 1); assert.match(warnings[0], /Texture transparency could not be read/); material.map?.dispose(); material.dispose();
});
test('actual configureAlpha refuses foreign hooks without changing custom render state and preserves abort', async () => {
  const {state,warnings} = owner(), material = new MeshBasicMaterial({ transparent: true, side: DoubleSide });
  const foreign = () => {}; material.onBeforeCompile = foreign; const version = material.version;
  await state.configureAlpha(material, { useAlpha: false });
  assert.equal(material.onBeforeCompile, foreign); assert.equal(material.depthWrite, true); assert.equal(material.forceSinglePass, false); assert.equal(material.version, version);
  assert.equal(warnings.length, 2); assert.match(warnings[1], /custom material shader/);
  state.abort.abort(); await assert.rejects(state.configureAlpha(material, { useAlpha: false }), /unsupported custom/); assert.equal(material.version, version); material.dispose();
});
test('actual material swaps release obsolete resources once and keep a shared old map referenced by an unmatched slot', async () => {
  const {state} = owner(), root = new Object3D(), geometry = new BoxGeometry(), oldMap = new Texture(), newMap = new Texture();
  const selected = new MeshBasicMaterial({ map: oldMap }), unmatched = new MeshBasicMaterial({ map: oldMap }), template = new MeshBasicMaterial({ map: newMap });
  const first = new Mesh(geometry, [selected, unmatched]), second = new Mesh(geometry, [selected, unmatched]); root.add(first, second);
  let selectedDisposed = 0, unmatchedDisposed = 0, oldMapDisposed = 0, newMapDisposed = 0, templateDisposed = 0, geometryDisposed = 0;
  selected.addEventListener('dispose',()=>selectedDisposed++); unmatched.addEventListener('dispose',()=>unmatchedDisposed++); oldMap.addEventListener('dispose',()=>oldMapDisposed++);
  newMap.addEventListener('dispose',()=>newMapDisposed++); template.addEventListener('dispose',()=>templateDisposed++); geometry.addEventListener('dispose',()=>geometryDisposed++);
  state.objects.set('parent',root); state.entities.set('parent',{id:'parent',type:'Model'}); state.makeMaterial=async()=>template;
  await state.applyEntityMaterial({id:'material',type:'Material',parentID:'parent',parentMaterialName:'0',materialData:'{"materials":{"name":"Override"}}'});
  assert.equal(selectedDisposed,1); assert.equal(unmatchedDisposed,0); assert.equal(oldMapDisposed,0); assert.equal(newMapDisposed,0); assert.equal(templateDisposed,1); assert.equal(geometryDisposed,0);
  assert.equal(first.material[1],unmatched); assert.equal(second.material[1],unmatched); assert.equal(first.material[0].map,newMap); assert.equal(second.material[0].map,newMap);
  first.material[0].dispose(); second.material[0].dispose(); unmatched.dispose(); oldMap.dispose(); newMap.dispose(); geometry.dispose();
});
test('unmatched Material selector disposes its template and maps without touching target resources', async () => {
  const {state} = owner(), root = new Object3D(), geometry = new BoxGeometry(), oldMap = new Texture(), newMap = new Texture();
  const old = new MeshBasicMaterial({map:oldMap}), template = new MeshBasicMaterial({map:newMap}), mesh = new Mesh(geometry,old); root.add(mesh);
  let oldDisposed=0,oldMapDisposed=0,newMapDisposed=0,templateDisposed=0;
  old.addEventListener('dispose',()=>oldDisposed++);oldMap.addEventListener('dispose',()=>oldMapDisposed++);newMap.addEventListener('dispose',()=>newMapDisposed++);template.addEventListener('dispose',()=>templateDisposed++);
  state.objects.set('parent',root);state.entities.set('parent',{id:'parent',type:'Model'});state.makeMaterial=async()=>template;
  await state.applyEntityMaterial({id:'material',type:'Material',parentID:'parent',parentMaterialName:'mat::Missing',materialData:'{"materials":{"name":"Unused"}}'});
  assert.equal(mesh.material,old);assert.equal(oldDisposed,0);assert.equal(oldMapDisposed,0);assert.equal(newMapDisposed,1);assert.equal(templateDisposed,1);
  old.dispose();oldMap.dispose();geometry.dispose();
});
test('target replaced during awaited material creation releases only the new template', async () => {
  const {state} = owner(), target = new Object3D(), geometry = new BoxGeometry(), old = new MeshBasicMaterial(), map = new Texture(), template = new MeshBasicMaterial({map}); target.add(new Mesh(geometry,old));
  let oldDisposed=0,geometryDisposed=0,mapDisposed=0,templateDisposed=0;
  old.addEventListener('dispose',()=>oldDisposed++);geometry.addEventListener('dispose',()=>geometryDisposed++);map.addEventListener('dispose',()=>mapDisposed++);template.addEventListener('dispose',()=>templateDisposed++);
  state.objects.set('parent',target);state.entities.set('parent',{id:'parent',type:'Model'});
  state.makeMaterial=async()=>{state.objects.set('parent',new Object3D());return template;};
  await state.applyEntityMaterial({id:'material',type:'Material',parentID:'parent',materialData:'{"materials":{"name":"Stale"}}'});
  assert.equal(oldDisposed,0);assert.equal(geometryDisposed,0);assert.equal(mapDisposed,1);assert.equal(templateDisposed,1);
  old.dispose();geometry.dispose();
});
