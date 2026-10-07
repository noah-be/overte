// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import { applyNativeMaterialAlpha } from '../src/native-alpha-material';
import { applyNativeRenderState } from '../src/native-render-state';
import { hasNativeZeroLightShader, installNativeZeroLightShader } from '../src/native-zero-lights';

type Lit = THREE.MeshStandardMaterial | THREE.MeshPhongMaterial | THREE.MeshLambertMaterial;
type Image = Uint8Array | Uint16Array;
function halfRank(value: number) { return value & 0x8000 ? 0x8000 - (value & 0x7fff) : 0x8000 + value; }
function difference(a: Image, b: Image, half: boolean) {
  if (a.length !== b.length) throw Error('Pixel comparison dimensions changed');
  let maximum = 0, changed = 0;
  for (let index = 0; index < a.length; index++) {
    if (half && (!Number.isFinite(THREE.DataUtils.fromHalfFloat(a[index])) || !Number.isFinite(THREE.DataUtils.fromHalfFloat(b[index])))) throw Error('Nonfinite HDR pixels');
    const delta = half ? Math.abs(halfRank(a[index]) - halfRank(b[index])) : Math.abs(a[index] - b[index]);
    maximum = Math.max(maximum, delta); if (delta) changed++;
  }
  return { maximum, changed };
}

/** Controlled GPU comparison, not a performance result. Both sides use exactly
 * the same fixed sixteen lights, pixels, geometry, native alpha and render
 * state. Only the owned zero-light branch differs. No World hooks are changed. */
