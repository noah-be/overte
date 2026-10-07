// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
test('optional asynchronous GPU observation preserves actual rendering and releases owned queries',async({page})=>{
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));await page.goto('/');
 const result=await page.evaluate(async()=>{const path='/tests/gpu-time-observer-fixture.ts';return(await import(/* @vite-ignore */ path)).auditGpuTimeObserver();});
 expect(result.webgl2).toBe(true);expect(result.before).toEqual(result.after);expect(result.pixel).toEqual([255,0,0,255]);
 if(result.measured.supported){expect(result.began).toBe(true);expect(result.measured.completed).toBe(1);expect(result.measured.totalGpuMs).toBeGreaterThanOrEqual(0);expect(result.measured.totalGpuMs).toBeLessThan(result.measured.timeoutMs);expect(result.measured.failed).toBe(0);expect(result.measured.disjointDropped).toBe(0);}
 else{expect(result.began).toBe(false);expect(result.measured.completed).toBe(0);expect(result.measured.peakQueries).toBe(0);}
 expect(result.disposed.disposed).toBe(true);expect(result.disposed.pending).toBe(0);expect(result.disposed.active).toBe(false);
});
