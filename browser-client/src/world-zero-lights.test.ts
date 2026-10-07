// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry, BufferAttribute, DoubleSide, Material, Mesh, MeshBasicMaterial, MeshStandardMaterial, Object3D, ShaderChunk, ShaderLib, Texture, type BufferGeometry, type WebGLRenderer } from 'three';
import { BrowserWorld } from './world';
import { applyNativeMaterialAlpha, getNativeAlphaOptions, hasNativeAlphaShader, type MappedMaterial, type NativeAlphaOptions } from './native-alpha-material';
import { applyNativeRenderState, cloneNativeMaterialForGeometry } from './native-render-state';
import { hasNativeZeroLightShader, installNativeZeroLightShader, restoreNativeZeroLightShader } from './native-zero-lights';
import { batchStaticModel, inspectStaticModel } from './static-model-batch';

function owner(enabled?: boolean) {
  const world = Object.create(BrowserWorld.prototype) as BrowserWorld, warnings: string[] = [];
  const state = world as unknown as { abort: AbortController; disposed: boolean; zeroLightWarnings: WeakSet<Material>; zeroLightGuard: boolean; compilingGraphics: number;
    options: { zeroLightGuard?: boolean; onStatus(message: string): void }; renderer: { compileAsync(root: Object3D): Promise<void> };
    configureAlpha(material: MappedMaterial, options: NativeAlphaOptions, signal?: AbortSignal): Promise<void>;
    prepareZeroLightShaders(root: Object3D): void; prepareGraphics(root: Object3D): Promise<void>; recordLoadPhase(): void };
  state.abort = new AbortController(); state.disposed = false; state.zeroLightWarnings = new WeakSet(); state.compilingGraphics = 0;
  state.zeroLightGuard = enabled === true;
  state.options = { zeroLightGuard: enabled, onStatus: message => warnings.push(message) }; state.recordLoadPhase = () => {};
  return { state, warnings };
}
function rootWith(material: Material, geometry: BufferGeometry = new BoxGeometry()) {
  const root = new Object3D(); root.add(new Mesh(geometry, material), new Mesh(geometry, material)); return { root, geometry };
}
function shader() { return { ...ShaderLib.standard, uniforms: { ...ShaderLib.standard.uniforms } } as Parameters<Material['onBeforeCompile']>[0]; }

test('default-off actual World preserves baseline alpha/state versions, warnings and unwrapped material hooks', async () => {
  const { state, warnings } = owner(), map = new Texture();
  const baseline = new MeshStandardMaterial({ map, side: DoubleSide }), material = baseline.clone();
  await applyNativeMaterialAlpha(baseline, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .375 }); applyNativeRenderState(baseline);
  await state.configureAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .375 });
  // The real constructor captures this flag once; changing the external
  // options object does not activate new hooks on an existing World.
  state.options.zeroLightGuard = true;
  const { root, geometry } = rootWith(material); state.prepareZeroLightShaders(root);
  assert.equal(material.version, baseline.version); assert.equal(hasNativeZeroLightShader(material), false); assert.equal(hasNativeAlphaShader(material), true);
  assert.equal(material.alphaTest, baseline.alphaTest); assert.equal(material.depthWrite, baseline.depthWrite); assert.equal(material.forceSinglePass, baseline.forceSinglePass);
  assert.equal(material.customProgramCacheKey(), baseline.customProgramCacheKey()); assert.deepEqual(warnings, []);
  baseline.dispose(); material.dispose(); map.dispose(); geometry.dispose();
});

test('terminal opt-in graph installs each owned lit material once and leaves native alpha state and unlit materials intact', async () => {
  const { state, warnings } = owner(true), map = new Texture();
  const opaque = new MeshStandardMaterial(), mask = new MeshStandardMaterial({ map }), unlit = new MeshBasicMaterial();
  await state.configureAlpha(mask, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .4 });
  assert.equal(hasNativeZeroLightShader(mask), false);
  const { root, geometry } = rootWith(opaque); root.add(new Mesh(geometry, mask), new Mesh(geometry, unlit));
  const before = [opaque.version, mask.version, unlit.version], originalChunk = ShaderChunk.lights_fragment_begin;
  state.prepareZeroLightShaders(root); const versions = [opaque.version, mask.version, unlit.version];
  assert.deepEqual(versions, [before[0] + 1, before[1] + 1, before[2]]);
  for (let index = 0; index < 20; index++) state.prepareZeroLightShaders(root);
  assert.deepEqual([opaque.version, mask.version, unlit.version], versions);
  assert.equal(hasNativeZeroLightShader(opaque), true); assert.equal(hasNativeZeroLightShader(mask), true); assert.equal(hasNativeZeroLightShader(unlit), false);
  assert.equal(mask.alphaTest, .4); assert.equal(mask.depthWrite, true); assert.equal(unlit.onBeforeCompile, Material.prototype.onBeforeCompile);
  assert.equal(ShaderChunk.lights_fragment_begin, originalChunk); assert.deepEqual(warnings, []);
  opaque.dispose(); mask.dispose(); unlit.dispose(); map.dispose(); geometry.dispose();
});

