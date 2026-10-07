// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {expect,type Page} from '@playwright/test';
/** Genuine no-delegation denial, including a real trusted API call and painted input. */
export async function runEmbeddedFullscreenDenial(page:Page){
    await page.goto('/');
    const parent=new URL('/fullscreen-owned-parent.html',page.url()),child=new URL('/fullscreen-owned-child.html',parent);
    if(parent.protocol!=='http:'||!['127.0.0.1','localhost'].includes(parent.hostname)||!parent.port||parent.username||parent.password)throw Error('Owned loopback source required');
    child.hostname=parent.hostname==='127.0.0.1'?'localhost':'127.0.0.1';expect(child.origin).not.toBe(parent.origin);expect(child.port).toBe(parent.port);
    let parentResponses=0,childResponses=0;
    await page.route(parent.href,route=>{parentResponses++;return route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><html><body style="margin:0"><iframe id="owned-fullscreen-frame" src="'+child.href+'" style="position:fixed;inset:0;width:100%;height:100%;border:0"></iframe></body></html>'});});
    await page.route(child.href,route=>{childResponses++;return route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><html><body></body></html>'});});
    let frame:ReturnType<Page['frames']>[number]|undefined;
    try{
        await page.goto(parent.href);frame=page.frames().find(f=>f.url()===child.href);expect(frame).toBeDefined();if(!frame)throw Error('Owned cross-origin Frame required');
        expect(parentResponses).toBe(1);expect(childResponses).toBe(1);
        await frame.evaluate(async()=>{
        const path='/src/tablet.ts';const {BrowserTablet}=await import(path);
        const host=document.createElement('div');host.id='fullscreen-tablet-owner';Object.assign(host.style,{position:'fixed',inset:'0',zIndex:'100'});document.body.append(host);
        const sent:Record<string,unknown>[]=[],statuses:string[]=[];
        const tablet=new BrowserTablet(host,{send:(value:Record<string,unknown>)=>sent.push(value),onStatus:(value:string)=>statuses.push(value),onVisibility(){}});
        function join(){tablet.setConnected(true);tablet.open();tablet.receive({type:'tablet',kind:'state',revision:1,visible:true,loading:false,screen:'Authored fullscreen fixture'});
            const image=document.createElement('canvas');image.width=480;image.height=706;const ctx=image.getContext('2d')!;ctx.fillStyle='#285064';ctx.fillRect(0,0,480,706);
            const sequence=Number([...sent].reverse().find(value=>value.action==='open')?.sequence);
            tablet.receive({type:'tablet',kind:'frame',navigationSequence:sequence,revision:1,sequence:1,width:480,height:706,mime:'image/png',surface:'tablet',data:image.toDataURL().split(',')[1]});}
        join();(window as any).__fullscreenTablet={tablet,host,sent,statuses,join};
        });
        await expect.poll(()=>frame!.evaluate(()=>(window as any).__fullscreenTablet.sent.some((value:any)=>value.action==='frameAck'&&value.displayed===true))).toBe(true);
        expect(await page.evaluate(()=>{const e=document.getElementById('owned-fullscreen-frame')!;return {noDelegation:!e.hasAttribute('allowfullscreen')&&!e.hasAttribute('allow'),none:document.fullscreenElement===null};})).toEqual({noDelegation:true,none:true});
        expect(await frame.evaluate(()=>({enabled:document.fullscreenEnabled,visible:document.visibilityState==='visible',connected:(window as any).__fullscreenTablet.host.isConnected,none:document.fullscreenElement===null}))).toEqual({enabled:false,visible:true,connected:true,none:true});
        await expect(frame.getByRole('button',{name:'Fullscreen',exact:true})).toBeDisabled();await expect(frame.getByText('Fullscreen is unavailable in this browser or embedding.',{exact:true})).toBeVisible();
        await frame.evaluate(()=>{(window as any).__ownedEmbeddedPointer=[];for(const type of ['pointerdown','pointerup'])document.addEventListener(type,event=>{const e=event as PointerEvent;if(e.target!==document.querySelector('#fullscreen-tablet-owner canvas'))return;const events=(window as any).__ownedEmbeddedPointer;if(events.length>=8)throw Error('Authored pointer bound');events.push({type:e.type,trusted:e.isTrusted,button:e.button});},{capture:true});});
        const canvas=frame.getByLabel('Native tablet apps and dialogs'),bounds=await canvas.boundingBox();expect(bounds).not.toBeNull();if(!bounds)throw Error('Painted owned canvas required');
        expect(await canvas.evaluate((e:HTMLCanvasElement)=>[...e.getContext('2d')!.getImageData(40,40,1,1).data])).toEqual([40,80,100,255]);expect(bounds.width/bounds.height).toBeCloseTo(480/706,3);
        await canvas.click();
        expect(await frame.evaluate(()=>(window as any).__ownedEmbeddedPointer)).toEqual([{type:'pointerdown',trusted:true,button:0},{type:'pointerup',trusted:true,button:0}]);
        const inputs=await frame.evaluate(()=>(window as any).__fullscreenTablet.sent.filter((v:any)=>v.action==='input'));
        for(const event of ['press','release']){const input=inputs.find((v:any)=>v.event===event);expect(input).toMatchObject({revision:1,frameSequence:1,button:0});expect(Math.abs(Number(input.x)-.5)*bounds.width).toBeLessThanOrEqual(1);expect(Math.abs(Number(input.y)-.5)*bounds.height).toBeLessThanOrEqual(1);}
        await frame.evaluate(()=>{const button=document.createElement('button');button.id='owned-fullscreen-api-probe';button.textContent='Probe actual embedded fullscreen permission';Object.assign(button.style,{position:'fixed',right:'4px',top:'4px',zIndex:'1000'});document.body.append(button);(window as any).__ownedFullscreenProbe=null;let calls=0;button.addEventListener('click',event=>{const host=(window as any).__fullscreenTablet.host,current={trusted:event.isTrusted,calls:++calls,visible:document.visibilityState==='visible',connected:host.isConnected,enabled:document.fullscreenEnabled};let operation;try{operation=host.requestFullscreen();}catch(error){(window as any).__ownedFullscreenProbe={...current,rejected:true,name:(error as Error).name,none:document.fullscreenElement===null};return;}void Promise.resolve(operation).then(()=>{(window as any).__ownedFullscreenProbe={...current,rejected:false,name:null,none:document.fullscreenElement===null};},error=>{(window as any).__ownedFullscreenProbe={...current,rejected:true,name:error?.name,none:document.fullscreenElement===null};});});});
        await frame.getByRole('button',{name:'Probe actual embedded fullscreen permission',exact:true}).click();
        await expect.poll(()=>frame!.evaluate(()=>(window as any).__ownedFullscreenProbe)).toEqual({trusted:true,calls:1,visible:true,connected:true,enabled:false,rejected:true,name:'TypeError',none:true});
        expect(await frame.evaluate(()=>document.fullscreenElement===null)).toBe(true);expect(await page.evaluate(()=>document.fullscreenElement===null)).toBe(true);
    }finally{
        try{if(frame&&!frame.isDetached()){await frame.evaluate(()=>(window as any).__fullscreenTablet?.tablet.dispose());expect(await frame.evaluate(()=>document.fullscreenElement===null)).toBe(true);}expect(await page.evaluate(()=>document.fullscreenElement===null)).toBe(true);}
        finally{await page.unroute(parent.href);await page.unroute(child.href);}
    }
}
