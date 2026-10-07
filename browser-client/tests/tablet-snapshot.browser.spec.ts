// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual local WebGL component pixels; not domain compatibility evidence.
import {test,expect} from '@playwright/test';
import {inflateSync} from 'node:zlib';
// Decode actual compositor PNG bytes in Node, avoiding a second browser/GPU round trip.
function screenshotPixel(png:Buffer,x:number,y:number):number[]{
    expect(png.subarray(0,8)).toEqual(Buffer.from([137,80,78,71,13,10,26,10]));
    let width=0,height=0,channels=0;const parts:Buffer[]=[];
    for(let offset=8;offset<png.length;){const length=png.readUInt32BE(offset),kind=png.toString('ascii',offset+4,offset+8),data=png.subarray(offset+8,offset+8+length);
        if(kind==='IHDR'){width=data.readUInt32BE(0);height=data.readUInt32BE(4);expect(data[8]).toBe(8);channels=data[9]===6?4:data[9]===2?3:0;expect(channels).toBeGreaterThan(0);expect(data[12]).toBe(0);}
        else if(kind==='IDAT')parts.push(data);offset+=length+12;
    }
    const stride=width*channels,raw=inflateSync(Buffer.concat(parts),{maxOutputLength:(stride+1)*height});
    expect(raw.length).toBe((stride+1)*height);let previous=Buffer.alloc(stride);
    for(let row=0;row<=Math.floor(y);row++){const filter=raw[row*(stride+1)],current=Buffer.from(raw.subarray(row*(stride+1)+1,(row+1)*(stride+1)));expect(filter).toBeLessThanOrEqual(4);
        for(let i=0;i<stride;i++){const left=i>=channels?current[i-channels]:0,up=previous[i],corner=i>=channels?previous[i-channels]:0;let prediction=0;
            if(filter===1)prediction=left;else if(filter===2)prediction=up;else if(filter===3)prediction=Math.floor((left+up)/2);else if(filter===4){const value=left+up-corner,a=Math.abs(value-left),b=Math.abs(value-up),c=Math.abs(value-corner);prediction=a<=b&&a<=c?left:b<=c?up:corner;}
            current[i]=(current[i]+prediction)&255;
        }previous=current;
    }
    return Array.from(previous.subarray(Math.floor(x)*channels,Math.floor(x)*channels+3));
}
// Parse actual GIF blocks rather than scanning compressed data for delay bytes.
function animatedDuration(gif:Buffer):number{
    let cursor=13+((gif[10]&128)?3*(1<<((gif[10]&7)+1)):0),duration=0;
    const blocks=()=>{for(let size;(size=gif[cursor++])!==0;)cursor+=size;};
    while(cursor<gif.length){const kind=gif[cursor++];if(kind===0x3b)return duration;
        if(kind===0x21){const label=gif[cursor++];if(label===0xf9){expect(gif[cursor++]).toBe(4);duration+=gif.readUInt16LE(cursor+1)*10;cursor+=4;expect(gif[cursor++]).toBe(0);}else blocks();}
        else{expect(kind).toBe(0x2c);const packed=gif[cursor+8];cursor+=9;if(packed&128)cursor+=3*(1<<((packed&7)+1));cursor++;blocks();}
    }throw Error('Actual GIF trailer is missing');
}
test('Snap exports still and genuinely animated local WebGL while the native tablet covers the world',async({page})=>{
    const uploads=new Map<string,Buffer>();
    await page.route('**/snapshot-files?name=*',async route=>{uploads.set(new URL(route.request().url()).searchParams.get('name')!,route.request().postDataBuffer()!);await route.fulfill({status:200,contentType:'application/json',body:'{}'});});
    await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));await page.goto('/');
    const covered=await page.evaluate(async()=>{
        const worldPath='/src/world.ts',tabletPath='/src/tablet.ts';const {BrowserWorld}=await import(worldPath),{BrowserTablet}=await import(tabletPath);
        document.body.innerHTML='<div id="scene" style="position:relative;width:800px;height:600px"></div>';
        const holder=document.getElementById('scene')!,proof={sent:[] as any[],captures:0,world:undefined as any,tablet:undefined as any};
        const world=new BrowserWorld(holder,{resolveAsset:(url:string)=>url,onPose:()=>{},onInteract:()=>{},onStatus:()=>{}});proof.world=world;world.setSpawn({x:0,y:.85,z:0});world.setEnabled(true);
        const scene=(green:boolean)=>[{id:'floor',type:'Box',position:{x:0,y:-.5,z:0},dimensions:{x:30,y:1,z:30}},{id:'wall',type:'Box',position:{x:0,y:1.5,z:-3},dimensions:{x:5,y:3,z:.2},color:green?{red:20,green:240,blue:20}:{red:240,green:20,blue:20}}];world.setEntities(scene(false));
        const tablet=new BrowserTablet(holder,{send:(value:unknown)=>proof.sent.push(value),onStatus:()=>{},onVisibility:(visible:boolean)=>world.setInputEnabled(!visible),fileURL:(name:string)=>`/snapshot-files?name=${encodeURIComponent(name)}`,captureScene:async()=>{
            proof.captures++;const green=proof.captures>2;world.setEntities(scene(green));const deadline=performance.now()+10000;
            // Entity population and shader preparation begin asynchronously. Verify the
            // actual captured wall pixels, including the first microtask, before encoding.
            while(true){
                await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
                const blob=await world.captureScene(),image=await createImageBitmap(blob),canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
                const context=canvas.getContext('2d')!;context.drawImage(image,0,0);const pixel=context.getImageData(canvas.width/2,canvas.height/2,1,1).data;image.close();
                if(green?pixel[1]>pixel[0]*2:pixel[0]>pixel[1]*2)return blob;
                if(performance.now()>deadline)throw Error(`Actual ${green?'green':'red'} wall pixels did not become ready`);
            }
        }});proof.tablet=tablet;
        tablet.setConnected(true);tablet.open();tablet.receive({type:'tablet',kind:'state',revision:1,visible:true,screen:'Snap',loading:false});
        const qt=document.createElement('canvas');qt.width=480;qt.height=706;qt.getContext('2d')!.fillStyle='#0000ff';qt.getContext('2d')!.fillRect(0,0,480,706);
        tablet.receive({type:'tablet',kind:'frame',navigationSequence:1,revision:1,sequence:1,width:480,height:706,mime:'image/png',surface:'tablet',data:qt.toDataURL().split(',')[1]});(window as any).__snapshotProof=proof;
        const deadline=performance.now()+10000;while(world.getPerformance().compilingGraphics){if(performance.now()>deadline)throw Error('Actual scene shaders did not finish compiling');await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));}
        await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
        const blob=await world.captureScene(),image=await createImageBitmap(blob),canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;canvas.getContext('2d')!.drawImage(image,0,0);
        const pixel=Array.from(canvas.getContext('2d')!.getImageData(image.width/2,image.height/2,1,1).data);image.close();return pixel;
    });
    expect(covered[0]).toBeGreaterThan(covered[1]*2);expect(covered[0]).toBeGreaterThan(covered[2]*2);await expect(page.getByLabel('Native tablet apps and dialogs')).toBeVisible();
    await page.evaluate(()=>(window as any).__snapshotProof.tablet.receive({type:'tablet',kind:'snapshot',revision:1,requestId:1,animated:false,aspectRatio:1.91}));
    await expect.poll(()=>page.evaluate(()=>(window as any).__snapshotProof.sent.find((value:any)=>value.action==='snapshotResult'&&value.requestId===1))).toMatchObject({requestId:1});
    const stillMessage=await page.evaluate(()=>(window as any).__snapshotProof.sent.find((value:any)=>value.requestId===1));expect(stillMessage.error).toBeUndefined();const stillBytes=uploads.get(stillMessage.stillName)!;expect(stillBytes.subarray(0,8)).toEqual(Buffer.from([137,80,78,71,13,10,26,10]));
    const still=await page.evaluate(async(base64:string)=>{const image=await createImageBitmap(await(await fetch(`data:image/png;base64,${base64}`)).blob());const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;canvas.getContext('2d')!.drawImage(image,0,0);const pixel=Array.from(canvas.getContext('2d')!.getImageData(image.width/2,image.height/2,1,1).data);image.close();return{width:canvas.width,height:canvas.height,pixel};},stillBytes.toString('base64'));
    expect(still.width/still.height).toBeCloseTo(1.91,2);expect(still.pixel[0]).toBeGreaterThan(still.pixel[1]*2);
    await page.evaluate(()=>(window as any).__snapshotProof.tablet.receive({type:'tablet',kind:'snapshot',revision:1,requestId:2,animated:true,aspectRatio:1.91}));
    await expect.poll(()=>page.evaluate(()=>(window as any).__snapshotProof.sent.find((value:any)=>value.action==='snapshotResult'&&value.requestId===2)),{timeout:20000}).toMatchObject({requestId:2});
    const animated=await page.evaluate(()=>(window as any).__snapshotProof.sent.find((value:any)=>value.requestId===2));expect(animated.error).toBeUndefined();const gif=uploads.get(animated.gifName)!;expect(gif.subarray(0,6).toString()).toBe('GIF89a');expect(gif.at(-1)).toBe(0x3b);expect(animatedDuration(gif)).toBe(5000);
    // Play/decode the GIF, proving exported frames actually change over time.
    await page.evaluate(async(base64:string)=>{const image=document.createElement('img');image.id='gif-playback';Object.assign(image.style,{position:'fixed',top:'0',left:'0',zIndex:'100',maxWidth:'100vw'});image.src=`data:image/gif;base64,${base64}`;document.body.append(image);await image.decode();},gif.toString('base64'));
    const pixel=()=>page.evaluate(()=>{const image=document.getElementById('gif-playback') as HTMLImageElement,canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;canvas.getContext('2d')!.drawImage(image,0,0);return Array.from(canvas.getContext('2d')!.getImageData(canvas.width/2,canvas.height/2,1,1).data);});
    const initial=await pixel();expect(initial[0]).toBeGreaterThan(initial[1]*2);
    // Canvas drawImage uses an animated image's default frame by specification.
    // Screenshot the actual displayed <img> to verify its compositor animation.
    const playbackBounds=await page.locator('#gif-playback').boundingBox();expect(playbackBounds).not.toBeNull();
    await expect.poll(async()=>{const pixel=screenshotPixel(await page.screenshot(),playbackBounds!.x+playbackBounds!.width/2,playbackBounds!.y+playbackBounds!.height/2);return pixel[1]>pixel[0]*2;},{timeout:5000}).toBe(true);
    await page.evaluate(()=>(window as any).__snapshotProof.tablet.receive({type:'tablet',kind:'state',revision:1,visible:true,screen:'Snap',loading:false}));await page.locator('#gif-playback').evaluate(element=>element.remove());const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download animated snapshot'}).click();expect((await download).suggestedFilename()).toBe(animated.gifName);
    await page.evaluate(()=>{(window as any).__snapshotProof.tablet.dispose();(window as any).__snapshotProof.world.dispose();});
});
