// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
test('actual World 4096 images preserve residual alpha, native UVs, samplers, exact pixels and lease cleanup',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('/');const report=await page.evaluate(async()=>{const path='/tests/fixtures/world-bitmap-integration.ts';return(await import(/* @vite-ignore */path)).runWorldBitmapIntegrationProof();});
 await testInfo.attach('world-4096-bitmap-original-comparison',{contentType:'application/json',body:JSON.stringify({browser:page.context().browser()?.version(),project:testInfo.project.name,report,errors})});
 expect(errors).toEqual([]);expect(report.qualityChanged).toBe(false);expect(report.width).toBe(4096);expect(report.height).toBe(4096);expect(report.reports).toHaveLength(2);
 const [original,prepared]=report.reports;expect(prepared.pixelHash).toBe(original.pixelHash);expect(prepared.states).toEqual(original.states);expect(prepared.programsBefore).toBe(original.programsBefore);expect(prepared.programsAfter).toBe(original.programsAfter);
 for(const row of report.reports){expect(row.warnings).toEqual([]);expect(row.reds).toBeGreaterThan(0);expect(row.greens).toBeGreaterThan(0);expect(row.blues).toBeGreaterThan(0);expect(row.disposal.objects).toBe(0);expect(row.disposal.textures).toBe(0);expect(row.disposal.geometries).toBe(0);expect(Number.isFinite(row.firstRenderMs)).toBe(true);}
 expect(original.uploads.imageCalls).toBe(2);expect(original.uploads.bitmapCalls).toBe(0);expect(prepared.uploads.bitmapCalls).toBe(2);expect(prepared.uploads.imageCalls).toBe(0);
 expect(prepared.statistics.enabled).toBe(true);expect(prepared.statistics.created).toBe(1);expect(prepared.statistics.converted).toBe(2);
 expect(prepared.disposal.owner.leases).toBe(0);expect(prepared.disposal.owner.bytes).toBe(0);expect(prepared.disposal.owner.active).toBe(0);expect(prepared.disposal.owner.closeFailures).toBe(0);expect(prepared.disposal.owner.closed).toBe(1);
});
