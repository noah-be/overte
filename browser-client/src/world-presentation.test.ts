// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ACESFilmicToneMapping, OrthographicCamera, Scene, SRGBColorSpace, Vector4, WebGLRenderTarget, type WebGLRenderer } from 'three';
import { nativeToneParameters, presentationAllocation, WorldPresentation, type PresentationCapabilities } from './world-presentation';

const capabilities: PresentationCapabilities = { maxTextureSize: 8192, maxRenderbufferSize: 8192, halfFloat: true, halfFloatSamples: [4, 2, 1], byteSamples: [8, 4, 2, 1] };
function fixture(options: { halfFloat?: boolean; maxBytes?: number } = {}) {
  let target: WebGLRenderTarget | null = null, pixelRatio = 1, incomplete = false, failure = false, disposed = 0, scissorTest = true;
  const viewport = new Vector4(0, 0, 17, 19), scissor = new Vector4(1, 2, 3, 4), frames: Array<{ target: WebGLRenderTarget | null; tone: number; color: string }> = [], allocations: WebGLRenderTarget[] = [];
  const effectiveViewport = viewport.clone(), effectiveScissor = scissor.clone(); let effectiveScissorTest = scissorTest;
  const gl = { RENDERBUFFER: 1, SAMPLES: 2, RGBA16F: 3, RGBA8: 4, MAX_TEXTURE_SIZE: 5, MAX_RENDERBUFFER_SIZE: 6, FRAMEBUFFER: 7, FRAMEBUFFER_COMPLETE: 8, SCISSOR_BOX: 9, SCISSOR_TEST: 10,
    getExtension: () => options.halfFloat === false ? null : {}, getParameter: (key: number) => key === 9 ? effectiveScissor.toArray() : 8192, isEnabled: () => effectiveScissorTest, getInternalformatParameter: () => new Int32Array([4, 2, 1]), checkFramebufferStatus: () => incomplete ? 0 : 8 };
  const renderer = { getContext: () => gl, toneMapping: ACESFilmicToneMapping, outputColorSpace: SRGBColorSpace, autoClear: false,
    info: { autoReset: true, render: { calls: 0 }, reset() { this.render.calls = 0; } },
    getRenderTarget: () => target, getActiveCubeFace: () => 0, getActiveMipmapLevel: () => 0, setRenderTarget(value: WebGLRenderTarget | null) { target = value; effectiveViewport.copy(value ? value.viewport : viewport.clone().multiplyScalar(pixelRatio)); effectiveScissor.copy(value ? value.scissor : scissor.clone().multiplyScalar(pixelRatio)); effectiveScissorTest = value?.scissorTest ?? scissorTest; },
    getViewport: (value: Vector4) => value.copy(viewport), getCurrentViewport: (value: Vector4) => value.copy(effectiveViewport), setViewport: (value: Vector4) => { viewport.copy(value); effectiveViewport.copy(value).multiplyScalar(pixelRatio); }, getScissor: (value: Vector4) => value.copy(scissor), setScissor: (value: Vector4) => { scissor.copy(value); effectiveScissor.copy(value).multiplyScalar(pixelRatio); }, getScissorTest: () => scissorTest, setScissorTest: (value: boolean) => { scissorTest = effectiveScissorTest = value; },
    initRenderTarget(value: WebGLRenderTarget) { allocations.push(value); value.addEventListener('dispose', () => disposed++); }, getPixelRatio: () => pixelRatio, setPixelRatio: (value: number) => { pixelRatio = value; },
    setSize(width: number, height: number) { this.domElement.width = Math.floor(width * pixelRatio); this.domElement.height = Math.floor(height * pixelRatio); },
    domElement: { width: 17, height: 19, toBlob(callback: (value: Blob) => void) { callback(new Blob(['owned-world'], { type: 'image/png' })); } },
    render() { frames.push({ target, tone: this.toneMapping, color: this.outputColorSpace }); if (failure) throw Error('Actual scene render failed'); this.info.render.calls++; },
    compileAsync: () => Promise.resolve(), dispose() { throw Error('Renderer belongs to caller'); },
  };
  return { renderer, presentation: new WorldPresentation(renderer as unknown as WebGLRenderer, {maxBytes: options.maxBytes}), frames, allocations, get disposed() { return disposed; }, viewport, scissor, effectiveViewport, effectiveScissor, get effectiveScissorTest() { return effectiveScissorTest; }, get target() { return target; }, fail() { failure = true; }, incomplete() { incomplete = true; } };
}

