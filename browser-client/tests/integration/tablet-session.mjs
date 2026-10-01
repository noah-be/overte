// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual Qt Tablet applications through a real gateway/native Interface worker.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const systemFirefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
const directory=path.join(repo,'build/browser-hub-lab/tablet-evidence',systemFirefox?'system-firefox':'chromium');
const report={startedAt:new Date().toISOString(),domain:'overte://127.0.0.2:45102',syntheticMicrophone:true,assertions:[],apps:[],completed:false};
const delay=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
let browser;
try{
    await mkdir(directory,{recursive:true});
    const options={headless:true,args:['--use-angle=swiftshader','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']};
    if(process.env.OVERTE_LAB_CHROMIUM)options.executablePath=path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM);
    if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env={...process.env,LD_LIBRARY_PATH:path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)};
    browser=systemFirefox?await launchSystemFirefox():await chromium.launch(options);report.browserVersion=browser.version();
    const context=await browser.newContext({viewport:{width:1280,height:900},permissions:systemFirefox?[]:['microphone']});const page=await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
        const Original=window.WebSocket;
        window.__tabletAudit={frames:[],states:[],commands:[],frame:null,errors:[]};
        window.WebSocket=class extends Original{
            constructor(...args){super(...args);this.addEventListener('message',event=>{
                if(typeof event.data!=='string')return;
                try{const value=JSON.parse(event.data),audit=window.__tabletAudit;if(value.type!=='tablet')return;
                    if(value.kind==='frame'){audit.frames.push(value);if(audit.frames.length>20)audit.frames.shift();}
                    else if(value.kind==='error')audit.errors.push(value.message);
                    else if(value.kind==='state')audit.states.push(value);
                }catch{}
            });}
            send(data){if(typeof data==='string'){try{const value=JSON.parse(data);if(value.type==='tablet'){const audit=window.__tabletAudit;audit.commands.push(value);if(value.action==='frameAck'&&value.displayed===true)audit.frame=audit.frames.find(frame=>frame.sequence===value.frameSequence&&frame.revision===value.revision)||audit.frame;}}catch{}}super.send(data);}
        };
    });
    await page.goto(process.env.OVERTE_LAB_URL||'http://127.0.0.1:8092');
    await page.locator('#domain').fill(report.domain);await page.locator('#name').fill('Browser Tablet Audit');await page.locator('#join').click();
    await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});
    await page.locator('#tablet').click();
    await page.waitForFunction(()=>window.__tabletAudit?.frame?.tabletRect,undefined,{timeout:30000});
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    const capture=async name=>{
        const frame=await page.evaluate(()=>window.__tabletAudit.frame);assert(frame&&frame.tabletRect,'Actual native tablet geometry is available');
        await writeFile(path.join(directory,`${name}-native-ui.png`),Buffer.from(frame.data,'base64'));
        const bytes=await canvas.evaluate(element=>element.toDataURL('image/png').split(',')[1]);await writeFile(path.join(directory,`${name}-browser-ui.png`),Buffer.from(bytes,'base64'));
        return frame;
    };
    const tap=async(x,y)=>{
        const frame=await page.evaluate(()=>window.__tabletAudit.frame),bounds=await canvas.boundingBox();assert(bounds,'Tablet canvas visible');
        await page.mouse.click(bounds.x+x/frame.width*bounds.width,bounds.y+y/frame.height*bounds.height);
    };
    const tapApp=async(x,y)=>{
        const frame=await page.evaluate(()=>window.__tabletAudit.frame),rect=frame.tabletRect;
        await tap(rect.x+x*rect.width/480,rect.y+y*rect.height/706);
    };
    const home=async()=>{
        const previous=await page.evaluate(()=>window.__tabletAudit.frame.sequence);
        await page.getByRole('button',{name:'Home',exact:true}).click();
        await page.waitForFunction(sequence=>window.__tabletAudit.frame.sequence>sequence,previous,{timeout:15000});
        await delay(1000);
    };
    await delay(2500);await capture('home');report.assertions.push('Actual native home PNG is decoded and displayed in the browser');
    const initial=await page.evaluate(()=>window.__overte.pose.position);await page.keyboard.down('w');await delay(500);await page.keyboard.up('w');
    const after=await page.evaluate(()=>window.__overte.pose.position);assert(Math.hypot(initial.x-after.x,initial.z-after.z)<.001,'Tablet keyboard does not move the visitor');report.assertions.push('World movement is frozen while tablet input is focused');
    const apps=[['Audio',100,180],['Shield',240,180],['Snap',380,180],['Avatar',100,320],['People',240,320],['Chat',380,320],['Places',100,460],['Create',240,460],['Emote',380,460],['Settings',100,600],['More',240,600]];
    for(const [name,x,y] of apps){
        await home();const previous=await page.evaluate(()=>({sequence:window.__tabletAudit.frame.sequence,data:window.__tabletAudit.frame.data,shield:window.__tabletAudit.frame.effects?.shield}));await tapApp(x,y);
        await page.waitForFunction(previous=>window.__tabletAudit.frame.sequence>previous.sequence&&window.__tabletAudit.frame.data!==previous.data,previous,{timeout:20000});
        await delay(3500);const frame=await capture(name.toLowerCase());const state=await page.evaluate(()=>window.__tabletAudit.states.at(-1));
        report.apps.push({name,surface:frame.surface,width:frame.width,height:frame.height,screen:state?.screen,at:new Date().toISOString(),status:'actual UI opened or native toggle changed'});
        if(name==='Shield'){assert.equal(typeof previous.shield,'boolean','Native shield API is available');assert.equal(frame.effects.shield,!previous.shield,'Native shield state actually toggled');report.assertions.push('Shield changes the actual native ignore-radius state');}
        else if(name==='Chat')assert.equal(frame.surface,'dialogs','Actual native desktop Chat window is captured');
        else assert(['QML','Web'].includes(state?.screen),`${name} actually navigated its native application`);
        if(name==='Audio'){
            await tap(frame.tabletRect.x+45/480*frame.tabletRect.width,frame.tabletRect.y+50/706*frame.tabletRect.height);
            await page.waitForFunction(()=>document.querySelector('#microphone')?.getAttribute('aria-pressed')==='true',undefined,{timeout:15000});
            report.assertions.push('Native Audio mute control enables the browser microphone through its permission path');
            // The tablet covers the ordinary control bar, so operate native mute again.
            await tap(frame.tabletRect.x+45/480*frame.tabletRect.width,frame.tabletRect.y+50/706*frame.tabletRect.height);
            await page.waitForFunction(()=>document.querySelector('#microphone')?.getAttribute('aria-pressed')==='false');
        }
    }
    assert.equal(report.apps.length,11);assert.equal(errors.length,0,errors.join('\n'));
    const nativeErrors=await page.evaluate(()=>window.__tabletAudit.errors);assert.equal(nativeErrors.length,0,nativeErrors.join('\n'));
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await canvas.waitFor({state:'hidden'});
    assert(await page.evaluate(()=>window.__overte.connected&&window.__overte.entityCount>=7));
    report.assertions.push('All eleven genuine standard applications remain accessible including native desktop dialogs');
    report.assertions.push('Closing the tablet preserves the actual world connection');
    await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected&&!window.__overte.tabletVisible);
    report.assertions.push('Leave closes tablet and native session');report.completed=true;
}catch(error){report.failure=error instanceof Error?error.message:String(error);process.exitCode=1;}
finally{await browser?.close();report.finishedAt=new Date().toISOString();await writeFile(path.join(directory,'tablet-session.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
