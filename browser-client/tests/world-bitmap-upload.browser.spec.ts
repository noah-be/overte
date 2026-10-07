// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
test('already decoded bitmap variants preserve exact HTML texture pixels and owned sampler teardown',async({page},testInfo)=>{
 await page.goto('/');const report=await page.evaluate(async()=>{const path='/tests/fixtures/world-bitmap-upload.ts';const fixture=await import(/* @vite-ignore */path);return fixture.runBitmapUploadProof();});
 await testInfo.attach('bitmap-upload-parity',{body:JSON.stringify(report,null,2),contentType:'application/json'});
 expect(report.completed).toBe(true);expect(report.checks).toHaveLength(12);for(const check of report.checks)expect(check.maximumChannelError).toBe(0);
 expect(report.checks.filter((check:{prepared:boolean})=>check.prepared)).toHaveLength(6);expect(report.checks.filter((check:{prepared:boolean})=>!check.prepared)).toHaveLength(6);
 for(const check of report.checks)expect(check.prepared).toBe(!check.premultiplyAlpha);
 expect(report.ownership.leases).toBe(0);expect(report.ownership.bytes).toBe(0);expect(report.ownership.active).toBe(0);expect(report.ownership.closeFailures).toBe(0);expect(report.textureCountAfterClose).toBe(0);expect(report.geometryCountAfterClose).toBe(0);
});
