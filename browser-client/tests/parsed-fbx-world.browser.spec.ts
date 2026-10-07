// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
import {replacementMaterialFbx,replacementRGBA,admissionPNG} from './fixtures/parsed-template-fbx';
for(const variant of ['original','rgb','skin','mask']as const)test('actual World FBX template reuse preserves native/FST '+variant+' pixels, geometry ownership and cleanup',async({page},testInfo)=>{
 const errors:string[]=[],requests:{baseline:string[];candidate:string[]}={baseline:[],candidate:[]};page.on('pageerror',error=>errors.push(error.message));
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body style="margin:0"></body>'}));
 await page.route('**/parsed-world-assets/**',async route=>{const url=new URL(route.request().url()),which=url.pathname.includes('/baseline/')?'baseline':'candidate',file=url.pathname.split('/').at(-1)!;requests[which].push(file);const headers={'cache-control':'no-store'};
  if(file==='model.fbx')await route.fulfill({headers,body:Buffer.from(replacementMaterialFbx({withoutOriginalTextures:variant!=='original',vertexColors:variant==='rgb',skin:variant==='skin'}))});
  else if(file==='model.fst')await route.fulfill({headers,body:'filename = model.fbx\nmaterialMap = [{"all":"material.json#Mapped"}]'});
  else if(file==='material.json')await route.fulfill({headers,contentType:'application/json',body:JSON.stringify({materials:{name:'Mapped',model:'hifi_pbr',unlit:variant!=='skin',albedoMap:'color.png',opacityMapMode:variant==='mask'?'OPACITY_MAP_MASK':'OPACITY_MAP_OPAQUE'}})});
  else if(file==='color.png')await route.fulfill({headers,contentType:'image/png',body:Buffer.from(replacementRGBA)});
  else if(file.endsWith('.png'))await route.fulfill({headers,contentType:'image/png',body:Buffer.from(admissionPNG)});
  else await route.fulfill({status:404,body:'Unexpected owned dependency'});
 });
 await page.goto('/');const reports=[];for(const enabled of [false,true])reports.push(await page.evaluate(async({enabled,variant})=>{const path='/tests/parsed-fbx-world-fixture.ts';const {auditParsedFbxWorld}=await import(/* @vite-ignore */path);return auditParsedFbxWorld(`/parsed-world-assets/${enabled?'candidate':'baseline'}/model.${variant==='original'?'fbx':'fst'}`,enabled,variant);},{enabled,variant}));
 await testInfo.attach('actual-world-template-pixels',{contentType:'application/json',body:JSON.stringify({project:testInfo.project.name,reports,requests,errors})});
 expect(errors).toEqual([]);expect(reports.map(report=>report.warnings)).toEqual([[],[]]);expect(reports.every(report=>report.webgl2&&report.cleanup)).toBe(true);expect(reports[1].pixels).toEqual(reports[0].pixels);expect(reports[0].pixels).toHaveLength(5);
 for(const report of reports)for(const record of report.pixels){expect(record.visibleChannels).toBeGreaterThan(0);expect(record.surfaceColors).toHaveLength(4);for(const color of record.surfaceColors)expect(color).not.toEqual(record.background);}
 expect(requests.candidate).toEqual(requests.baseline);expect(reports[0].counter).toEqual({enabled:false,fallbacks:0,cache:null});expect(reports[1].counter.enabled).toBe(true);expect(reports[1].counter.fallbacks).toBe(0);expect(reports[1].counter.cache?.producers).toBe(1);expect((reports[1].counter.cache?.hits??0)+(reports[1].counter.cache?.joined??0)).toBeGreaterThan(0);
 if(variant==='skin')for(const report of reports){expect(report.initial.skins).toBeGreaterThan(0);expect(report.privateBones.allocated).toBeGreaterThan(0);expect(report.privateBones.disposed).toBe(report.privateBones.allocated);}
});
