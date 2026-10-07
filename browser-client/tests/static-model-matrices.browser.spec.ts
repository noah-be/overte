// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);const {nativeWindingAsset}=require('./integration/native-winding-assets.mjs');
test('actual World static matrix opt-in preserves all pixels, picking, transformed geometry and material rebuilds',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await page.route('**/__static-model-matrices.gltf',route=>route.fulfill({contentType:'model/gltf+json',body:JSON.stringify(nativeWindingAsset())}));await page.goto('/');
 const records=[];for(const enabled of [false,true])records.push(await page.evaluate(async(enabled)=>{const path='/tests/static-model-matrices-fixture.ts';const {auditStaticModelMatrices}=await import(/* @vite-ignore */path);return auditStaticModelMatrices('/__static-model-matrices.gltf',enabled);},enabled));
 await testInfo.attach('actual-static-matrix-preservation',{contentType:'application/json',body:JSON.stringify({browser:page.context().browser()?.version(),project:testInfo.project.name,records,errors})});
 expect(errors).toEqual([]);expect(records.every(record=>record.webgl2)).toBe(true);expect(records.map(record=>record.warnings)).toEqual([[],[]]);
 expect(records[1].records).toEqual(records[0].records);expect(records[0].records).toHaveLength(6);
 const initial=records[0].records[0] as {center:number[];hits:unknown[]};expect(initial.center[0]).toBeGreaterThan(initial.center[1]+15);expect(initial.hits.length).toBeGreaterThan(0);
 expect(records[0].statistics).toEqual({enabled:false});const optimized=records[1].statistics as {skippedTraversals:number;updatedTraversals:number;activeRoots:number;retainedNodes:number};expect(optimized.skippedTraversals).toBeGreaterThanOrEqual(100);expect(optimized.updatedTraversals).toBeGreaterThanOrEqual(4);expect(optimized.activeRoots).toBe(0);expect(optimized.retainedNodes).toBe(0);
});
