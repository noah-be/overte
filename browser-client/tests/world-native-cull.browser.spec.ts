// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
// Same independently authored indexed asset/cases as the real native observer.
const { nativeWindingAsset, nativeWindingCases } = require('./integration/native-winding-assets.mjs') as {
  nativeWindingAsset(): unknown;
  nativeWindingCases: { name: string; cull: 'CULL_BACK'|'CULL_FRONT'|'CULL_NONE'|null; unlit: boolean; lightDirection: {z:-1|1}; dominant?: string[]; brighter?: string }[];
};

test('actual World native cull opt-in preserves mirrored face and normal classification without program churn', async ({ page }) => {
  await page.route('**/__native-winding-world.gltf', route => route.fulfill({ contentType: 'model/gltf+json', body: JSON.stringify(nativeWindingAsset()) }));
  await page.goto('/');
  for (const entry of nativeWindingCases) {
    const result = await page.evaluate(async input => {
      const path = '/tests/world-native-cull-fixture.ts'; const { auditWorldNativeCull } = await import(path);
      return auditWorldNativeCull(input);
    }, { url: '/__native-winding-world.gltf', cull: entry.cull, unlit: entry.unlit, lightZ: entry.lightDirection.z });
    expect(result.webgl2).toBe(true); expect(result.convertedMeshes).toBe(1); expect(result.vertexColors).toEqual([true,true]);
    expect(result.versionsStable).toBe(true); expect(result.programsStable).toBe(true); expect(result.calls.every((value:number) => value === 2)).toBe(true);
    if (entry.dominant) for (let index = 0; index < 2; index++) {
      const color = entry.dominant[index] === 'red' ? 0 : 1;
      expect(result.pixels[index][color], `${entry.name} ${index ? 'mirrored' : 'positive'} actual authored face`).toBeGreaterThan(result.pixels[index][1-color] + 15);
    } else {
      const bright = entry.brighter === 'positive' ? 0 : 1, dark = 1-bright;
      expect(result.pixels[bright][0], entry.name).toBeGreaterThan(result.pixels[dark][0] + 30);
      expect(result.pixels[bright][0], 'controlled real light must illuminate the surface').toBeGreaterThan(60);
    }
  }
});
