// SPDX-License-Identifier: Apache-2.0
// Focused native-asset geometry/render regression; not an avatar/domain journey.
import { test, expect } from '@playwright/test';

test('actual native mannequin geometry and textures retain WebGL pixels when compatible static instances batch', async ({ page }) => {
    await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' }));
    await page.goto('/');
    const result = await page.evaluate(async () => {
        const modulePath = '/tests/static-model-batch-fixture.ts';
        const { auditNativeStaticPixels } = await import(/* @vite-ignore */ modulePath);
        return auditNativeStaticPixels();
    });
    expect(result.nativeVertices).toBe(39552);
    expect(result.before.draws).toBe(3); expect(result.after.draws).toBe(1); expect(result.saved).toBe(2);
    expect(result.before.triangles).toBe(result.after.triangles);
    expect(result.visible).toBeGreaterThan(10000);
    expect(result.different).toBeLessThanOrEqual(12); // At most 0.005% edge pixels from equivalent Float32 transform rounding.
    expect(result.restoredDifferences).toBe(0); expect(result.unchangedMaterial).toBe(true);
});

test('mixed opaque batching preserves exact transparent order, equal-depth object-ID ties and visible blended pixels', async ({page}) => {
    await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));await page.goto('/');
    const result=await page.evaluate(async()=>{const modulePath='/tests/static-model-batch-fixture.ts';const {auditMixedStaticPixels}=await import(/* @vite-ignore */modulePath);return auditMixedStaticPixels();});
    expect(result.before.draws).toBe(6);expect(result.after.draws).toBe(5);expect(result.saved).toBe(1);
    expect(result.before.triangles).toBe(12);expect(result.after.triangles).toBe(12);expect(result.visible).toBeGreaterThan(10000);
    expect(result.different).toBe(0);expect(result.restoredDifferences).toBe(0);expect(result.originalIdentityPreserved).toBe(true);
    expect(result.sourceGeometryUnchanged).toBe(true);expect(result.exactReferenceRestored).toBe(true);
    expect(result.residualOrder).toEqual([{start:12,count:6,materialIndex:1},{start:18,count:6,materialIndex:1}]);
});
