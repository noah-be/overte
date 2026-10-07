// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import type { auditNativeZeroLights } from './native-zero-lights-fixture';

test('owned exact-zero light branches preserve full mixed-light pixels, HDR, alpha, shadows and stable programs', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message)); page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' })); await page.goto('/');
  const report = await page.evaluate(async () => { const path = '/tests/native-zero-lights-fixture.ts'; return (await import(/* @vite-ignore */ path)).auditNativeZeroLights(); }) as Awaited<ReturnType<typeof auditNativeZeroLights>>;
  expect(report.webgl2).toBe(true); expect(report.hdrSupported).toBe(true); expect(report.drawingBuffer).toEqual({ width: 64, height: 64, pixelRatio: 1 });
  expect(report.results.map(result => result.name)).toEqual(['standard-opaque', 'phong-opaque', 'lambert-opaque', 'physical-hdr', 'native-mask-shadow-map', 'native-blend-shadow-map']);
  for (const result of report.results) {
    expect(result.owned).toBe(true); expect(result.uniformsOnly).toBe(true);
    expect(result.mixedVsZero.changed).toBeGreaterThan(64);
    if (result.half) expect(result.maximumHdr).toBeGreaterThan(1);
    for (const comparison of result.comparisons) {
      // RGBA8 quantization: at most one byte step; HDR: two half-float ULPs.
      // All 16,384 components are compared, including alpha and masked holes.
      expect(comparison.maximum).toBeLessThanOrEqual(result.half ? 2 : 1);
      expect(comparison.calls).toBe(comparison.referenceCalls); expect(comparison.triangles).toBe(comparison.referenceTriangles);
    }
    expect(result.versionsAfter).toEqual(result.versions); expect(result.programsAfter).toBe(result.programs);
    // Compatible Standard materials may share one actual GPU program.
    expect(new Set(result.calls).size).toBe(1); expect(result.shaderLoops.length).toBeGreaterThanOrEqual(1);
    for (const loops of result.shaderLoops) expect(loops).toEqual({ points: 8, spots: 8 });
    if (result.name.includes('shadow')) { expect(result.shadowMaps).toEqual([true,true,true,true]); expect(result.shadowDifference).toBeGreaterThan(1); }
  }
  expect(errors).toEqual([]);
});