test('actual guarded World mask/blend/mask swaps preserve cutoff, scalar opacity, culling and private parent proof', async () => {
  const { state, warnings } = owner(true), map = new Texture(), material = new MeshStandardMaterial({ map, side: DoubleSide });
  await state.configureAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .375 }); installNativeZeroLightShader(material);
  await state.configureAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_BLEND' });
  assert.equal(hasNativeZeroLightShader(material), true); assert.equal(material.transparent, true); assert.equal(material.depthWrite, false); assert.equal(material.forceSinglePass, true); assert.equal(material.side, DoubleSide);
  assert.equal(getNativeAlphaOptions(material)?.mode, 'OPACITY_MAP_BLEND');
  material.opacity = .6; await state.configureAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .2 });
  assert.equal(hasNativeZeroLightShader(material), true); assert.equal(material.opacity, .6); assert.equal(material.alphaTest, .12); assert.equal(material.depthWrite, false);
  const parameters = shader(); material.onBeforeCompile(parameters, {} as WebGLRenderer);
  assert.equal(parameters.uniforms.nativeOpacityCutoff.value, .2); assert.ok(parameters.fragmentShader.includes('notEqual( spotLight.color'));
  assert.equal(restoreNativeZeroLightShader(material), true); assert.equal(hasNativeAlphaShader(material), true); assert.equal(getNativeAlphaOptions(material)?.cutoff, .2);
  assert.deepEqual(warnings, []); material.dispose(); map.dispose();
});

test('classification failure retains the exact old alpha parent and warns instead of silently dropping the guard', async () => {
  const { state, warnings } = owner(true), material = new MeshStandardMaterial({ map: new Texture() });
  await state.configureAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .375 }); installNativeZeroLightShader(material);
  await state.configureAlpha(material, { useAlpha: true });
  assert.equal(hasNativeZeroLightShader(material), true); assert.equal(material.alphaTest, .375); assert.equal(getNativeAlphaOptions(material)?.mode, 'OPACITY_MAP_MASK');
  assert.equal(warnings.length, 1); assert.match(warnings[0], /Texture transparency could not be read/);
  material.map?.dispose(); material.dispose();
});

test('aborted reader or World during actual asynchronous alpha rejection never reinstalls a detached guard or emits stale warnings', async () => {
  for (const boundary of ['reader', 'world', 'disposed'] as const) {
    const { state, warnings } = owner(true), reader = new AbortController(), material = new MeshStandardMaterial({ map: new Texture() });
    await state.configureAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK' }); installNativeZeroLightShader(material);
    // Invalid unloaded image is a genuine async classifier rejection. Abort
    // before its promise continuation; no fake Worker/clock or weakened API.
    const pending = state.configureAlpha(material, { useAlpha: true }, reader.signal);
    if (boundary === 'reader') reader.abort(); else if (boundary === 'world') state.abort.abort(); else state.disposed = true;
    await assert.rejects(pending, /loaded image/); assert.equal(hasNativeZeroLightShader(material), false); assert.equal(hasNativeAlphaShader(material), true); assert.deepEqual(warnings, []);
    material.map?.dispose(); material.dispose();
  }
});

test('foreign or copied guard mutations retain original alpha/state refusal without callback, version or state changes', async () => {
  for (const boundary of ['foreign', 'copied'] as const) {
    const { state, warnings } = owner(true), donor = new MeshStandardMaterial(), material = new MeshStandardMaterial({ transparent: true, side: DoubleSide });
    installNativeZeroLightShader(donor);
    if (boundary === 'foreign') { installNativeZeroLightShader(material); material.onBeforeCompile = () => {}; }
    else { material.onBeforeCompile = donor.onBeforeCompile; material.customProgramCacheKey = donor.customProgramCacheKey; }
    material.userData.nativeZeroLights = true;
    const compile = material.onBeforeCompile, key = material.customProgramCacheKey, version = material.version;
    await state.configureAlpha(material, { useAlpha: false });
    assert.equal(material.onBeforeCompile, compile); assert.equal(material.customProgramCacheKey, key); assert.equal(material.version, version);
    assert.equal(material.depthWrite, true); assert.equal(material.forceSinglePass, false); assert.equal(warnings.length, 2);
    const { root, geometry } = rootWith(material); state.prepareZeroLightShaders(root); state.prepareZeroLightShaders(root);
    assert.equal(warnings.length, 3); assert.equal(hasNativeZeroLightShader(material), false); assert.equal(inspectStaticModel(root).savedDrawCalls, 0);
    donor.dispose(); material.dispose(); geometry.dispose();
  }
});

