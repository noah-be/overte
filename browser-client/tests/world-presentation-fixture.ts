// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { BufferGeometry, Float32BufferAttribute, Mesh, MeshBasicMaterial, NoToneMapping, OrthographicCamera, Scene, SRGBColorSpace, Vector4, WebGLRenderer, WebGLRenderTarget } from 'three';
import { applyNativeRenderState } from '../src/native-render-state';
import { WorldPresentation } from '../src/world-presentation';

function srgb8(linear: number) { return Math.round(255 * (linear <= .0031308 ? 12.92 * linear : 1.055 * linear ** (1 / 2.4) - .055)); }
export async function auditWorldPresentation() {
  const renderer = new WebGLRenderer({ antialias: false, preserveDrawingBuffer: true }); renderer.setSize(64, 64); renderer.setClearColor(0, 1); renderer.toneMapping = NoToneMapping; renderer.outputColorSpace = SRGBColorSpace;
  const geometry = new BufferGeometry(); geometry.setAttribute('position', new Float32BufferAttribute([-1, -1, .1, 1, -1, .1, 0, 1, .1, -1, -1, 0, 0, 1, 0, 1, -1, 0], 3));
  geometry.setAttribute('color', new Float32BufferAttribute([1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0], 3)); geometry.setIndex([0, 1, 2, 3, 4, 5]);
  const material = new MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: .5 }); applyNativeRenderState(material, { cullFaceMode: 'CULL_NONE' });
  const scene = new Scene(); scene.add(new Mesh(geometry, material)); const camera = new OrthographicCamera(-1, 1, 1, -1, .1, 10); camera.position.z = 2;
  const context = renderer.getContext();
  const pixels = () => { const buffer = new Uint8Array(4); context.readPixels(renderer.domElement.width / 2, renderer.domElement.height / 2, 1, 1, context.RGBA, context.UNSIGNED_BYTE, buffer); return Array.from(buffer); };
  const presentation = new WorldPresentation(renderer, { samples: 4 });
  try {
    renderer.render(scene, camera); const historical = pixels();
    presentation.resize(64, 64, 2); presentation.render(scene, camera); const native = pixels(), state = presentation.getState();
    const drawCalls = renderer.info.render.calls, version = material.version, programs = renderer.info.programs?.length;
    for (let index = 0; index < 20; index++) presentation.render(scene, camera);
    const stable = { materialVersion: material.version === version, programs: renderer.info.programs?.length === programs, drawCalls: renderer.info.render.calls };
    const previous = new WebGLRenderTarget(53,47); previous.viewport.set(2,3,17,19); previous.scissor.set(4,5,7,9); previous.scissorTest = true;
    let restoredCustomTarget;
    try {
      renderer.setRenderTarget(previous); presentation.render(scene,camera);
      const viewport = Array.from(context.getParameter(context.VIEWPORT) as Int32Array), scissor = Array.from(context.getParameter(context.SCISSOR_BOX) as Int32Array);
      restoredCustomTarget = {sameTarget: renderer.getRenderTarget() === previous, viewport, scissor, test: context.isEnabled(context.SCISSOR_TEST), currentViewport: renderer.getCurrentViewport(new Vector4()).toArray(), metadataViewport: previous.viewport.toArray(), metadataScissor: previous.scissor.toArray(), metadataTest: previous.scissorTest};
    } finally {renderer.setRenderTarget(null);previous.dispose();}
    presentation.setEnabled(false); const skipped = presentation.render(scene, camera); material.opacity = .25;
    const snapshot = await presentation.capture(scene, camera), bitmap = await createImageBitmap(snapshot);
    const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height; const ctx = canvas.getContext('2d')!; ctx.drawImage(bitmap, 0, 0); const exported = Array.from(ctx.getImageData(bitmap.width / 2, bitmap.height / 2, 1, 1).data); bitmap.close();
    const beforeDispose = renderer.info.memory.textures; presentation.dispose(); const afterDispose = renderer.info.memory.textures;
    return { webgl2: context instanceof WebGL2RenderingContext, capabilities: presentation.capabilities, historical, native, state, drawCalls, stable, restoredCustomTarget, skipped, snapshot: { type: snapshot.type, width: canvas.width, height: canvas.height, pixel: exported }, expected: [srgb8(.25), srgb8(.5), 0, 255], expectedSnapshot: [srgb8(.1875), srgb8(.25), 0, 255], beforeDispose, afterDispose, rendererRestored: renderer.toneMapping === NoToneMapping && renderer.outputColorSpace === SRGBColorSpace && renderer.getRenderTarget() === null };
  } finally { presentation.dispose(); geometry.dispose(); material.dispose(); renderer.dispose(); }
}
