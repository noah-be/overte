// SPDX-License-Identifier: Apache-2.0
// Actual WebGL/renderer component proof; no public-world or speed claims.
import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' }));
  await page.goto('/');
});

test('current Three cache equals actual WebGL capabilities before and after genuine context restoration', async ({ page }) => {
  const result = await page.evaluate(async () => {
    const threePath = '/node_modules/three/build/three.module.js';
    const helperPath = '/src/compressed-color-capabilities.ts';
    const THREE = await import(/* @vite-ignore */ threePath);
    const { currentCompressedColorCapabilities: read } = await import(/* @vite-ignore */ helperPath);
    const renderer = new THREE.WebGLRenderer();
    const gl = renderer.getContext();
    const raw = () => ({ s3tc: !!gl.getExtension('WEBGL_compressed_texture_s3tc'), s3tcSRGB: !!gl.getExtension('WEBGL_compressed_texture_s3tc_srgb'), maximumTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE) });
    const before = { cached: read(renderer), raw: raw() };
    const previousCapabilities = renderer.capabilities, previousExtensions = renderer.extensions;
    const lose = gl.getExtension('WEBGL_lose_context');
    if (!lose) throw Error('Actual browser context-loss extension is required for this proof');
    try {
      await new Promise<void>((resolve, reject) => {
        const deadline = setTimeout(() => reject(Error('Actual context restoration exceeded 10 seconds')), 10000);
        renderer.domElement.addEventListener('webglcontextlost', (event: Event) => { event.preventDefault(); setTimeout(() => lose.restoreContext(), 30); }, { once: true });
        renderer.domElement.addEventListener('webglcontextrestored', () => { clearTimeout(deadline); resolve(); }, { once: true });
        lose.loseContext();
      });
      return { before, after: { cached: read(renderer), raw: raw() }, capabilitiesReplaced: previousCapabilities !== renderer.capabilities, extensionsReplaced: previousExtensions !== renderer.extensions };
    } finally { renderer.dispose(); }
  });
  expect(result.before.cached).toEqual(result.before.raw);
  expect(result.after.cached).toEqual(result.after.raw);
  expect(result.capabilitiesReplaced).toBe(true);
  expect(result.extensionsReplaced).toBe(true);
});

test('every actual World texmeta reader checks current approval while avoiding repeated raw size queries', async ({ page }) => {
  const result = await page.evaluate(async () => {
    const worldPath = '/src/world.ts';
    const { BrowserWorld } = await import(/* @vite-ignore */ worldPath);
    const container = document.createElement('div'); container.style.cssText = 'width:128px;height:128px'; document.body.append(container);
    const capabilities: unknown[] = [], denials: string[] = []; let authorityCalls = 0, resolverCalls = 0;
    const world = new BrowserWorld(container, {
      resolveAsset: (url: string) => { resolverCalls++; return url; }, onPose() {}, onInteract() {}, onStatus() {},
      compressedColors: (current: unknown) => { capabilities.push(current); return { captureApproval() { throw Error(`Current approval refused reader ${++authorityCalls}`); } }; },
    });
    const privateWorld = world as unknown as { renderer: { getContext(): WebGL2RenderingContext }; originalTexture(url: string, color: boolean, role: string): Promise<unknown> };
    const gl = privateWorld.renderer.getContext(), originalGet = gl.getParameter.bind(gl);
    const raw = { s3tc: !!gl.getExtension('WEBGL_compressed_texture_s3tc'), s3tcSRGB: !!gl.getExtension('WEBGL_compressed_texture_s3tc_srgb'), maximumTextureSize: originalGet(gl.MAX_TEXTURE_SIZE) };
    let rawSizeQueries = 0;
    gl.getParameter = ((parameter: number) => { if (parameter === gl.MAX_TEXTURE_SIZE) rawSizeQueries++; return originalGet(parameter); }) as typeof gl.getParameter;
    try {
      for (let i = 0; i < 2; i++) {
        try { await privateWorld.originalTexture('https://fixture.invalid/color.texmeta.json', true, 'albedo'); }
        catch (error) { denials.push(error instanceof Error ? error.message : String(error)); }
      }
      return { raw, capabilities, authorityCalls, resolverCalls, denials, rawSizeQueries };
    } finally { gl.getParameter = originalGet; world.dispose(); container.remove(); }
  });
  expect(result.capabilities).toEqual([result.raw, result.raw]);
  expect(result.authorityCalls).toBe(2);
  expect(result.denials).toEqual(['Current approval refused reader 1', 'Current approval refused reader 2']);
  expect(result.resolverCalls).toBe(0);
  expect(result.rawSizeQueries).toBe(0);
});
