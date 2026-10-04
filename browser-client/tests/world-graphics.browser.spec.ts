// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
test('actual browser World graphics controls change local-light pixels, projection, framebuffer and constrained camera',async({page})=>{
    await page.goto('/');
    const result=await page.evaluate(async()=>{const path='/tests/world-graphics-fixture.ts';const {auditWorldGraphics}=await import(path);return auditWorldGraphics();});
    expect(result.webgl2).toBe(true);expect(result.warnings).toEqual([]);
    expect(result.lit[0]).toBeGreaterThan(80);expect(result.lit[0]).toBeGreaterThan(result.lit[1]+50);
    expect(result.dark.slice(0,3)).toEqual([0,0,0]);expect(result.relit).toEqual(result.lit);
    expect(result.narrow).not.toEqual(result.projectionBefore);expect(result.wide).not.toEqual(result.projectionBefore);expect(result.narrow[0]).toBeGreaterThan(result.wide[0]);
    for(const entry of result.resolutions){expect(entry.effective).toBe(entry.percent);expect(entry.width).toBe(Math.floor(result.base.width*entry.percent/100));expect(entry.height).toBe(Math.floor(result.base.height*entry.percent/100));}
    expect(result.camera.constrained).toBeLessThan(1.4);expect(result.camera.free).toBeCloseTo(3,5);expect(result.camera.restored).toBeCloseTo(result.camera.constrained,5);
    expect(result.effective).toEqual({version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true});
});