test('actual batch collector retains original opaque/mask sharing and excludes foreign composed pairs', async () => {
  for (const mask of [false, true]) {
    const material = new MeshStandardMaterial({ map: mask ? new Texture() : null });
    if (mask) await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK' });
    const { root, geometry } = rootWith(material), before = inspectStaticModel(root);
    installNativeZeroLightShader(material); const version = material.version;
    assert.deepEqual(inspectStaticModel(root), before); const batch = batchStaticModel(root);
    assert.equal(batch.savedDrawCalls, 1); assert.equal(batch.batches[0].material, material); assert.equal(hasNativeZeroLightShader(material), true); assert.equal(material.version, version);
    batch.restore(); assert.equal(root.children.length, 2); assert.equal(inspectStaticModel(root).savedDrawCalls, 1);
    material.onBeforeCompile = () => {}; assert.equal(inspectStaticModel(root).savedDrawCalls, 0);
    material.map?.dispose(); material.dispose(); geometry.dispose();
  }
});

test('actual geometry-aware native clone preserves registered composed alpha and independent vertex-color state', async () => {
  const map = new Texture(), material = new MeshStandardMaterial({ map }); await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .37 }); installNativeZeroLightShader(material);
  const plain = new BoxGeometry(), colored = plain.clone(); colored.setAttribute('color', new BufferAttribute(new Float32Array(colored.getAttribute('position').count * 3).fill(.25), 3));
  const version = material.version, first = cloneNativeMaterialForGeometry(material, colored), second = cloneNativeMaterialForGeometry(material, plain);
  assert.equal(material.version, version); assert.equal(hasNativeZeroLightShader(material), true); assert.equal(first.vertexColors, true); assert.equal(second.vertexColors, false); assert.equal(material.vertexColors, false);
  for (const clone of [first, second]) {
    assert.equal(hasNativeZeroLightShader(clone), true); assert.equal(clone.map, map); assert.equal(clone.alphaTest, .37); assert.deepEqual(getNativeAlphaOptions(clone), getNativeAlphaOptions(material));
    assert.equal(restoreNativeZeroLightShader(clone), true); assert.equal(hasNativeAlphaShader(clone), true); clone.dispose();
  }
  material.dispose(); map.dispose(); plain.dispose(); colored.dispose();
});

test('World revocation before or during terminal setup prevents further owned shader installation', () => {
  const { state, warnings } = owner(true), foreign = new MeshStandardMaterial(), material = new MeshStandardMaterial(), { root, geometry } = rootWith(foreign);
  foreign.onBeforeCompile = () => {}; root.add(new Mesh(geometry, material));
  state.options.onStatus = message => { warnings.push(message); state.abort.abort(); };
  assert.throws(() => state.prepareZeroLightShaders(root), /abort/i); assert.equal(hasNativeZeroLightShader(material), false); assert.equal(material.version, 0); assert.equal(warnings.length, 1);
  const other = owner(true); other.state.disposed = true; assert.throws(() => other.state.prepareZeroLightShaders(root), /ended/); assert.equal(material.version, 0);
  foreign.dispose(); material.dispose(); geometry.dispose();
});

test('actual terminal warmup receives guarded material, while disposed async compile cannot mark root ready', async () => {
  const { state } = owner(true), material = new MeshStandardMaterial(), { root, geometry } = rootWith(material); let observed = false, release: () => void = () => {};
  state.renderer = { compileAsync: async () => { observed = hasNativeZeroLightShader(material); await new Promise<void>(resolve => { release = resolve; }); } };
  const pending = state.prepareGraphics(root); assert.equal(observed, true); assert.equal(state.compilingGraphics, 1); assert.equal(root.visible, false);
  state.disposed = true; release(); await pending;
  assert.equal(root.userData.shadersReady, false); assert.equal(root.visible, false); assert.equal(state.compilingGraphics, 0); material.dispose(); geometry.dispose();
});
