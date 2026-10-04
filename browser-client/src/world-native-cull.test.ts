// SPDX-License-Identifier: Apache-2.0
// Actual World methods and owned resources; CPU contracts, not native/GPU proof.
import test from 'node:test';
import assert from 'node:assert/strict';
import { BackSide, BoxGeometry, DoubleSide, FrontSide, Group, Mesh, MeshBasicMaterial, PlaneGeometry, Texture, Vector3 } from 'three';
import { BrowserWorld } from './world';
import { MeshCollision } from './mesh-collision';

function world(enabled = true) {
  const warnings: string[] = [], context = Object.create(BrowserWorld.prototype);
  Object.assign(context, { nativeCullDefaults: enabled, nativeWinding: new WeakMap(), modelReaders: new WeakMap(),
    abort: new AbortController(), disposed: false, zeroLightGuard: false, loadPhases: new Map(),
    options: { nativeCullDefaults: enabled, onStatus: (message: string) => warnings.push(message) },
    objects: new Map(), meshCollisions: new Map() });
  return { context, warnings };
}

test('actual World defaults remain off, and only known solid primitive sides change when opted in', () => {
  for (const enabled of [false, true]) {
    const { context } = world(enabled);
    // Mutating retained options cannot switch the already captured experiment.
    context.options.nativeCullDefaults = !enabled;
    for (const entity of [{ type: 'Box' }, { type: 'Sphere' }, { type: 'Shape', shape: 'Cylinder' }]) {
      const material = context.baseMaterial({ id: 'solid', ...entity });
      assert.equal(material.side, enabled ? FrontSide : DoubleSide); material.dispose();
    }
    for (const shape of ['Quad', 'Circle']) {
      const material = context.baseMaterial({ id: 'flat', type: 'Shape', shape });
      assert.equal(material.side, DoubleSide); material.dispose();
    }
  }
});

test('actual native Material factory preserves explicit and unknown modes and alpha classification', async () => {
  for (const enabled of [false, true]) {
    const { context } = world(enabled);
    for (const [declared, expected] of [[undefined, enabled ? FrontSide : DoubleSide], ['CULL_BACK', FrontSide], ['CULL_FRONT', BackSide], ['CULL_NONE', DoubleSide], ['CULL_FUTURE', DoubleSide]] as const) {
      const material = await context.makeMaterial({ name: 'native-side-contract', unlit: true, opacity: .5, cullFaceMode: declared });
      assert.equal(material.side, expected); assert.equal(material.transparent, true); assert.equal(material.opacity, .5);
      assert.equal(material.depthWrite, false); assert.equal(material.toneMapped, false); material.dispose();
    }
  }
});

test('actual completed model uses full parent determinant, preserves materials, and rebuilds only its collision owner', async () => {
  const { context } = world(), parent = new Group(), root = new Group(); parent.scale.set(-2, 3, 4); parent.add(root);
  const geometry = new BoxGeometry(), map = new Texture(), material = new MeshBasicMaterial({ map, side: DoubleSide });
  const mesh = new Mesh(geometry, material); root.add(mesh); context.objects.set('model', root);
  const indexBefore = [...geometry.index!.array], vertices = geometry.getAttribute('position');
  let disposedGeometry = 0, disposedMaterial = 0, disposedTexture = 0, oldCollider = 0, foreignCollider = 0;
  geometry.addEventListener('dispose', () => disposedGeometry++); material.addEventListener('dispose', () => disposedMaterial++); map.addEventListener('dispose', () => disposedTexture++);
  context.meshCollisions.set('model', { value: { dispose() { oldCollider++; } } });
  context.meshCollisions.set('other', { value: { dispose() { foreignCollider++; } } });
  await context.prepareNativeModelFaces({ id: 'model', type: 'Model' }, root);
  assert.notEqual(mesh.geometry, geometry); assert.equal(mesh.geometry.getAttribute('position'), vertices);
  const expected = [...indexBefore]; for (let at = 0; at < expected.length; at += 3) [expected[at], expected[at + 1]] = [expected[at + 1], expected[at]];
  assert.deepEqual([...mesh.geometry.index!.array], expected); assert.equal(mesh.material, material);
  assert.equal(material.map, map); assert.equal(material.side, DoubleSide); assert.equal(disposedMaterial, 0); assert.equal(disposedTexture, 0);
  assert.equal(disposedGeometry, 1); assert.equal(oldCollider, 1); assert.equal(foreignCollider, 0); assert.equal(context.meshCollisions.has('model'), false);
  assert.equal(context.nativeWinding.get(root).convertedMeshes, 1); context.nativeWinding.get(root).assertStatic();
});

test('a positive model and default-off negative model preserve exact geometry and existing early collision', async () => {
  for (const enabled of [true, false]) {
    const { context } = world(enabled), root = new Group(), mesh = new Mesh(new BoxGeometry(), new MeshBasicMaterial());
    if (!enabled) root.scale.x = -1;
    root.add(mesh); context.objects.set('model', root); const before = mesh.geometry; let colliderDisposals = 0;
    context.meshCollisions.set('model', { value: { dispose() { colliderDisposals++; } } });
    await context.prepareNativeModelFaces({ id: 'model', type: 'Model' }, root);
    assert.equal(mesh.geometry, before); assert.equal(colliderDisposals, 0); assert.equal(context.meshCollisions.has('model'), true);
  }
});

test('removed/aborted model owners cannot allocate winding geometry or invalidate live colliders', async () => {
  for (const kind of ['removed', 'world-abort', 'reader-abort']) {
    const { context } = world(), root = new Group(), mesh = new Mesh(new BoxGeometry(), new MeshBasicMaterial()); root.add(mesh); root.scale.x = -1;
    if (kind !== 'removed') context.objects.set('model', root);
    if (kind === 'world-abort') context.abort.abort();
    if (kind === 'reader-abort') { const reader = new AbortController(); context.modelReaders.set(root, reader); reader.abort(); }
    const before = mesh.geometry; let disposed = 0; context.meshCollisions.set('model', { value: { dispose() { disposed++; } } });
    await assert.rejects(context.prepareNativeModelFaces({ id: 'model', type: 'Model' }, root), { name: 'AbortError' });
    assert.equal(mesh.geometry, before); assert.equal(disposed, 0); assert.equal(context.nativeWinding.has(root), false);
  }
});

test('fixed-CCW renderer index preparation does not invent/remove genuine floor support', async () => {
  const { context } = world(), root = new Group(), mesh = new Mesh(new PlaneGeometry(20, 20), new MeshBasicMaterial());
  mesh.rotation.x = -Math.PI / 2; root.scale.x = -1; root.add(mesh); context.objects.set('model', root);
  const before = new MeshCollision(root), position = new Vector3(0, .85001, 0); assert.equal(before.supports(position), true);
  await context.prepareNativeModelFaces({ id: 'model', type: 'Model' }, root);
  const after = new MeshCollision(root); assert.equal(after.supports(position), true); assert.equal(after.supports(new Vector3(0, 3, 0)), false);
  before.dispose(); after.dispose();
});

test('geometry parity mutation is refused before a subsequent actual batch rebuild', async () => {
  const { context } = world(), root = new Group(); root.add(new Mesh(new BoxGeometry(), new MeshBasicMaterial())); context.objects.set('model', root);
  await context.prepareNativeModelFaces({ id: 'model', type: 'Model' }, root);
  root.scale.x = -1; let restored = 0;
  context.restoreModelBatch = () => restored++;
  assert.throws(() => context.prepareModelBatch('model', root), /parity or geometry changed/); assert.equal(restored, 1);
});
