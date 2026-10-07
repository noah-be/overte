// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('native RGBA masking removes transparent black backgrounds while preserving actual opaque black pixels',async({page})=>{
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));await page.goto('/');
  const r=await page.evaluate(async()=>{const modulePath='/tests/texture-alpha-fixture.ts';return(await import(/* @vite-ignore */modulePath)).auditAlphaPixels();});
  expect(r.alpha).toBe('mask');expect(r.shared).toEqual(['mask','mask']);expect(r.before.background).toBe(0);expect(r.after.background).toBe(196608);
  expect(r.after.black).toBe(4096);expect(r.after.green).toBe(61440);
});
test('cancelling one alpha reader preserves a simultaneous reader and all opaque-black alpha bytes',async({page})=>{
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));await page.goto('/');
  const r=await page.evaluate(async()=>{const modulePath='/tests/texture-alpha-fixture.ts';return(await import(/* @vite-ignore */modulePath)).auditAlphaCancellation();});
  expect(r).toEqual({cancelled:true,retained:'opaque',retry:'mask'});
});
test('a stalled bitmap operation reaches the bounded deadline and releases subsequent real-image work',async({page})=>{
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));await page.goto('/');await page.clock.install();
  await page.evaluate(async()=>{
    const modulePath='/src/texture-alpha.ts';const {nativeTextureAlpha}=await import(/* @vite-ignore */modulePath);
    const state=window as unknown as {restoreBitmap?:()=>void;pendingAlpha?:Promise<string>};const original=window.createImageBitmap;
    window.createImageBitmap=(()=>new Promise(()=>{})) as typeof original;state.restoreBitmap=()=>{window.createImageBitmap=original;};
    const source=document.createElement('canvas');source.width=source.height=16;state.pendingAlpha=nativeTextureAlpha({image:source}).then(()=> 'Unexpected success',(error:Error)=>error.message);
  });
  await page.clock.fastForward(30001);
  const r=await page.evaluate(async()=>{
    const state=window as unknown as {restoreBitmap:()=>void;pendingAlpha:Promise<string>};state.restoreBitmap();const error=await state.pendingAlpha;
    const modulePath='/src/texture-alpha.ts';const {nativeTextureAlpha}=await import(/* @vite-ignore */modulePath);const source=document.createElement('canvas');source.width=source.height=16;
    return {error,next:await nativeTextureAlpha({image:source})};
  });
  expect(r.error).toBe('Texture alpha inspection exceeded 30 seconds');expect(r.next).toBe('mask');
});
