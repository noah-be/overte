// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Two real browser visitors, each with its own native Interface and standard Qt Chat app.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const firefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
const directory=path.join(repo,'build/browser-hub-lab/tablet-chat-evidence',firefox?'system-firefox':'chromium');
const report={startedAt:new Date().toISOString(),domain:'overte://127.0.0.2:45102',microphoneEnabled:false,assertions:[],completed:false};
const canonical=value=>value.replace(/[{}]/g,'').toLowerCase();
const delay=value=>new Promise(resolve=>setTimeout(resolve,value));
let browser;const pages=[];
try{
    await mkdir(directory,{recursive:true});const options={headless:true,args:['--use-angle=swiftshader','--mute-audio']};
    if(process.env.OVERTE_LAB_CHROMIUM)options.executablePath=path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM);
    if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env={...process.env,LD_LIBRARY_PATH:path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)};
    browser=firefox?await launchSystemFirefox({syntheticMicrophone:false}):await chromium.launch(options);report.browserVersion=browser.version();
    for(const name of ['Browser Chat A','Browser Chat B']){report.step=`${name}: create isolated browser context`;
        const context=await browser.newContext({viewport:{width:1280,height:900}});report.step=`${name}: create actual page`;const page=await context.newPage();pages.push(page);
        await page.addInitScript(()=>{
            const Original=window.WebSocket;window.__chatAudit={frame:null,frames:[],clipboard:null,commands:[],chat:[],errors:[],selfId:''};
            window.WebSocket=class extends Original{
                constructor(...args){super(...args);this.addEventListener('message',event=>{if(typeof event.data!=='string')return;try{
                    const value=JSON.parse(event.data),audit=window.__chatAudit;
                    if(value.type==='avatars')audit.selfId=value.selfId;
                    if(value.type!=='tablet')return;
                    if(value.kind==='frame'){audit.frames.push(value);if(audit.frames.length>10)audit.frames.shift();}
                    else if(value.kind==='clipboard')audit.clipboard=value;
                    else if(value.kind==='chat'){audit.chat.push(value);if(audit.chat.length>32)audit.chat.shift();}
                    else if(value.kind==='error')audit.errors.push(value.message);
                }catch{}});}
                send(data){if(typeof data==='string')try{const value=JSON.parse(data),audit=window.__chatAudit;if(value.type==='tablet'){audit.commands.push(value);if(audit.commands.length>100)audit.commands.shift();if(value.action==='frameAck')audit.frame=audit.frames.find(frame=>frame.sequence===value.frameSequence&&frame.revision===value.revision)||audit.frame;}}catch{}super.send(data);}
            };
        });
        report.step=`${name}: load application`;await page.goto(process.env.OVERTE_LAB_URL||'http://127.0.0.1:8092');report.step=`${name}: submit actual join`;await page.locator('#domain').fill(report.domain);await page.locator('#name').fill(name);await page.locator('#join').click();
        report.step=`${name}: wait for actual native/world`;await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7&&window.__chatAudit.selfId,undefined,{timeout:90000});
    }
    const tap=async(page,x,y)=>{await page.bringToFront();const frame=await page.evaluate(()=>window.__chatAudit.frame),bounds=await page.getByLabel('Native tablet apps and dialogs').boundingBox();assert(bounds&&frame);await page.mouse.click(bounds.x+x/frame.width*bounds.width,bounds.y+y/frame.height*bounds.height);};
    for(const page of pages){
        report.step='Open genuine native Chat GUI';await page.bringToFront();await page.locator('#tablet').click();await page.waitForFunction(()=>window.__chatAudit.frame?.tabletRect,undefined,{timeout:30000});await delay(1500);
        const frame=await page.evaluate(()=>window.__chatAudit.frame),rect=frame.tabletRect;
        await tap(page,rect.x+380*rect.width/480,rect.y+320*rect.height/706);
        await page.waitForFunction(()=>window.__chatAudit.frame?.surface==='dialogs',undefined,{timeout:20000});await delay(1000);
    }
    const ids=await Promise.all(pages.map(page=>page.evaluate(()=>window.__chatAudit.selfId)));assert.notEqual(canonical(ids[0]),canonical(ids[1]));
    for(let sender=0;sender<2;sender++){
        report.step=`Send genuine Qt Chat message ${sender?'B':'A'}`;const message=`Browser Chat ${sender?'B':'A'}: 世界 👋`,page=pages[sender],frame=await page.evaluate(()=>window.__chatAudit.frame);
        await tap(page,frame.width*.44,frame.height*.705);
        await page.getByLabel('Native tablet text input').evaluate((element,text)=>element.dispatchEvent(new CompositionEvent('compositionend',{data:text,bubbles:true})),message);await page.keyboard.press('Enter');
        for(const receiver of pages){
            await receiver.bringToFront();await receiver.waitForFunction(text=>window.__chatAudit.chat.some(value=>value.text===text),message,{timeout:15000});
            const delivery=await receiver.evaluate(text=>window.__chatAudit.chat.find(value=>value.text===text),message);assert.equal(canonical(delivery.senderId),canonical(ids[sender]));
        }
        report.assertions.push(`The original Qt Chat app in native worker ${sender?'B':'A'} sends actual UTF-8 message-mixer text to both real visitors with the correct authoritative sender`);
    }
    // Copy from each actual rendered read-only Qt message body, proving it reached
    // the standard native UI, not just the observation packet used above.
    for(let visitor=0;visitor<2;visitor++){
        report.step=`Verify actual Qt message body in visitor ${visitor+1}`;const page=pages[visitor];let found=false,selectedNativeText='';
        for(let y=215;y<500&&!found;y+=24){
            await tap(page,280,y);await page.keyboard.press('Control+a');const previous=await page.evaluate(()=>window.__chatAudit.clipboard?.requestId||0);await page.keyboard.press('Control+c');
            await page.waitForFunction(id=>(window.__chatAudit.clipboard?.requestId||0)>id,previous,{timeout:10000});
            const text=await page.evaluate(()=>window.__chatAudit.clipboard.text);selectedNativeText=text;found=text.includes('Browser Chat A: 世界 👋')||text.includes('Browser Chat B: 世界 👋');
        }
        assert(found,'Actual Qt message body must expose the exchanged native Chat text');
        const cutId=await page.evaluate(()=>window.__chatAudit.clipboard.requestId);await page.keyboard.press('Control+x');
        await page.waitForFunction(id=>window.__chatAudit.clipboard.requestId>id,cutId,{timeout:10000});
        const copyId=await page.evaluate(()=>window.__chatAudit.clipboard.requestId);await page.keyboard.press('Control+a');await page.keyboard.press('Control+c');
        await page.waitForFunction(id=>window.__chatAudit.clipboard.requestId>id,copyId,{timeout:10000});
        assert.equal(await page.evaluate(()=>window.__chatAudit.clipboard.text),selectedNativeText,'Native readonly message body survives cut and remains available to genuine copy');

        const frame=await page.evaluate(()=>window.__chatAudit.frame);await writeFile(path.join(directory,`visitor-${visitor+1}-native-chat.png`),Buffer.from(frame.data,'base64'));
        const shown=await page.getByLabel('Native tablet apps and dialogs').evaluate(element=>element.toDataURL('image/png').split(',')[1]);await writeFile(path.join(directory,`visitor-${visitor+1}-browser-chat.png`),Buffer.from(shown,'base64'));
        assert.equal((await page.evaluate(()=>window.__chatAudit.errors)).length,0);
        assert(await page.evaluate(()=>window.__overte.connected&&document.querySelector('#microphone')?.getAttribute('aria-pressed')==='false'));
    }
    report.assertions.push('Both genuine Qt Chat windows render exchanged message bodies, verified by their actual native read-only text selection and browser PNGs');
    report.assertions.push('Cut cannot mutate the actual native readonly message bodies, and copy still exports their exact exchanged text');
    for(const page of pages){await page.bringToFront();await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected&&!window.__overte.tabletVisible);}
    report.assertions.push('Both microphones stay muted, private world connections remain usable, and both workers leave cleanly');report.completed=true;
}catch(error){report.failure=error instanceof Error?error.message:String(error);process.exitCode=1;
    report.diagnostics=[];
    for(let index=0;index<pages.length;index++)try{
        const audit=await pages[index].evaluate(()=>({frame:window.__chatAudit.frame,errors:window.__chatAudit.errors,chatCount:window.__chatAudit.chat.length,commands:window.__chatAudit.commands.slice(-8).map(command=>({action:command.action,event:command.event,operation:command.operation}))}));
        if(audit.frame?.data)await writeFile(path.join(directory,`visitor-${index+1}-failure.png`),Buffer.from(audit.frame.data,'base64'));
        report.diagnostics.push({visitor:index+1,surface:audit.frame?.surface,width:audit.frame?.width,height:audit.frame?.height,chatCount:audit.chatCount,errors:audit.errors,commands:audit.commands});
    }catch(error){report.diagnostics.push({visitor:index+1,diagnosticError:error instanceof Error?error.message:String(error)});}
}
finally{await browser?.close();report.finishedAt=new Date().toISOString();await writeFile(path.join(directory,'tablet-chat.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
