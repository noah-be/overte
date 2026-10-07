// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
import {replacementMaterialFbx,replacementRGBA} from './fixtures/replacement-material-fbx';
const png=Buffer.from(replacementRGBA);
for(const variant of ['opaque','rgb','skin','blend','mask','foreign']as const)test(`Actual FBX/World ordered replacement clone reuse preserves strict ${variant} pixels and teardown`,async({page},testInfo)=>{
 const errors:string[]=[],requests:{baseline:string[];candidate:string[]}={baseline:[],candidate:[]};page.on('pageerror',error=>errors.push(error.message));
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body style="margin:0"></body>'}));
 await page.route('**/replacement-clone-assets/**',async route=>{const url=new URL(route.request().url()),which=url.pathname.includes('/baseline/')?'baseline':'candidate',file=url.pathname.split('/').at(-1)!;requests[which].push(file);const headers={'cache-control':'no-store'};
 if(file==='model.fbx')await route.fulfill({headers,body:Buffer.from(replacementMaterialFbx({withoutOriginalTextures:true,vertexColors:variant==='rgb',skin:variant==='skin'}))});
 else if(file==='model.fst')await route.fulfill({headers,body:'filename = model.fbx\nmaterialMap = [{"all":"material.json#Replacement"}]'});
 else if(file==='material.json')await route.fulfill({headers,contentType:'application/json',body:JSON.stringify({materials:{name:'Replacement',model:'hifi_pbr',unlit:variant!=='opaque',albedoMap:'color.png',opacity:variant==='blend'?.6:1,opacityMapMode:variant==='mask'?'OPACITY_MAP_MASK':variant==='blend'?'OPACITY_MAP_BLEND':'OPACITY_MAP_OPAQUE'}})});
 else if(file==='color.png')await route.fulfill({headers,contentType:'image/png',body:png});else await route.fulfill({status:404,body:'Unexpected owned fixture dependency'});});
 await page.goto('/');const reports=[];for(const enabled of [false,true])reports.push(await page.evaluate(async({enabled,variant})=>{const path='/tests/replacement-material-clones-fixture.ts';const {auditReplacementMaterialClones}=await import(/* @vite-ignore */path);return auditReplacementMaterialClones(`/replacement-clone-assets/${enabled?'candidate':'baseline'}/model.fst`,enabled,variant);},{enabled,variant}));
 await testInfo.attach('replacement-clone-strict-source-proof',{contentType:'application/json',body:JSON.stringify({browser:page.context().browser()?.version(),project:testInfo.project.name,reports,requests,errors})});
 expect(errors).toEqual([]);expect(reports.map(report=>report.warnings)).toEqual([[],[]]);expect(reports.every(report=>report.webgl2&&report.cleanup)).toBe(true);expect(reports[1].pixels).toEqual(reports[0].pixels);expect(reports[0].pixels).toHaveLength(5);expect(reports[0].pixels.every((record:{visibleChannels:number})=>record.visibleChannels>0)).toBe(true);
 for(const report of reports)for(const record of report.pixels){expect(record.surfaceColors).toHaveLength(2);for(const surface of record.surfaceColors)expect(surface).not.toEqual(record.background);}
 expect(requests.candidate).toEqual(requests.baseline);expect(reports[0].counter).toEqual({enabled:false,applications:0,created:0,reused:0,refused:0});expect(reports[1].counter.enabled).toBe(true);expect(reports[1].counter.reused).toBeGreaterThan(0);if(variant==='foreign')expect(reports[1].counter.refused).toBeGreaterThan(0);else expect(reports[1].counter.refused).toBe(0);
 // True ordered index-0 replacement remains distinct from the untouched slot.
 expect(reports[1].initial.unique).toBeLessThanOrEqual(reports[0].initial.unique);expect(reports[1].initial.slots).toBeGreaterThan(0);
});
