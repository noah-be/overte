// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Renderer components use generated RGBA images; actual Hub proof remains separate.
import { test, expect } from '@playwright/test';

test('actual world material factory honors native alpha eligibility, explicit modes, scalar opacity and cloning', async ({ page }) => {
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body><div id="world" style="width:100px;height:100px"></div></body></html>' }));
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const threePath = '/node_modules/three/build/three.module.js', worldPath = '/src/world.ts', alphaPath = '/src/native-alpha-material.ts';
    const THREE = await import(/* @vite-ignore */threePath);
    const { BrowserWorld } = await import(/* @vite-ignore */worldPath);
    const { cloneNativeMaterial } = await import(/* @vite-ignore */alphaPath);
    const world = new BrowserWorld(document.querySelector('#world')!, { resolveAsset: (url: string) => url, onPose() {}, onInteract() {}, onStatus() {} });
    const source = document.createElement('canvas'); source.width = 4; source.height = 1;
    source.getContext('2d')!.putImageData(new ImageData(new Uint8ClampedArray([0, 0, 0, 0, 0, 255, 0, 64, 0, 255, 0, 191, 0, 0, 0, 255]), 4, 1), 0, 0);
    const url = source.toDataURL('image/png');
    const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false }); renderer.setSize(64, 16); renderer.setClearColor(0x3366ff);
    renderer.toneMapping = THREE.NoToneMapping;
    const scene = new THREE.Scene(), camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .1, 10); camera.position.z = 2;
    const geometry = new THREE.PlaneGeometry(2, 2), mesh = new THREE.Mesh(geometry); scene.add(mesh);
    const modes: Record<string, { classification: string; pixels: number[][] }> = {};
    try {
      for (const [name, options] of [
        ['ineligible', {}], ['inferred', { opacityMap: url }],
        ['opaque', { opacityMap: url, opacityMapMode: 'OPACITY_MAP_OPAQUE' }],
        ['mask', { opacityMapMode: 'OPACITY_MAP_MASK', opacityCutoff: .5 }],
        ['maskQuarter', { opacityMapMode: 'OPACITY_MAP_MASK', opacityCutoff: .5, opacity: .25 }],
        ['opaqueQuarter', { opacityMapMode: 'OPACITY_MAP_OPAQUE', opacity: .25 }],
        ['ineligibleQuarter', { opacity: .25 }],
        ['blendQuarter', { opacityMapMode: 'OPACITY_MAP_BLEND', opacity: .25 }],
      ] as const) {
        const material = await (world as any).makeMaterial({ albedoMap: url, unlit: true, ...options });
        material.map.magFilter = material.map.minFilter = THREE.NearestFilter;
        const cloned = cloneNativeMaterial(material); mesh.material = cloned;
        renderer.render(scene, camera);
        const gl = renderer.getContext(), pixels: number[][] = [];
        for (const x of [8, 24, 40, 56]) { const pixel = new Uint8Array(4); gl.readPixels(x, 8, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel); pixels.push([...pixel]); }
        modes[name] = { classification: cloned.userData.nativeAlpha.classification, pixels };
        cloned.dispose(); material.map.dispose(); material.dispose();
      }
      return modes;
    } finally { world.dispose(); geometry.dispose(); renderer.dispose(); }
  });
  expect(result.ineligible.classification).toBe('opaque');
  expect(result.inferred.classification).toBe('blend');
  expect(result.opaque.pixels).toEqual(result.ineligible.pixels);
  expect(result.mask.pixels[0]).toEqual([51, 102, 255, 255]);
  expect(result.mask.pixels[1]).toEqual([51, 102, 255, 255]);
  expect(result.mask.pixels[2]).toEqual([0, 255, 0, 255]);
  // Fully opaque black is authored color, never an invented transparency mask.
  expect(result.mask.pixels[3]).toEqual([0, 0, 0, 255]);
  expect(result.maskQuarter.pixels[0]).toEqual(result.mask.pixels[0]);
  expect(result.maskQuarter.pixels[1]).toEqual(result.mask.pixels[1]);
  // Binary masking keeps this texel, then authored opacity blends one quarter
  // green with three quarters background: round([51,102,255]*.75+[0,255,0]*.25).
  [38,140,191,255].forEach((channel,index)=>expect(Math.abs(result.maskQuarter.pixels[2][index]-channel)).toBeLessThanOrEqual(1));
  // Native automatic flags do not erase RGBA: scalar translucency multiplies
  // map alpha even for explicit opaque or an ineligible albedo/opacity pair.
  expect(result.opaqueQuarter.pixels).toEqual(result.blendQuarter.pixels);
  expect(result.ineligibleQuarter.pixels).toEqual(result.blendQuarter.pixels);
  expect(result.opaqueQuarter.pixels[0]).toEqual([51, 102, 255, 255]);
  expect(result.opaqueQuarter.pixels[1]).not.toEqual(result.opaqueQuarter.pixels[2]);
});