test('native tone defaults and exposure use source-defined SRGB and two-power EV', () => {
  assert.deepEqual(nativeToneParameters(), { curve: 'srgb', index: 1, exposureEV: 0, twoPowExposure: 1 });
  assert.equal(nativeToneParameters('filmic', 2).twoPowExposure, 4); assert.equal(nativeToneParameters('reinhard', -1).index, 2);
  assert.throws(() => nativeToneParameters('invalid' as 'srgb'), /Unsupported/); assert.throws(() => nativeToneParameters('srgb', 1000), /represented/);
});
test('allocation validates exact DPR/MSAA/capability/budget rather than silently reducing requested quality', () => {
  const allocation = presentationAllocation(1024, 768, 2, 4, 'half-float', capabilities);
  assert.equal(allocation.physicalWidth, 2048); assert.equal(allocation.physicalHeight, 1536); assert.equal(allocation.samples, 4);
  assert.throws(() => presentationAllocation(1024, 768, 1, 8, 'half-float', capabilities), /antialiasing/);
  assert.throws(() => presentationAllocation(9000, 1, 1, 0, 'half-float', capabilities), /resolution/);
  assert.throws(() => presentationAllocation(1024, 768, 1, 4, 'half-float', capabilities, 100), /budget/);
  assert.throws(() => presentationAllocation(10, 10, 1, 0, 'half-float', { ...capabilities, halfFloat: false }), /half-float/);
  assert.equal(presentationAllocation(10, 10, 1, 0, 'unsigned-byte', { ...capabilities, halfFloat: false }).precision, 'unsigned-byte');
});
test('world render stays linear until one output draw and restores caller renderer state', () => {
  const f = fixture(); f.presentation.resize(1024, 768, 1); const scene = new Scene(), camera = new OrthographicCamera();
  assert.equal(f.presentation.render(scene, camera), true); assert.equal(f.frames.length, 2); assert.equal(f.frames[0].target, f.allocations[0]); assert.equal(f.frames[1].target, null);
  assert.notEqual(f.frames[0].color, SRGBColorSpace); assert.equal(f.frames[1].color, SRGBColorSpace);
  assert.equal(f.renderer.info.render.calls, 2, 'performance counters must include the world and output draw');
  assert.equal(f.renderer.toneMapping, ACESFilmicToneMapping); assert.equal(f.renderer.outputColorSpace, SRGBColorSpace); assert.equal(f.renderer.autoClear, false); assert.equal(f.renderer.info.autoReset, true); assert.equal(f.target, null);
  assert.deepEqual(f.viewport.toArray(), [0, 0, 17, 19]); assert.deepEqual(f.scissor.toArray(), [1, 2, 3, 4]);
});
test('render failure restores state and does not leave the presentation reentrancy lock held', () => {
  const f = fixture(); f.presentation.resize(32, 32); f.fail();
  assert.throws(() => f.presentation.render(new Scene(), new OrthographicCamera()), /Actual scene/);
  assert.equal(f.target, null); assert.equal(f.renderer.toneMapping, ACESFilmicToneMapping);
  assert.doesNotThrow(() => f.presentation.dispose());
});
test('pause suppresses frame work but visitor snapshot forces current world rendering', async () => {
  const f = fixture(); f.presentation.resize(32, 32); f.presentation.setEnabled(false);
  const scene = new Scene(), camera = new OrthographicCamera(); assert.equal(f.presentation.render(scene, camera), false); assert.equal(f.frames.length, 0);
  const blob = await f.presentation.capture(scene, camera); assert.equal(blob.type, 'image/png'); assert.equal(await blob.text(), 'owned-world'); assert.equal(f.frames.length, 2); assert.equal(f.presentation.getState().enabled, false);
});
test('replacement allocation fails atomically and releases only its failed candidate', () => {
  const f = fixture(); f.presentation.resize(32, 32); assert.equal(f.presentation.getState().nativeHDR, true);
  f.incomplete(); assert.throws(() => f.presentation.resize(64, 64), /incomplete/);
  assert.equal(f.disposed, 1); assert.equal(f.presentation.getState().allocation?.physicalWidth, 32); assert.equal(f.renderer.domElement.width, 32);
  f.presentation.dispose(); f.presentation.dispose(); assert.equal(f.disposed, 2); assert.equal(f.presentation.getState().nativeHDR, false); assert.throws(() => f.presentation.render(new Scene(), new OrthographicCamera()), /disposed/);
});
test('successful resize releases old owned target and idempotent resize performs no allocation', () => {
  const f = fixture(); f.presentation.resize(32, 32); f.presentation.resize(32, 32); assert.equal(f.allocations.length, 1);
  f.presentation.resize(64, 64); assert.equal(f.allocations.length, 2); assert.equal(f.disposed, 1); assert.equal(f.renderer.domElement.width, 64);
  f.presentation.setTone({ curve: 'filmic' }); f.presentation.setTone({ exposureEV: 2 }); assert.deepEqual(f.presentation.getState().tone, { curve: 'filmic', exposureEV: 2 });
  f.presentation.dispose(); assert.equal(f.disposed, 2);
});
test('shader readiness restores renderer immediately while asynchronous compilation remains pending', async () => {
  const f = fixture(); f.presentation.resize(32, 32); let resolve!: () => void;
  f.renderer.compileAsync = () => new Promise<void>(done => { resolve = done; });
  const ready = f.presentation.prepare(new Scene(), new OrthographicCamera()); assert.equal(f.target, null); assert.equal(f.renderer.toneMapping, ACESFilmicToneMapping);
  f.presentation.render(new Scene(), new OrthographicCamera()); resolve(); await ready; f.presentation.dispose();
});


