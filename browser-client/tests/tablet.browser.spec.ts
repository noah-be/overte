// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{
    await page.goto('/');
    await page.evaluate(async()=>{
        const modulePath='/src/tablet.ts';const {BrowserTablet}=await import(modulePath);
        const holder=document.createElement('div');Object.assign(holder.style,{position:'fixed',inset:'0',zIndex:'100'});document.body.append(holder);
        const proof={sent:[] as unknown[],statuses:[] as string[],visible:false,worldKeys:0,tablet:undefined as any};
        window.addEventListener('keydown',()=>proof.worldKeys++);
        proof.tablet=new BrowserTablet(holder,{send:(message:unknown)=>proof.sent.push(message),onStatus:(message:string)=>proof.statuses.push(message),onVisibility:(visible:boolean)=>proof.visible=visible});
        proof.tablet.setConnected(true);proof.tablet.open();
        proof.tablet.receive({type:'tablet',kind:'state',revision:1,visible:true,loading:false,screen:'Home'});
        const image=document.createElement('canvas');image.width=480;image.height=706;const context=image.getContext('2d')!;context.fillStyle='#285064';context.fillRect(0,0,480,706);
        proof.tablet.receive({type:'tablet',kind:'frame',navigationSequence:1,revision:1,sequence:1,width:480,height:706,mime:'image/png',surface:'tablet',data:image.toDataURL().split(',')[1]});
        (window as any).__tabletProof=proof;
    });
    await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.some((item:any)=>item.action==='frameAck'))).toBe(true);
});
test('genuine PNG display forwards normalized native pointer, keyboard and navigation while isolating world keys',async({page})=>{
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    expect(await canvas.evaluate((element:HTMLCanvasElement)=>Array.from(element.getContext('2d')!.getImageData(40,40,1,1).data))).toEqual([40,80,100,255]);
    const bounds=await canvas.boundingBox();expect(bounds).not.toBeNull();
    await page.mouse.click(bounds!.x+bounds!.width/2,bounds!.y+bounds!.height/2);
    await page.keyboard.press('Control+a');await page.keyboard.type('Overte');await page.keyboard.press('Escape');
    const input=await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.action==='input'));
    const press=input.find((item:any)=>item.event==='press');
    expect(press).toMatchObject({button:0,buttons:1,revision:1,frameSequence:1});
    // Native pointer coordinates retain the browser's actual device-pixel rounding.
    expect(Math.abs(press.x-.5)*bounds!.width).toBeLessThanOrEqual(1);
    expect(Math.abs(press.y-.5)*bounds!.height).toBeLessThanOrEqual(1);
    expect(input.find((item:any)=>item.key==='a')).toMatchObject({modifiers:2});
    expect(input.at(-1)).toMatchObject({key:'Escape'});
    expect(await page.evaluate(()=>(window as any).__tabletProof.worldKeys)).toBe(0);
    await page.getByLabel('Native tablet text input').evaluate(element=>element.dispatchEvent(new CompositionEvent('compositionend',{data:'Überte 世界 👋',bubbles:true})));
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.at(-1))).toMatchObject({event:'text',text:'Überte 世界 👋'});
    await page.getByRole('button',{name:'Home',exact:true}).click();
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.at(-1))).toMatchObject({action:'home',revision:1});
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await expect(canvas).toBeHidden();
    expect(await page.evaluate(()=>(window as any).__tabletProof.visible)).toBe(false);
});
test('responsive tablet pixels and input retain their aspect ratio and obsolete session frames are ignored',async({page})=>{
    await page.setViewportSize({width:420,height:540});
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    await expect.poll(async()=>{const box=await canvas.boundingBox();return box?box.width/box.height:0;}).toBeCloseTo(480/706,3);
    await page.evaluate(()=>{
        const proof=(window as any).__tabletProof;proof.tablet.setConnected(false);
        proof.tablet.receive({type:'tablet',kind:'state',revision:1,visible:true,loading:false,screen:'Old session'});
    });
    await expect(canvas).toBeHidden();
    expect(await page.evaluate(()=>(window as any).__tabletProof.visible)).toBe(false);
});
test('pending or failed dialog PNG decode retains input coordinates from the successfully displayed tablet surface',async({page})=>{
    await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.action==='frameAck'))).toMatchObject({frameSequence:1,displayed:true});
    await page.evaluate(()=>{
        const proof=(window as any).__tabletProof,original=window.createImageBitmap.bind(window);let release!:()=>void;
        const gate=new Promise<void>(resolve=>release=resolve);proof.obsoleteBitmap=undefined;proof.releaseBitmap=()=>{window.createImageBitmap=original;release();};
        window.createImageBitmap=(async(...args:Parameters<typeof createImageBitmap>)=>{const image=await (original as any)(...args);await gate;return image;}) as typeof createImageBitmap;
        const image=document.createElement('canvas');image.width=640;image.height=360;const context=image.getContext('2d')!;context.fillStyle='#14aa55';context.fillRect(0,0,640,360);
        proof.tablet.receive({type:'tablet',kind:'frame',navigationSequence:1,revision:1,sequence:2,width:640,height:360,mime:'image/png',surface:'dialogs',data:image.toDataURL().split(',')[1]});
    });
    const canvas=page.getByLabel('Native tablet apps and dialogs');await canvas.click();await page.mouse.wheel(12,24);
    const pending=await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.action==='input'&&['press','wheel'].includes(item.event)));
    expect(pending.at(-1)).toMatchObject({event:'wheel',frameSequence:1});expect(pending.findLast((item:any)=>item.event==='press')).toMatchObject({frameSequence:1});
    expect(await canvas.evaluate((el:HTMLCanvasElement)=>({width:el.width,height:el.height}))).toEqual({width:480,height:706});
    await page.evaluate(()=>(window as any).__tabletProof.releaseBitmap());
    await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.action==='frameAck'))).toMatchObject({frameSequence:2,displayed:true});
    expect(await canvas.evaluate((el:HTMLCanvasElement)=>({width:el.width,height:el.height,pixel:Array.from(el.getContext('2d')!.getImageData(10,10,1,1).data)}))).toEqual({width:640,height:360,pixel:[20,170,85,255]});
    await page.evaluate(()=>(window as any).__tabletProof.tablet.receive({type:'tablet',kind:'frame',navigationSequence:1,revision:1,sequence:3,width:640,height:360,mime:'image/png',surface:'dialogs',data:'AQID'}));
    await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.action==='frameAck'))).toMatchObject({frameSequence:3,displayed:false});
    await canvas.click();expect(await page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.event==='press'))).toMatchObject({frameSequence:2});
    await page.evaluate(()=>(window as any).__tabletProof.tablet.receive({type:'tablet',kind:'state',revision:2,visible:true,loading:true,screen:'Home'}));
    const before=await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.action==='input').length);
    await canvas.click();await page.keyboard.press('a');await page.mouse.wheel(1,2);
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.action==='input').length)).toBe(before);
});
test('superseded real bitmap decode acknowledges unseen pixels without replacing the latest canvas or leaking its bitmap',async({page})=>{
    await page.evaluate(()=>{
        const proof=(window as any).__tabletProof,original=window.createImageBitmap.bind(window);let release!:()=>void;
        const gate=new Promise<void>(resolve=>release=resolve);proof.bitmaps=[];proof.releaseBitmap=release;
        let call=0;window.createImageBitmap=(async(...args:Parameters<typeof createImageBitmap>)=>{const index=call++,image=await (original as any)(...args);proof.bitmaps.push(image);if(index===0)await gate;return image;}) as typeof createImageBitmap;
        function frame(sequence:number,color:string){const image=document.createElement('canvas');image.width=640;image.height=360;const context=image.getContext('2d')!;context.fillStyle=color;context.fillRect(0,0,640,360);return{type:'tablet',kind:'frame',navigationSequence:1,revision:1,sequence,width:640,height:360,mime:'image/png',surface:'dialogs',data:image.toDataURL().split(',')[1]};}
        proof.tablet.receive(frame(2,'#ff0000'));proof.tablet.receive(frame(3,'#14aa55'));
    });
    await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.find((item:any)=>item.action==='frameAck'&&item.frameSequence===3))).toMatchObject({displayed:true});
    await page.evaluate(()=>(window as any).__tabletProof.releaseBitmap());
    await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.find((item:any)=>item.action==='frameAck'&&item.frameSequence===2))).toMatchObject({displayed:false});
    const canvas=page.getByLabel('Native tablet apps and dialogs');expect(await canvas.evaluate((el:HTMLCanvasElement)=>Array.from(el.getContext('2d')!.getImageData(10,10,1,1).data))).toEqual([20,170,85,255]);
    expect(await page.evaluate(()=>(window as any).__tabletProof.bitmaps.map((image:ImageBitmap)=>image.width))).toEqual([0,0]);
    await canvas.click();expect(await page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.event==='press'))).toMatchObject({frameSequence:3});
});
test.describe('touch navigation',()=>{
    test.use({hasTouch:true});
    test('small viewport wraps all visitor controls and touch input keeps native coordinate mapping',async({page})=>{
    await page.setViewportSize({width:360,height:560});
    await page.evaluate(async()=>{
        const proof=(window as any).__tabletProof;proof.tablet.dispose();
        const modulePath='/src/tablet.ts';const {BrowserTablet}=await import(modulePath);const holder=document.createElement('div');Object.assign(holder.style,{position:'fixed',inset:'0',zIndex:'100'});document.body.append(holder);
        proof.tablet=new BrowserTablet(holder,{send:(value:unknown)=>proof.sent.push(value),onStatus:()=>{},onVisibility:()=>{},fileURL:(name?:string)=>`/visitor-files${name?'?name='+encodeURIComponent(name):''}`});proof.tablet.setConnected(true);proof.tablet.open();proof.tablet.receive({type:'tablet',kind:'state',revision:1,visible:true,loading:false,screen:'A long application state that must wrap in a small viewport'});
        const snapshots=proof.tablet.snapshots;const blob=new Blob(['layout fixture'],{type:'application/octet-stream'});snapshots.link('scene.png',blob);snapshots.link('scene.gif',blob);
        const image=document.createElement('canvas');image.width=480;image.height=706;const context=image.getContext('2d')!;context.fillStyle='#285064';context.fillRect(0,0,480,706);
        proof.tablet.receive({type:'tablet',kind:'frame',navigationSequence:1,revision:1,sequence:2,width:480,height:706,mime:'image/png',surface:'tablet',data:image.toDataURL().split(',')[1]});
    });
    await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.action==='frameAck'&&item.frameSequence===2))).toMatchObject({displayed:true});
    for(const label of ['Back','Home','Close tablet','Upload files','Visitor files']){
        const button=page.getByRole('button',{name:label,exact:true});await expect(button).toBeVisible();const box=await button.boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(360);expect(box!.y+box!.height).toBeLessThan(560);
    }
    for(const name of ['Download still snapshot','Download animated snapshot']){const box=await page.getByRole('link',{name}).boundingBox();expect(box!.x+box!.width).toBeLessThanOrEqual(360);expect(box!.y+box!.height).toBeLessThan(560);}
    const canvas=page.getByLabel('Native tablet apps and dialogs');const bounds=await canvas.boundingBox();expect(bounds!.height).toBeGreaterThan(150);
    await page.touchscreen.tap(bounds!.x+bounds!.width*.25,bounds!.y+bounds!.height*.75);
    const press=await page.evaluate(()=>(window as any).__tabletProof.sent.findLast((value:any)=>value.event==='press'));expect(press.revision).toBe(1);expect(Math.abs(press.x-.25)*bounds!.width).toBeLessThanOrEqual(1);expect(Math.abs(press.y-.75)*bounds!.height).toBeLessThanOrEqual(1);
    });
});
test('visitor paste forwards Unicode and native copy requests stay separate from world keys',async({page})=>{
    const canvas=page.getByLabel('Native tablet apps and dialogs');await canvas.click();await page.keyboard.press('Control+c');
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.at(-1))).toMatchObject({event:'clipboard',operation:'copy',revision:1});
    await page.getByLabel('Native tablet text input').evaluate(element=>{const text='const greeting = "Überte 世界 👋";\n';const event=new ClipboardEvent('paste',{bubbles:true,cancelable:true});Object.defineProperty(event,'clipboardData',{value:{getData:(type:string)=>type==='text/plain'?text:''}});element.dispatchEvent(event);});
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.at(-1))).toMatchObject({event:'text',text:'const greeting = "Überte 世界 👋";\n'});
    expect(await page.evaluate(()=>(window as any).__tabletProof.worldKeys)).toBe(0);
});
test('closing the tablet releases its own input focus so world movement and avatar shortcuts work again',async({page})=>{
    await page.getByLabel('Native tablet apps and dialogs').click();
    await page.keyboard.press('v');expect(await page.evaluate(()=>(window as any).__tabletProof.worldKeys)).toBe(0);
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();
    expect(await page.evaluate(()=>document.activeElement?.closest('[aria-label="Overte tablet"]'))).toBeNull();
    await page.keyboard.press('v');await page.keyboard.press('w');
    expect(await page.evaluate(()=>(window as any).__tabletProof.worldKeys)).toBe(2);
    expect(await page.evaluate(()=>(window as any).__tabletProof.visible)).toBe(false);
});
test('ordinary native loading updates preserve visitor text-input focus without resetting world controls',async({page})=>{
    await page.getByLabel('Native tablet apps and dialogs').click();
    await page.evaluate(()=>{
        const proof=(window as any).__tabletProof;proof.visibilityChanges=0;
        proof.tablet.options.onVisibility=()=>proof.visibilityChanges++;
        proof.tablet.receive({type:'tablet',kind:'state',revision:1,visible:true,loading:true,screen:'Web'});
    });
    await expect(page.getByLabel('Native tablet text input')).toBeFocused();
    expect(await page.evaluate(()=>(window as any).__tabletProof.visibilityChanges)).toBe(0);
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();
    await page.evaluate(()=>{
        const proof=(window as any).__tabletProof;
        proof.tablet.receive({type:'tablet',kind:'state',revision:1,visible:false,loading:false,screen:'Home'});
        proof.tablet.receive({type:'tablet',kind:'state',revision:1,visible:false,loading:true,screen:'Home'});
    });
    expect(await page.evaluate(()=>(window as any).__tabletProof.visibilityChanges)).toBe(1);
    await page.keyboard.press('w');expect(await page.evaluate(()=>(window as any).__tabletProof.worldKeys)).toBe(1);
});
test('IME commits preserve complete UTF-8 text and refuse oversized or prohibited text before the wire',async({page})=>{
    const input=page.getByLabel('Native tablet text input');
    const unicode='世界 👋'.repeat(100);
    await input.evaluate((element,text)=>element.dispatchEvent(new CompositionEvent('compositionend',{data:text,bubbles:true})),unicode);
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.at(-1))).toMatchObject({event:'text',text:unicode});
    const boundary='a'.repeat(65532)+'👋';
    await input.evaluate((element,text)=>element.dispatchEvent(new CompositionEvent('compositionend',{data:text,bubbles:true})),boundary);
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.at(-1).text)).toBe(boundary);
    const count=await page.evaluate(()=>(window as any).__tabletProof.sent.length);
    await input.evaluate((element,text)=>element.dispatchEvent(new CompositionEvent('compositionend',{data:text,bubbles:true})),boundary+'a');
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.length)).toBe(count);
    expect(await page.evaluate(()=>(window as any).__tabletProof.statuses.at(-1))).toBe('Composed text exceeds the 64 KiB limit.');
    await input.evaluate(element=>{const event=new ClipboardEvent('paste',{bubbles:true,cancelable:true});Object.defineProperty(event,'clipboardData',{value:{getData:()=>'prohibited'+String.fromCharCode(0)+'text'}});element.dispatchEvent(event);});
    expect(await page.evaluate(()=>(window as any).__tabletProof.sent.length)).toBe(count);
    expect(await page.evaluate(()=>(window as any).__tabletProof.statuses.at(-1))).toBe('Tablet text contains unsupported control characters.');
    expect(await page.evaluate(()=>(window as any).__tabletProof.visible)).toBe(true);
});
test('visitor file UI consumes the exact HTTP inventory wrapper and transfers actual selected-file bytes',async({page})=>{
    const files=new Map<string,Buffer>(),expected=Buffer.from([0,255,13,10,128,42]);
    await page.route('**/visitor-file-contract*',async route=>{
        const url=new URL(route.request().url()),name=url.searchParams.get('name'),method=route.request().method();
        if(method==='PUT'){files.set(name!,route.request().postDataBuffer()!);await route.fulfill({contentType:'application/json',body:JSON.stringify({name,size:files.get(name!)!.length})});}
        else if(method==='DELETE'){files.delete(name!);await route.fulfill({contentType:'application/json',body:'{"deleted":true}'});}
        else if(name)await route.fulfill({body:files.get(name)!,headers:{'content-type':'application/octet-stream','content-disposition':`attachment; filename="visitor.bin"; filename*=UTF-8''${encodeURIComponent(name!)}`,'x-content-type-options':'nosniff'}});
        else await route.fulfill({contentType:'application/json',body:JSON.stringify({files:[...files].map(([name,bytes])=>({name,size:bytes.length}))})});
    });
    await page.evaluate(async()=>{
        (window as any).__tabletProof.tablet.dispose();const path='/src/tablet-files.ts';const {TabletFiles}=await import(path);
        const holder=document.createElement('section');Object.assign(holder.style,{position:'fixed',inset:'0',zIndex:'100',background:'#141a24'});const nav=document.createElement('nav');holder.append(nav);document.body.append(holder);
        (window as any).__visitorFiles=new TabletFiles(nav,holder,{fileURL:(name?:string)=>`/visitor-file-contract${name?'?name='+encodeURIComponent(name):''}`,onStatus:(value:string)=>(window as any).__tabletProof.statuses.push(value)});
    });
    await page.locator('input[type=file]').setInputFiles({name:'Visitor 世界.bin',mimeType:'application/octet-stream',buffer:expected});
    await expect.poll(()=>files.get('Visitor 世界.bin')).toEqual(expected);
    await page.getByRole('button',{name:'Visitor files',exact:true}).click();await expect(page.getByRole('link',{name:'Visitor 世界.bin (1 KiB)',exact:true})).toBeVisible();
    const download=page.waitForEvent('download');await page.getByRole('link',{name:'Visitor 世界.bin (1 KiB)',exact:true}).click();expect((await download).suggestedFilename()).toBe('Visitor 世界.bin');
    await page.getByRole('button',{name:'Delete Visitor 世界.bin',exact:true}).click();await expect(page.getByText('No visitor files yet.')).toBeVisible();expect(files.size).toBe(0);
    await page.evaluate(()=>(window as any).__visitorFiles.dispose());
});
test('held pointer keeps its down-frame coordinates through a genuine dialog draw and releases before another gesture',async({page})=>{
 const canvas=page.getByLabel('Native tablet apps and dialogs'),down=await canvas.boundingBox();expect(down).not.toBeNull();
 await page.mouse.move(down!.x+down!.width*.25,down!.y+down!.height*.25);await page.mouse.down();
 await page.evaluate(()=>{const proof=(window as any).__tabletProof,image=document.createElement('canvas');image.width=640;image.height=360;image.getContext('2d')!.fillRect(0,0,640,360);proof.tablet.receive({type:'tablet',kind:'frame',revision:1,navigationSequence:1,sequence:2,width:640,height:360,mime:'image/png',surface:'dialogs',data:image.toDataURL().split(',')[1]});});
 await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.action==='frameAck'&&item.frameSequence===2))).toMatchObject({displayed:true});
 await page.mouse.move(down!.x+down!.width*.6,down!.y+down!.height*.5);await page.mouse.up();
 const inputs=await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>['press','move','release'].includes(item.event)));
 expect(inputs.at(-1)).toMatchObject({event:'release',frameSequence:1});const move=inputs.findLast((item:any)=>item.event==='move');expect(move.frameSequence).toBe(1);expect(Math.abs(move.x-.6)*down!.width).toBeLessThanOrEqual(1);expect(Math.abs(move.y-.5)*down!.height).toBeLessThanOrEqual(1);
 await canvas.click();expect(await page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.event==='press'))).toMatchObject({frameSequence:2});
});
test('lost browser pointer capture cancels exactly the owned native gesture',async({page})=>{
 const canvas=page.getByLabel('Native tablet apps and dialogs'),box=await canvas.boundingBox();
 await canvas.evaluate(element=>{
  const proof=(window as any).__tabletProof;proof.captureEvents=[];
  for(const type of ['gotpointercapture','lostpointercapture'])element.addEventListener(type,event=>proof.captureEvents.push({type:event.type,trusted:event.isTrusted}));
 });
 await page.mouse.move(box!.x+box!.width/2,box!.y+box!.height/2);await page.mouse.down();
 // Pointer Events processes pending capture before the next genuine pointer
 // event. Establish actual capture before asking the browser to release it.
 await page.mouse.move(box!.x+box!.width/2+4,box!.y+box!.height/2);
 await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.captureEvents)).toEqual([{type:'gotpointercapture',trusted:true}]);
 await canvas.evaluate((element:HTMLCanvasElement)=>element.releasePointerCapture((window as any).__tabletProof.tablet.activePointer.id));
 await page.mouse.move(box!.x+box!.width/2+8,box!.y+box!.height/2);
 await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.captureEvents)).toEqual([{type:'gotpointercapture',trusted:true},{type:'lostpointercapture',trusted:true}]);
 await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.event==='cancel'))).toMatchObject({frameSequence:1,button:0,buttons:0});
 expect(await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.event==='cancel').length)).toBe(1);
 const count=await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.event==='release').length);await page.mouse.up();expect(await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.event==='release').length)).toBe(count);
 await canvas.click();expect(await page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.event==='release'))).toMatchObject({frameSequence:1});
});
test('Home back and open require fresh navigation-bound pixels and discard pending or late old frames',async({page})=>{
 for(const action of ['home','back','open']){
  await page.evaluate((action:string)=>{
   const proof=(window as any).__tabletProof,original=window.createImageBitmap.bind(window);let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);proof.obsoleteBitmap=undefined;proof.releaseBitmap=()=>{window.createImageBitmap=original;release();};
   window.createImageBitmap=(async(...args:Parameters<typeof createImageBitmap>)=>{const image=await (original as any)(...args);proof.obsoleteBitmap=image;await gate;return image;}) as typeof createImageBitmap;
   const canvas=document.createElement('canvas');canvas.width=480;canvas.height=706;canvas.getContext('2d')!.fillRect(0,0,480,706);proof.data=canvas.toDataURL().split(',')[1];proof.beforeView=proof.tablet.navigationSequence;
   proof.tablet.receive({type:'tablet',kind:'frame',revision:1,navigationSequence:proof.beforeView,sequence:proof.tablet.frameSequence+1,width:480,height:706,mime:'image/png',surface:'tablet',data:proof.data});
  },action);
  await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.obsoleteBitmap?.width)).toBe(480);
  if(action==='open')await page.evaluate(()=>(window as any).__tabletProof.tablet.open());else await page.getByRole('button',{name:action==='home'?'Home':'Back',exact:true}).click();
  await page.evaluate(()=>{const proof=(window as any).__tabletProof;proof.tablet.receive({type:'tablet',kind:'frame',revision:1,navigationSequence:proof.beforeView,sequence:proof.tablet.frameSequence+10,width:480,height:706,mime:'image/png',surface:'tablet',data:proof.data});proof.releaseBitmap();});
  await expect.poll(()=>page.evaluate(()=>(window as any).__tabletProof.obsoleteBitmap?.width)).toBe(0);
  const canvas=page.getByLabel('Native tablet apps and dialogs'),before=await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.action==='input').length);await canvas.click();await page.keyboard.press('Enter');expect(await page.evaluate(()=>(window as any).__tabletProof.sent.filter((item:any)=>item.action==='input').length)).toBe(before);
  const next=await page.evaluate(()=>{const proof=(window as any).__tabletProof,sequence=proof.tablet.frameSequence+20;proof.tablet.receive({type:'tablet',kind:'frame',revision:1,navigationSequence:proof.tablet.navigationSequence,sequence,width:480,height:706,mime:'image/png',surface:'tablet',data:proof.data});return sequence;});
  await expect.poll(()=>page.evaluate((next:number)=>(window as any).__tabletProof.sent.findLast((item:any)=>item.action==='frameAck'&&item.frameSequence===next),next)).toMatchObject({displayed:true});
  await canvas.click();expect(await page.evaluate(()=>(window as any).__tabletProof.sent.findLast((item:any)=>item.event==='press'))).toMatchObject({frameSequence:next});
 }
});
