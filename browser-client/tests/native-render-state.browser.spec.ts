// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('native one-draw transparency preserves indexed face order, culling, depth and stable shader versions', async ({ page }) => {
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' })); await page.goto('/');
  const result = await page.evaluate(async () => { const path = '/tests/native-render-state-fixture.ts'; return (await import(/* @vite-ignore */ path)).auditNativeRenderState(); });
  expect(result.webgl2).toBe(true); expect(result.legacy.calls).toBe(2);
  for (const [index, value] of [128, 64, 0].entries()) expect(Math.abs(result.legacy.pixel[index] - value)).toBeLessThanOrEqual(1);
  const expected = { CULL_NONE: [64, 128, 0], CULL_BACK: [128, 0, 0], CULL_FRONT: [0, 128, 0] };
  for (const state of result.results) {
    for (const [index, value] of expected[state.mode as keyof typeof expected].entries()) {
      expect(Math.abs(state.pixel[index] - value)).toBeLessThanOrEqual(1);
      expect(Math.abs(state.reference[index] - value)).toBeLessThanOrEqual(1);
      expect(Math.abs(state.pixel[index] - state.reference[index])).toBeLessThanOrEqual(1);
    }
    expect(state.calls).toEqual(Array(20).fill(1)); expect(state.versionAfter).toBe(state.versionBefore); expect(state.programsAfter).toBe(state.programsBefore); expect(state.depthWrite).toBe(false);
  }
  expect(result.instanceCalls).toBe(1);
});
