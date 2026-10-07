// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('native glTF discards authored vertex alpha while retaining material opacity', async ({ page }) => {
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' })); await page.goto('/');
  const result = await page.evaluate(async () => { const path = '/tests/native-gltf-colors-fixture.ts'; return (await import(/* @vite-ignore */ path)).auditNativeGltfColors(); });
  expect(result.webgl2).toBe(true); expect(result.before).toEqual([0, 0, 0, 255]);
  expect(result.converted).toBe(1); expect(result.colorItemSize).toBe(3); expect(result.normalized).toBe(false);
  expect(result.opacity).toBe(.5); expect(result.vertexColors).toBe(true);
  // Native HFMMesh stores RGB only. Linear source-alpha blending therefore
  // leaves one-half red, despite COLOR_0's discarded all-zero alpha bytes.
  expect(Math.abs(result.after[0] - 128)).toBeLessThanOrEqual(1);
  expect(result.after.slice(1)).toEqual([0, 0, 255]);
});