export async function auditNativeZeroLights() {
  const renderer = new THREE.WebGLRenderer({ antialias: false }); renderer.setSize(64, 64); renderer.setPixelRatio(1);
  renderer.toneMapping = THREE.NoToneMapping; renderer.setClearColor(0, 1); renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
  const gl = renderer.getContext(); if (!(gl instanceof WebGL2RenderingContext)) throw Error('Actual WebGL2 is required');
  const hdrSupported = Boolean(gl.getExtension('EXT_color_buffer_float'));
  const camera = new THREE.OrthographicCamera(-2, 2, 2, -2, .1, 20); camera.position.set(0, 0, 5);
  const geometry = new THREE.PlaneGeometry(3.5, 3.5), cubeGeometry = new THREE.BoxGeometry(.7, .7, .6);
  const alphaMap = new THREE.DataTexture(new Uint8Array([255,255,255,0, 255,255,255,255, 255,255,255,255, 255,255,255,0]), 2, 2, THREE.RGBAFormat);
  alphaMap.magFilter = alphaMap.minFilter = THREE.NearestFilter; alphaMap.needsUpdate = true;
  const spotMap = new THREE.DataTexture(new Uint8Array([255,200,80,255, 80,255,200,255, 200,80,255,255, 255,255,255,255]), 2, 2, THREE.RGBAFormat);
  spotMap.needsUpdate = true;
  const results = [];
  try {
    for (const name of ['standard-opaque', 'phong-opaque', 'lambert-opaque', 'physical-hdr', 'native-mask-shadow-map', 'native-blend-shadow-map'] as const) {
      const half = name === 'physical-hdr'; if (half && !hdrSupported) continue;
      const shadows = name.includes('shadow'), scene = new THREE.Scene();
      const target = new THREE.WebGLRenderTarget(64, 64, { type: half ? THREE.HalfFloatType : THREE.UnsignedByteType }); target.texture.colorSpace = THREE.LinearSRGBColorSpace;
      const material: Lit = name.startsWith('phong') ? new THREE.MeshPhongMaterial({ color: 0xaabbd0, shininess: 20 })
        : name.startsWith('lambert') ? new THREE.MeshLambertMaterial({ color: 0xaabbd0 })
        : half ? new THREE.MeshPhysicalMaterial({ color: 0xaabbd0, roughness: .35, metalness: .1, clearcoat: .4 })
        : new THREE.MeshStandardMaterial({ color: 0xaabbd0, roughness: .65, metalness: .1 });
      if (name.includes('mask')) { material.map = alphaMap; await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .375 }); }
      else if (name.includes('blend')) { material.map = alphaMap; material.opacity = .55; await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_BLEND' }); }
      applyNativeRenderState(material, { cullFaceMode: 'CULL_NONE' });
      const board = new THREE.Mesh(geometry, material); board.receiveShadow = true;
      const cubeMaterial = new THREE.MeshStandardMaterial({ color: 0xd0aa80, roughness: .7 }); applyNativeRenderState(cubeMaterial);
      const cube = new THREE.Mesh(cubeGeometry, cubeMaterial); cube.position.set(.25, .15, .6); cube.castShadow = shadows; cube.receiveShadow = true; scene.add(board, cube);
      scene.add(new THREE.AmbientLight(0xddddff, .1)); const direction = new THREE.DirectionalLight(0xffffff, .3); direction.position.set(0, 1, 2); scene.add(direction);
      const points: THREE.PointLight[] = [], spots: THREE.SpotLight[] = [];
      for (let index = 0; index < 8; index++) {
        const point = new THREE.PointLight(0xffffff, 0, 10, 2); point.position.set(-1.2 + index * .3, 1, 2.5);
        const spot = new THREE.SpotLight(0xffffff, 0, 10, Math.PI / 4, .25, 2); spot.position.set(1.2 - index * .3, 1, 2.5); spot.target.position.set(0, 0, 0);
        if (shadows && index < 2) {
          point.castShadow = true; point.shadow.mapSize.set(64, 64); point.shadow.camera.near = .1;
          spot.castShadow = true; spot.shadow.mapSize.set(64, 64); spot.shadow.camera.near = .1; spot.map = spotMap;
        }
        points.push(point); spots.push(spot); scene.add(point, spot, spot.target);
      }
      const sample = () => {
        renderer.setRenderTarget(target); renderer.render(scene, camera);
        const pixels = half ? new Uint16Array(64 * 64 * 4) : new Uint8Array(64 * 64 * 4);
        renderer.readRenderTargetPixels(target, 0, 0, 64, 64, pixels);
        return { pixels, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles };
      };
      const setLights = (state: 'mixed' | 'zero' | 'swapped') => {
        for (const light of [...points, ...spots]) { light.intensity = 0; light.color.setRGB(1, 1, 1); }
        if (state === 'zero') return;
        const index = state === 'mixed' ? 0 : 7;
        points[index].color.setRGB(.8, .25, .2); points[index].intensity = half ? 128 : 8;
        spots[index].color.setRGB(.2, .75, 1.2); spots[index].intensity = half ? 96 : 6;
        // Preserve actual negative and tiny one-channel uniforms; never use a
        // magnitude threshold. Four active slots remain below World's eight.
        points[3].color.setRGB(0, -.125, 0); points[3].intensity = .1;
        spots[3].color.setRGB(0, 0, .00001); spots[3].intensity = 1;
      };
      try {
        renderer.setRenderTarget(target); setLights('mixed'); await renderer.compileAsync(scene, camera);
        const references = new Map<string, ReturnType<typeof sample>>();
        for (const state of ['mixed', 'zero', 'swapped'] as const) { setLights(state); references.set(state, sample()); }
        let shadowDifference = 0;
        if (shadows) {
          setLights('mixed'); board.receiveShadow = false; const unshadowed = sample(); board.receiveShadow = true;
          shadowDifference = difference(references.get('mixed')!.pixels, unshadowed.pixels, half).maximum;
        }
        installNativeZeroLightShader(material); installNativeZeroLightShader(cubeMaterial); setLights('mixed'); await renderer.compileAsync(scene, camera);
        const versions = [material.version, cubeMaterial.version], programs = renderer.info.programs?.length, comparisons = [];
        for (const state of ['mixed', 'zero', 'swapped'] as const) {
          setLights(state); const guarded = sample(), reference = references.get(state)!;
          comparisons.push({ state, ...difference(reference.pixels, guarded.pixels, half), calls: guarded.calls, referenceCalls: reference.calls, triangles: guarded.triangles, referenceTriangles: reference.triangles });
        }
        const calls = [];
        for (let index = 0; index < 20; index++) { setLights(index % 2 ? 'mixed' : 'swapped'); calls.push(sample().calls); }
        const sources = (renderer.info.programs ?? []).map(program => gl.getShaderSource(program.fragmentShader) ?? '').filter(source => source.includes('notEqual( pointLight.color'));
        let maximumHdr = 0;
        if (half) for (const value of references.get('mixed')!.pixels) maximumHdr = Math.max(maximumHdr, THREE.DataUtils.fromHalfFloat(value));
        const mixedVsZero = difference(references.get('mixed')!.pixels, references.get('zero')!.pixels, half);
        const shadowMaps = [...points, ...spots].filter(light => light.castShadow).map(light => Boolean(light.shadow.map));
        results.push({ name, half, comparisons, shadowDifference, shadowMaps, maximumHdr, mixedVsZero, calls,
          versions, versionsAfter: [material.version, cubeMaterial.version], programs, programsAfter: renderer.info.programs?.length,
          uniformsOnly: points.length === 8 && spots.length === 8 && [...points, ...spots].every(light => light.visible),
          owned: hasNativeZeroLightShader(material) && hasNativeZeroLightShader(cubeMaterial),
          shaderLoops: sources.map(source => ({ points: source.match(/if \( any\( notEqual\( pointLight.color/g)?.length ?? 0, spots: source.match(/if \( any\( notEqual\( spotLight.color/g)?.length ?? 0 })) });
      } finally {
        renderer.setRenderTarget(null); for (const light of [...points, ...spots]) light.shadow.dispose();
        material.dispose(); cubeMaterial.dispose(); target.dispose();
      }
    }
    return { webgl2: true, hdrSupported, drawingBuffer: { width: gl.drawingBufferWidth, height: gl.drawingBufferHeight, pixelRatio: renderer.getPixelRatio() }, results };
  } finally { alphaMap.dispose(); spotMap.dispose(); geometry.dispose(); cubeGeometry.dispose(); renderer.dispose(); renderer.forceContextLoss(); }
}