test('custom target physical viewport/scissor survive render and immediate shader preparation', async () => {
  const f = fixture(); f.presentation.resize(32,32,2);
  const target = new WebGLRenderTarget(99,87); target.viewport.set(2,3,41,29); target.scissor.set(4,5,13,17); target.scissorTest = false;
  f.renderer.setRenderTarget(target);
  // Renderer-global CSS defaults are deliberately different from target state.
  const defaults = {viewport:f.viewport.clone(),scissor:f.scissor.clone()};
  const metadata = {viewport:target.viewport.clone(),scissor:target.scissor.clone(),test:target.scissorTest};
  for (const operation of [()=>f.presentation.render(new Scene(),new OrthographicCamera()),()=>f.presentation.prepare(new Scene(),new OrthographicCamera())]) {
    await operation(); assert.equal(f.target,target);
    assert.deepEqual(f.effectiveViewport.toArray(),[2,3,41,29]); assert.deepEqual(f.effectiveScissor.toArray(),[4,5,13,17]); assert.equal(f.effectiveScissorTest,false);
    assert.deepEqual(f.viewport,defaults.viewport); assert.deepEqual(f.scissor,defaults.scissor);
    assert.deepEqual(target.viewport,metadata.viewport); assert.deepEqual(target.scissor,metadata.scissor); assert.equal(target.scissorTest,metadata.test);
  }
  // API viewport/scissor changes after target binding differ from its metadata.
  f.renderer.setViewport(new Vector4(6,7,11,12)); f.renderer.setScissor(new Vector4(8,9,5,6)); f.renderer.setScissorTest(true);
  f.presentation.render(new Scene(),new OrthographicCamera());
  assert.deepEqual(f.effectiveViewport.toArray(),[12,14,22,24]); assert.deepEqual(f.effectiveScissor.toArray(),[16,18,10,12]); assert.equal(f.effectiveScissorTest,true);
  assert.deepEqual(target.viewport,metadata.viewport); assert.deepEqual(target.scissor,metadata.scissor); assert.equal(target.scissorTest,false);
  f.presentation.dispose(); target.dispose();
});

test('transactional old-plus-candidate allocation stays inside the explicit owned peak budget', () => {
  // 32^2 * 12 bytes * (4 samples + resolve) = 61440. Each 40^2 target
  // individually fits, but the replacement peak 61440+96000 does not.
  const f = fixture({maxBytes:120000}); f.presentation.resize(32,32);
  assert.throws(()=>f.presentation.resize(40,40),/peak GPU memory budget/);
  assert.equal(f.allocations.length,1); assert.equal(f.disposed,0); assert.equal(f.presentation.getState().allocation?.physicalWidth,32);
  assert.equal(f.presentation.getState().peakEstimatedBytes,61440);
  f.presentation.resize(24,24); assert.equal(f.allocations.length,2); assert.equal(f.disposed,1);
  assert.equal(f.presentation.getState().peakEstimatedBytes,96000); f.presentation.dispose();
});
