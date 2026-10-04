// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('owned HDR world target blends linearly before native SRGB output and captures while paused', async ({ page }) => {
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' })); await page.goto('/');
  const result = await page.evaluate(async () => { const path = '/tests/world-presentation-fixture.ts'; return (await import(/* @vite-ignore */ path)).auditWorldPresentation(); });
  expect(result.webgl2).toBe(true); expect(result.capabilities.halfFloat).toBe(true); expect(result.capabilities.halfFloatSamples).toContain(4);
  expect(result.state.nativeHDR).toBe(true); expect(result.state.allocation?.samples).toBe(4); expect(result.state.allocation?.physicalWidth).toBe(128); expect(result.state.allocation?.physicalHeight).toBe(128);
  for (const [index, value] of [64, 128, 0, 255].entries()) expect(Math.abs(result.historical[index] - value)).toBeLessThanOrEqual(1);
  for (const [index, value] of result.expected.entries()) expect(Math.abs(result.native[index] - value)).toBeLessThanOrEqual(1);
  expect(result.drawCalls).toBe(2); expect(result.stable).toEqual({ materialVersion: true, programs: true, drawCalls: 2 }); expect(result.skipped).toBe(false);
  expect(result.snapshot.type).toBe('image/png'); expect(result.snapshot.width).toBe(128); expect(result.snapshot.height).toBe(128);
  for (const [index, value] of result.expectedSnapshot.entries()) expect(Math.abs(result.snapshot.pixel[index] - value)).toBeLessThanOrEqual(1);
  expect(result.restoredCustomTarget).toEqual({sameTarget:true,viewport:[2,3,17,19],scissor:[4,5,7,9],test:true,currentViewport:[2,3,17,19],metadataViewport:[2,3,17,19],metadataScissor:[4,5,7,9],metadataTest:true});
  expect(result.beforeDispose - result.afterDispose).toBe(1); expect(result.rendererRestored).toBe(true);
});
