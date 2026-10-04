// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { LinearSRGBColorSpace, NoToneMapping, OrthographicCamera, Scene, WebGLRenderer, WebGLRenderTarget } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { normalizeNativeGltfColors } from '../src/native-gltf-colors';
import { applyNativeModelRenderState } from '../src/native-render-state';

export async function auditNativeGltfColors() {
  // Actual glTF-loader input: indexed CCW triangle, normalized byte RGBA red,
  // zero authored vertex alpha, independent material opacity of one half.
  const positions = new Float32Array([-1, -1, 0, 1, -1, 0, 0, 1, 0]);
  const colors = new Uint8Array([255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0]);
  const indices = new Uint16Array([0, 1, 2]);
  const bytes = new Uint8Array(positions.byteLength + colors.byteLength + indices.byteLength);
  bytes.set(new Uint8Array(positions.buffer)); bytes.set(colors, positions.byteLength); bytes.set(new Uint8Array(indices.buffer), positions.byteLength + colors.byteLength);
  const asset = {
    asset: { version: '2.0' }, extensionsUsed: ['KHR_materials_unlit'], scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, COLOR_0: 1 }, indices: 2, material: 0 }] }],
    materials: [{ extensions: { KHR_materials_unlit: {} }, doubleSided: true, alphaMode: 'BLEND', pbrMetallicRoughness: { baseColorFactor: [1, 1, 1, .5] } }],
    buffers: [{ byteLength: bytes.length, uri: 'data:application/octet-stream;base64,' + btoa(String.fromCharCode(...bytes)) }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: positions.byteLength }, { buffer: 0, byteOffset: positions.byteLength, byteLength: colors.byteLength }, { buffer: 0, byteOffset: positions.byteLength + colors.byteLength, byteLength: indices.byteLength }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [-1, -1, 0], max: [1, 1, 0] }, { bufferView: 1, componentType: 5121, normalized: true, count: 3, type: 'VEC4' }, { bufferView: 2, componentType: 5123, count: 3, type: 'SCALAR' }],
  };
  const model = (await new GLTFLoader().parseAsync(JSON.stringify(asset), '')).scene;
  const scene = new Scene(); scene.add(model);
  const camera = new OrthographicCamera(-1, 1, 1, -1, .1, 10); camera.position.z = 2;
  const renderer = new WebGLRenderer({ antialias: false }); renderer.setSize(32, 32); renderer.setClearColor(0, 1); renderer.toneMapping = NoToneMapping;
  const target = new WebGLRenderTarget(32, 32); target.texture.colorSpace = LinearSRGBColorSpace; renderer.setRenderTarget(target);
  const pixel = () => { renderer.render(scene, camera); const out = new Uint8Array(4); renderer.readRenderTargetPixels(target, 16, 16, 1, 1, out); return Array.from(out); };
  try {
    applyNativeModelRenderState(model);
    const before = pixel(), converted = normalizeNativeGltfColors(model), after = pixel();
    let colorItemSize = 0, opacity = 0, normalized = true, vertexColors = false;
    model.traverse(object => { const mesh = object as import('three').Mesh; if (!mesh.isMesh) return; colorItemSize = mesh.geometry.getAttribute('color').itemSize; normalized = mesh.geometry.getAttribute('color').normalized; const material = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material; opacity = material.opacity; vertexColors = material.vertexColors; });
    return { webgl2: renderer.getContext() instanceof WebGL2RenderingContext, before, converted, after, colorItemSize, opacity, normalized, vertexColors };
  } finally {
    model.traverse(object => { const mesh = object as import('three').Mesh; if (!mesh.isMesh) return; mesh.geometry.dispose(); for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) material.dispose(); });
    target.dispose(); renderer.dispose();
  }
}
