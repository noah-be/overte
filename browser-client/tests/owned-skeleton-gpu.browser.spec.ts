// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
for(const survivor of [false,true])test('actual World skeleton disposal releases private GPU allocation and preserves other owner '+survivor,async({page},testInfo)=>{
 await page.goto('/');const reports=[];for(const enabled of [false,true])reports.push(await page.evaluate(async({enabled,survivor})=>{const path='/tests/owned-skeleton-gpu-fixture.ts';const {auditOwnedSkeletonGpu}=await import(/* @vite-ignore */path);return auditOwnedSkeletonGpu(enabled,survivor);},{enabled,survivor}));
 await testInfo.attach('owned-bone-texture-counterfactual',{body:JSON.stringify(reports),contentType:'application/json'});
 for(const report of reports){expect(report.webgl2).toBe(true);expect(report.visible).toBeGreaterThan(1000);expect(report.rootRetired).toBe(true);expect(report.cleanup).toBe(true);expect(report.buffers.before).toBe(0);expect(report.buffers.allocated).toBe(report.ownedSkeletons+report.retainedSkeletons);expect(report.events.retained).toBe(0);expect(report.retainedAlive).toBe(true);expect(report.buffers.final).toBe(0);if(survivor)expect(report.retainedVisible).toBeGreaterThan(500);else expect(report.retainedVisible).toBe(0);}
 expect(reports[1].hash).toBe(reports[0].hash);expect(reports[0].events.owned).toBe(0);expect(reports[0].buffers.after).toBe(reports[0].ownedSkeletons+reports[0].retainedSkeletons);expect(reports[1].events.owned).toBe(reports[1].ownedSkeletons);expect(reports[1].buffers.after).toBe(reports[1].retainedSkeletons);
});
