// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
const green=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGNk+M/AwMDAxMDAwMDAAAAMHgEDBINhkwAAAABJRU5ErkJggg==','base64');
const red=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==','base64');
for(const mode of ['partial','all'] as const)test(`Authorized ${mode} FST admission avoids unreachable network images and preserves exact rendered pixels`,async({page})=>{
 const errors:string[]=[],requests:{baseline:string[];candidate:string[]}={baseline:[],candidate:[]};page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
 await page.route('**/fst-admission-assets/**',async route=>{
  const path=new URL(route.request().url()).pathname,which=path.includes('/candidate/')?'candidate':'baseline',file=path.split('/').at(-1)!;requests[which].push(file);
  if(!['replacement.png','shared.png','unused-a.png','only-b.png'].includes(file)){await route.fulfill({status:404,body:'Unexpected dependency'});return;}
  await route.fulfill({headers:{'cache-control':'no-store'},contentType:'image/png',body:file==='replacement.png'?green:red});
 });
 await page.goto('/');
 const result=await page.evaluate(async mode=>{const path='/tests/fst-texture-admission-fixture.ts';const {auditFstTextureAdmission}=await import(/* @vite-ignore */path);return auditFstTextureAdmission(mode);},mode);
 expect(result.webGL2).toBe(true);expect(result.inputUnchanged).toBe(true);expect(result.geometryEqual).toBe(true);expect(result.differentRGBAComponents).toBe(0);expect(result.dependencyErrors).toEqual([]);expect(errors).toEqual([]);
 expect(result.before).toEqual({calls:2,triangles:2});expect(result.after).toEqual(result.before);expect(result.left).toEqual([0,255,0,255]);expect(result.background).toEqual([0,0,0,255]);
 expect(requests.baseline.sort()).toEqual(['only-b.png','replacement.png','shared.png','unused-a.png']);expect(requests.candidate).not.toContain('unused-a.png');
 if(mode==='all'){
  expect(requests.candidate).toEqual(['replacement.png']);expect(result.admission).toEqual({removedTextures:3,removedVideos:3,retainedTextures:0});expect(result.right).toEqual([0,255,0,255]);expect(result.sourceStats[1].uniqueImages).toBe(1);
 }else{
  expect(requests.candidate.sort()).toEqual(['only-b.png','replacement.png','shared.png']);expect(result.admission).toEqual({removedTextures:1,removedVideos:1,retainedTextures:2});expect(result.right[0]).toBeGreaterThan(50);expect(result.right[0]).toBeGreaterThan(result.right[1]*2);expect(result.sourceStats[1].uniqueImages).toBe(3);
 }
 expect(result.sourceStats[0].uniqueImages).toBe(4);expect(result.sourceStats.every((stats:any)=>stats.active===0&&stats.pending===0&&stats.failed===0)).toBe(true);expect(await page.locator('canvas').count()).toBe(0);
});
