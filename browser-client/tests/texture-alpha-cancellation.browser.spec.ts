// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Drive the actual worker module, including the per-image cancellation owner.
import {expect,test} from '@playwright/test';
test('Actual alpha worker cancels its current tile continuation, closes ports, and accepts a fresh exact-alpha job',async({page})=>{
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
  await page.goto('/');
  const result=await page.evaluate(async()=>{
    // Instrument only private owned MessagePort closure, then import the actual
    // production worker byte scanner. No replacement implementation is used.
    const source=`const NativeChannel=MessageChannel;let portsClosed=0;globalThis.MessageChannel=class extends NativeChannel{constructor(){super();for(const port of[this.port1,this.port2]){const close=port.close.bind(port);port.close=()=>{portsClosed++;close();};}}};self.addEventListener('message',({data})=>{if(data.inspect)self.postMessage({portsClosed});});await import('${location.origin}/src/texture-alpha-worker.ts');self.postMessage({ready:true});`;
    const url=URL.createObjectURL(new Blob([source],{type:'text/javascript'}));const worker=new Worker(url,{type:'module'});URL.revokeObjectURL(url);
    const next=()=>new Promise<any>((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Actual alpha worker did not respond within10 seconds')),10000);worker.onmessage=event=>{clearTimeout(timer);resolve(event.data);};worker.onerror=event=>{clearTimeout(timer);reject(Error(event.message));};});
    try{
      await next();
      const canvas=new OffscreenCanvas(2048,2048),context=canvas.getContext('2d')!;context.fillStyle='white';context.fillRect(0,0,canvas.width,canvas.height);const first=await createImageBitmap(canvas);
      const cancelled=next();worker.postMessage({id:41,bitmap:first},[first]);worker.postMessage({id:41,cancel:true});const cancellation=await cancelled;
      const closure=next();worker.postMessage({inspect:true});const firstClosure=await closure;
      const tiny=new OffscreenCanvas(3,1),data=new ImageData(new Uint8ClampedArray([255,255,255,255,255,255,255,0,255,255,255,128]),3,1);tiny.getContext('2d')!.putImageData(data,0,0);const second=await createImageBitmap(tiny);
      const completed=next();worker.postMessage({id:42,bitmap:second},[second]);const completion=await completed;
      const finalClosure=next();worker.postMessage({inspect:true});return{cancellation,completion,firstClosure,finalClosure:await finalClosure};
    }finally{worker.terminate();}
  });
  expect(result.cancellation.id).toBe(41);expect(result.cancellation.error).toContain('cancelled');expect(result.cancellation.total).toBeUndefined();
  expect(result.firstClosure.portsClosed).toBe(2);expect(result.completion).toEqual({id:42,total:3,opaque:1,intermediate:1});expect(result.finalClosure.portsClosed).toBe(4);
});
