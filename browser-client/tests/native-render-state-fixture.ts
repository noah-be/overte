// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import { applyNativeRenderState, type NativeCullFaceMode } from '../src/native-render-state';

// One indexed mesh: the near RED front-facing triangle is first, and the GREEN
// rear back-facing triangle second. Native one-draw blending preserves this
// index order. Three's default two-pass transparency reverses these two faces.
const positions = new Float32Array([-1,-1,.1, 1,-1,.1, 0,1,.1, -1,-1,0, 0,1,0, 1,-1,0]);
const colors = new Float32Array([1,0,0, 1,0,0, 1,0,0, 0,1,0, 0,1,0, 0,1,0]);
const indices = new Uint16Array([0,1,2,3,4,5]);

/** Independent GPU reference using the exact native standard pipeline state.
 * This is source-backed OpenGL-state validation; an actual native-client image
 * comparison is a separate integration proof, not claimed by this fixture.
 */
function nativeStateReference(mode: NativeCullFaceMode): number[] {
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 16;
  const gl = canvas.getContext('webgl2', { alpha: false, antialias: false }); if (!gl) throw Error('Actual WebGL2 is required');
  const shaders: WebGLShader[] = [], buffers: WebGLBuffer[] = []; let program: WebGLProgram | null = null;
  try {
    function compile(kind: number, source: string) {
      const shader = gl!.createShader(kind)!; shaders.push(shader); gl!.shaderSource(shader, source); gl!.compileShader(shader);
      if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS)) throw Error(gl!.getShaderInfoLog(shader) || 'Reference shader compilation failed'); return shader;
    }
    program = gl.createProgram()!;
    gl.attachShader(program, compile(gl.VERTEX_SHADER, '#version 300 es\nin vec3 position; in vec3 color; out vec3 vColor; void main(){vColor=color; gl_Position=vec4(position.xy, -position.z, 1.0);}'));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, '#version 300 es\nprecision highp float; in vec3 vColor; out vec4 outputColor; void main(){outputColor=vec4(vColor,.5);}'));
    gl.linkProgram(program); if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program) || 'Reference linking failed'); gl.useProgram(program);
    for (const [name, values] of [['position', positions], ['color', colors]] as const) {
      const buffer = gl.createBuffer()!; buffers.push(buffer); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, values, gl.STATIC_DRAW);
      const location = gl.getAttribLocation(program, name); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location, 3, gl.FLOAT, false, 0, 0);
    }
    const index = gl.createBuffer()!; buffers.push(index); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, index); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
    gl.viewport(0, 0, 16, 16); gl.clearColor(0, 0, 0, 1); gl.clearDepth(1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(false); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    if (mode === 'CULL_NONE') gl.disable(gl.CULL_FACE); else { gl.enable(gl.CULL_FACE); gl.cullFace(mode === 'CULL_BACK' ? gl.BACK : gl.FRONT); }
    gl.drawElements(gl.TRIANGLES, indices.length, gl.UNSIGNED_SHORT, 0);
    const pixel = new Uint8Array(4); gl.readPixels(8, 8, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel); return [...pixel];
  } finally {
    for (const buffer of buffers) gl.deleteBuffer(buffer); for (const shader of shaders) gl.deleteShader(shader); if (program) gl.deleteProgram(program);
    gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
}

export async function auditNativeRenderState() {
  const renderer = new THREE.WebGLRenderer({ antialias: false }); renderer.setSize(16, 16); renderer.setClearColor(0, 1); renderer.toneMapping = THREE.NoToneMapping;
  const target = new THREE.WebGLRenderTarget(16, 16); target.texture.colorSpace = THREE.LinearSRGBColorSpace;
  renderer.setRenderTarget(target);
  const geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(positions, 3)).setAttribute('color', new THREE.BufferAttribute(colors, 3)); geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  const material = new THREE.MeshBasicMaterial({ vertexColors: true, opacity: .5, transparent: true, side: THREE.DoubleSide, toneMapped: false });
  const scene = new THREE.Scene(), mesh = new THREE.Mesh(geometry, material); scene.add(mesh);
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .1, 10); camera.position.z = 2;
  const pixel = () => { const value = new Uint8Array(4); renderer.readRenderTargetPixels(target, 8, 8, 1, 1, value); return [...value]; };
  try {
    // Retain legacy draw ordering but remove the depth-write mismatch, to isolate
    // the exact two-pass versus native index-order composition difference.
    material.depthWrite = false; renderer.render(scene, camera);
    const legacy = { pixel: pixel(), calls: renderer.info.render.calls };
    const results = [];
    for (const mode of ['CULL_NONE', 'CULL_BACK', 'CULL_FRONT'] as const) {
      applyNativeRenderState(material, { cullFaceMode: mode }); await renderer.compileAsync(scene, camera);
      const before = material.version, programs = renderer.info.programs?.length;
      const calls: number[] = []; for (let i = 0; i < 20; i++) { renderer.render(scene, camera); calls.push(renderer.info.render.calls); }
      results.push({ mode, pixel: pixel(), reference: nativeStateReference(mode), calls, versionBefore: before, versionAfter: material.version, programsBefore: programs, programsAfter: renderer.info.programs?.length, depthWrite: material.depthWrite });
    }
    // Instancing retains its actual single indexed draw rather than expanding
    // visitors' repeated geometry into the historical two culling passes.
    scene.remove(mesh); applyNativeRenderState(material, { cullFaceMode: 'CULL_NONE' });
    const instances = new THREE.InstancedMesh(geometry, material, 2); instances.setMatrixAt(0, new THREE.Matrix4().makeTranslation(-.2, 0, 0)); instances.setMatrixAt(1, new THREE.Matrix4().makeTranslation(.2, 0, 0)); instances.instanceMatrix.needsUpdate = true; scene.add(instances);
    renderer.render(scene, camera); const instanceCalls = renderer.info.render.calls; instances.dispose();
    return { legacy, results, instanceCalls, webgl2: renderer.getContext() instanceof WebGL2RenderingContext };
  } finally { material.dispose(); geometry.dispose(); target.dispose(); renderer.dispose(); renderer.forceContextLoss(); }
}
