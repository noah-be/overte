// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real owned worker task delivery/cancellation; no WebGL/domain parity claim.
import {expect,test} from '@playwright/test';
test('Owned worker continuations yield to incoming cancellation between bounded tiles and close their ports',async({page})=>{
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
  await page.goto('/');
  const result=await page.evaluate(async()=>{
    const source=`import {WorkerTaskYield} from '${location.origin}/src/worker-task-yield.ts';
      let active;
      self.onmessage=async({data})=>{
        if(data.cancel){active?.abort();return;}
        const controller=new AbortController();active=controller;let closes=0,tiles=0;
        const owned=new WorkerTaskYield({signal:controller.signal,channelFactory:()=>{const channel=new MessageChannel();for(const port of[channel.port1,channel.port2]){const close=port.close.bind(port);port.close=()=>{closes++;close();};}return channel;}});
        const bytes=new Uint8Array(256*256*4).fill(255);let opaque=0;
        try{for(;tiles<data.total;tiles++){for(let at=3;at<bytes.length;at+=4)if(bytes[at]===255)opaque++;if(data.cancelAt!==undefined&&tiles===data.cancelAt)self.postMessage({progress:true});await owned.yield();}owned.close();self.postMessage({completed:true,tiles,opaque,closes});}
        catch(error){owned.close();self.postMessage({cancelled:error.name==='AbortError',tiles,closes});}
        finally{if(active===controller)active=undefined;}
      };`;
    const url=URL.createObjectURL(new Blob([source],{type:'text/javascript'}));const worker=new Worker(url,{type:'module'});URL.revokeObjectURL(url);
    const run=(config:{total:number;cancelAt?:number})=>new Promise<any>((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('Owned worker continuation test exceeded10 seconds')),10000);
      worker.onerror=event=>{clearTimeout(timer);reject(Error(event.message));};worker.onmessage=event=>{if(event.data.progress)worker.postMessage({cancel:true});else{clearTimeout(timer);resolve(event.data);}};worker.postMessage(config);
    });
    try{return{cancelled:await run({total:1024,cancelAt:8}),completed:await run({total:16})};}finally{worker.terminate();}
  });
  expect(result.cancelled.cancelled).toBe(true);expect(result.cancelled.tiles).toBeGreaterThanOrEqual(8);expect(result.cancelled.tiles).toBeLessThan(1024);expect(result.cancelled.closes).toBe(2);
  expect(result.completed).toEqual({completed:true,tiles:16,opaque:16*256*256,closes:2});
});
