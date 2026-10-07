// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
import type {auditGraphicsWarmup,auditGraphicsWarmupCancellation} from './graphics-warmup-fixture';
async function fixturePage(page:import('@playwright/test').Page){
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));await page.goto('/');return errors;
}
test('yielded actual compiler preserves independent cold renderer RGBA through camera, skin, instance, morph and every root material binding',async({page},testInfo)=>{
 const errors=await fixturePage(page);
 const report=await page.evaluate(async()=>{const source='/tests/graphics-warmup-fixture.ts';return (await import(/* @vite-ignore */source)).auditGraphicsWarmup();}) as Awaited<ReturnType<typeof auditGraphicsWarmup>>;
 await testInfo.attach('graphics-warmup-fidelity',{contentType:'application/json',body:JSON.stringify({schemaVersion:1,browser:page.context().browser()?.version(),project:testInfo.project.name,report,errors})});
 expect(report.webgl2).toBe(true);expect(report.statistics.fallback).toBeNull();expect(report.statistics.bindings).toBe(14);expect(report.statistics.batches).toBe(4);expect(report.statistics.yielded).toBe(4);
 expect(report.components).toBe(96*96*4);expect(report.nonBackground).toBeGreaterThan(100);expect(report.changedAnimationComponents).toBeGreaterThan(100);
 expect(report.frames).toHaveLength(21);expect(report.maximum).toBe(0);expect(report.changed).toBe(0);
 for(const frame of report.frames){expect(frame.changed).toBe(0);expect(frame.maximum).toBe(0);expect(frame.calls).toBe(frame.directCalls);expect(frame.triangles).toBe(frame.directTriangles);expect(frame.programs).toBe(frame.directPrograms);}
 for(const key of ['finalRootExact','finalCameraExact','finalSceneExact','warmInputs','callsEqual','trianglesEqual','stableCalls','stablePrograms','stableVersions','coldProgramCountsEqual','retainedHooks','nativeAlphaInitiallyCorrect','nativeAlphaRetained','sharedRendererDFG','actualShadowMap','retainedInputs'] as const)expect(report[key],key).toBe(true);
 expect(report.nativeAlphaHooksBefore).toEqual({mask:true,blend:false});expect(report.nativeAlphaHooksAfter).toEqual(report.nativeAlphaHooksBefore);
 for(const cleanup of report.cleanup){expect(cleanup.closed).toBe(true);expect(cleanup.geometryDisposals).toBe(cleanup.expectedGeometryDisposals);expect(cleanup.materialDisposals).toBe(cleanup.expectedMaterialDisposals);expect(cleanup.targetDisposals).toBe(1);expect(cleanup.geometriesAfterClose).toBe(0);expect(cleanup.texturesAfterClose,JSON.stringify({steps:cleanup.textureReleaseSteps,identity:cleanup.textureIdentity})).toBe(0);expect(cleanup.textureIdentity.created).toBeGreaterThan(0);expect(cleanup.textureIdentity.deleted).toBe(cleanup.textureIdentity.created);expect(cleanup.textureReleaseSteps.at(-1)?.remaining).toEqual([]);expect(cleanup.textureIdentity.dfg).toEqual({name:'DFG_LUT',width:16,height:16,isDataTexture:true});}
 expect(errors).toEqual([]);
});
test('real shader submissions stop across actual task authority revocation and owned teardown before GPU/geometry disposal',async({page},testInfo)=>{
 const errors=await fixturePage(page);
 const report=await page.evaluate(async()=>{const source='/tests/graphics-warmup-fixture.ts';return (await import(/* @vite-ignore */source)).auditGraphicsWarmupCancellation();}) as Awaited<ReturnType<typeof auditGraphicsWarmupCancellation>>;
 await testInfo.attach('graphics-warmup-cancellation',{contentType:'application/json',body:JSON.stringify({schemaVersion:1,browser:page.context().browser()?.version(),project:testInfo.project.name,report,errors})});
 expect(report.webgl2).toBe(true);expect(report.failureName).toBe('AbortError');expect(report.submitted).toBe(1);expect(report.settledSubmitted).toBe(1);expect(report.finalCalls).toBe(0);expect(report.yields).toBe(1);expect(report.closed).toBe(1);expect(report.publishedReady).toBe(0);expect(report.warmInputs).toBe(true);expect(report.shadersReady).toBe(false);expect(report.cleanup.closed).toBe(true);expect(report.cleanup.geometryDisposals).toBe(report.cleanup.expectedGeometryDisposals);expect(report.cleanup.materialDisposals).toBe(report.cleanup.expectedMaterialDisposals);expect(report.cleanup.targetDisposals).toBe(1);expect(report.cleanup.geometriesAfterClose).toBe(0);expect(report.cleanup.texturesAfterClose).toBe(0);expect(errors).toEqual([]);
});
