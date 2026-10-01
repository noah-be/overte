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
const directory=path.join(repo,'build/browser-hub-lab/tablet-functions-evidence',systemFirefox?'system-firefox':'chromium');
const report={step:'launch',startedAt:new Date().toISOString(),domain:'overte://127.0.0.2:45102',syntheticMicrophone:true,assertions:[],apps:[],completed:false};
const delay=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
function gifDuration(bytes){
    let cursor=13+((bytes[10]&128)?3*(1<<((bytes[10]&7)+1)):0),duration=0;
    const blocks=()=>{while(cursor<bytes.length){const size=bytes[cursor++];if(!size)return;assert(cursor+size<=bytes.length,'GIF sub-block remains in the actual file');cursor+=size;}throw Error('Incomplete GIF sub-block');};
    while(cursor<bytes.length){const kind=bytes[cursor++];if(kind===0x3b)return duration;
        if(kind===0x21){const label=bytes[cursor++];if(label===0xf9){assert.equal(bytes[cursor++],4);duration+=bytes.readUInt16LE(cursor+1)*10;cursor+=4;assert.equal(bytes[cursor++],0);}else blocks();}
        else{assert.equal(kind,0x2c);assert(cursor+9<=bytes.length);const packed=bytes[cursor+8];cursor+=9;if(packed&128)cursor+=3*(1<<((packed&7)+1));cursor++;blocks();}
    }throw Error('GIF trailer is missing');
}

let browser,page,closing=false;report.browserLifecycle=[];
try{
    await mkdir(directory,{recursive:true});
    const options={headless:true,args:['--use-angle=swiftshader','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']};
    if(process.env.OVERTE_LAB_CHROMIUM)options.executablePath=path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM);
    if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env={...process.env,LD_LIBRARY_PATH:path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)};
    browser=systemFirefox?await launchSystemFirefox():await chromium.launch(options);report.browserVersion=browser.version();browser.on?.('disconnected',()=>report.browserLifecycle.push({event:'browser-disconnected',expected:closing,step:report.step,at:new Date().toISOString()}));
    const context=await browser.newContext({viewport:{width:1280,height:900},permissions:systemFirefox?[]:['microphone']});page=await context.newPage();if(systemFirefox)await page.bringToFront();page.on('crash',()=>report.browserLifecycle.push({event:'page-crashed',step:report.step,at:new Date().toISOString()}));page.on('close',()=>report.browserLifecycle.push({event:'page-closed',expected:closing,step:report.step,at:new Date().toISOString()}));
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
        const Original=window.WebSocket;
        window.__tabletAudit={frames:[],states:[],commands:[],frame:null,errors:[],sessionId:"",avatars:[],connectionStates:[],clipboard:null};
        window.WebSocket=class extends Original{
            constructor(...args){super(...args);this.addEventListener('message',event=>{
                if(typeof event.data!=='string')return;
                try{const value=JSON.parse(event.data),audit=window.__tabletAudit;if(value.type==='state'){audit.connectionStates.push({state:value.state,message:value.message});if(value.sessionId)audit.sessionId=value.sessionId;}if(value.type==='avatars')audit.avatars=value.avatars;if(value.type!=='tablet')return;
                    if(value.kind==='frame'){audit.frames.push(value);if(audit.frames.length>20)audit.frames.shift();}
                    else if(value.kind==='clipboard')audit.clipboard=value;else if(value.kind==='error')audit.errors.push(value.message);
                    else if(value.kind==='state')audit.states.push(value);
                }catch{}
            });}
            send(data){if(typeof data==='string'){try{const value=JSON.parse(data);if(value.type==='tablet'){const audit=window.__tabletAudit;audit.commands.push(value);if(value.action==='frameAck')audit.frame=audit.frames.find(frame=>frame.sequence===value.frameSequence&&frame.revision===value.revision)||audit.frame;}}catch{}}super.send(data);}
        };
    });
    await page.goto(process.env.OVERTE_LAB_URL||'http://127.0.0.1:8092');
    await page.locator('#domain').fill(report.domain);await page.locator('#name').fill('Browser Tablet Audit');await page.locator('#join').click();report.step='join';
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
    const apps=[['Snap',380,180],['People',240,320]];
    for(const [name,x,y] of apps){
        await home();const previous=await page.evaluate(()=>({sequence:window.__tabletAudit.frame.sequence,data:window.__tabletAudit.frame.data,shield:window.__tabletAudit.frame.effects?.shield}));await tapApp(x,y);
        await page.waitForFunction(previous=>window.__tabletAudit.frame.sequence>previous.sequence&&window.__tabletAudit.frame.data!==previous.data,previous,{timeout:20000});
        await delay(3500);const frame=await capture(name.toLowerCase());const state=await page.evaluate(()=>window.__tabletAudit.states.at(-1));
        report.apps.push({name,surface:frame.surface,width:frame.width,height:frame.height,screen:state?.screen,at:new Date().toISOString(),status:'actual UI opened or native toggle changed'});
        if(name==='Snap'){
            // The real installed Snap app sends its capture request after this Qt click.
            report.step='native Snap capture';await tapApp(238,640);
            await page.waitForFunction(()=>window.__tabletAudit.commands.some(value=>value.action==='snapshotResult'&&value.gifName),undefined,{timeout:25000});
            const result=await page.evaluate(()=>window.__tabletAudit.commands.find(value=>value.action==='snapshotResult'&&value.gifName));assert(!result.error,'Native Snap obtained browser-local still and animation');
            const downloaded=await page.evaluate(async names=>{const id=window.__tabletAudit.sessionId;return Promise.all(names.map(async name=>{const response=await fetch(`/api/tablet-files/${encodeURIComponent(id)}?name=${encodeURIComponent(name)}`);if(!response.ok)throw Error('Snapshot file unavailable');return {name,bytes:Array.from(new Uint8Array(await response.arrayBuffer())),nosniff:response.headers.get('x-content-type-options'),disposition:response.headers.get('content-disposition')};}));},[result.stillName,result.gifName]);
            for(const file of downloaded){assert.equal(file.nosniff,'nosniff');assert.match(file.disposition,/^attachment/);const bytes=Buffer.from(file.bytes);await writeFile(path.join(directory,file.name),bytes);if(file.name.endsWith('.png'))assert.deepEqual(bytes.subarray(0,8),Buffer.from([137,80,78,71,13,10,26,10]));else{assert.equal(bytes.subarray(0,6).toString(),'GIF89a');assert.equal(bytes.at(-1),0x3b);assert.equal(gifDuration(bytes),5000,'Actual native Snap export plays for the full five-second recording');report.animatedSnapshotDurationMs=5000;}}
            await page.waitForFunction(()=>window.__overte.tabletVisible,undefined,{timeout:20000});await delay(1500);await capture('snap-export-review');
            report.assertions.push('The genuine Snap application captures the visitor local WebGL scene into downloadable PNG and animated GIF in the private visitor workspace');
            report.step='visitor file input upload';await page.evaluate(()=>{const input=document.querySelector('section[aria-label="Overte tablet"] input[type="file"]');const transfer=new DataTransfer();transfer.items.add(new File(['Browser visitor file: 世界 👋\n'],'visitor-unicode.txt',{type:'text/plain'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));});
            await page.waitForFunction(async()=>{const response=await fetch(`/api/tablet-files/${encodeURIComponent(window.__tabletAudit.sessionId)}?name=visitor-unicode.txt`);return response.ok&&(await response.text())==='Browser visitor file: 世界 👋\n';},undefined,{timeout:15000});
            report.step='open visitor file list';await page.getByRole('button',{name:'Visitor files',exact:true}).click();report.step='visitor file list rendered';await page.waitForFunction(()=>document.querySelector('aside[aria-label="Visitor files"] a')?.textContent.includes('overte-snapshot'));
            assert(await page.evaluate(()=>Array.from(document.querySelectorAll('aside[aria-label="Visitor files"] a')).some(item=>item.textContent.includes('visitor-unicode.txt'))));
            await page.getByRole('button',{name:'Close files',exact:true}).click();report.assertions.push('Browser file selection uploads actual UTF-8 bytes and the real visitor files UI lists the uploaded file and native Snapshot results');
        }else if(name==='People'){
            report.step='People Unicode rename';await tapApp(256,42);await delay(500);await page.keyboard.press('Control+a');
            await page.getByLabel('Native tablet text input').evaluate(element=>element.dispatchEvent(new CompositionEvent('compositionend',{data:'Überte 世界 👋',bubbles:true})));await page.keyboard.press('Enter');
            await page.waitForFunction(()=>window.__tabletAudit.avatars.some(value=>value.displayName==='Überte 世界 👋'),undefined,{timeout:15000});report.assertions.push('Unicode IME input in native People changes the real native avatar display name observed through AvatarList');
            await tapApp(256,42);await delay(300);await page.keyboard.press('Control+a');await page.keyboard.press('Control+c');
            await page.waitForFunction(()=>document.querySelector('[aria-label="Selected native text"]')?.value==='Überte 世界 👋',undefined,{timeout:10000});await page.keyboard.press('Enter');report.assertions.push('Native People selection is exported as visitor clipboard text without using the host clipboard');
        }
    }
    assert.equal(report.apps.length,2);assert.equal(errors.length,0,errors.join('\n'));
    const nativeErrors=await page.evaluate(()=>window.__tabletAudit.errors);assert.equal(nativeErrors.length,0,nativeErrors.join('\n'));
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await canvas.waitFor({state:'hidden'});
    assert(await page.evaluate(()=>window.__overte.connected&&window.__overte.entityCount>=7));
    report.assertions.push('Native Snap and People perform real file exports and avatar updates, beyond opening their screens');
    report.assertions.push('Closing the tablet preserves the actual world connection');
    await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected&&!window.__overte.tabletVisible);
    report.assertions.push('Leave closes tablet and native session');report.completed=true;
}catch(error){report.failure=error instanceof Error?error.message:String(error);if(page){report.diagnostics=await page.evaluate(()=>({connected:!!window.__overte?.connected,connectionStates:window.__tabletAudit?.connectionStates?.slice(-10),tabletVisible:!!window.__overte?.tabletVisible,entityCount:window.__overte?.entityCount,tabletErrors:window.__tabletAudit?.errors?.length,tabletErrorMessages:window.__tabletAudit?.errors?.slice(-5),clipboard:window.__tabletAudit?.clipboard,selectedText:document.querySelector('[aria-label="Selected native text"]')?.value,clipboardRequests:window.__tabletAudit?.commands?.filter(value=>value.event==='clipboard').map(value=>({sequence:value.sequence,operation:value.operation})),avatarNames:window.__tabletAudit?.avatars?.map(value=>value.displayName),visitorLinkCount:document.querySelectorAll('aside[aria-label="Visitor files"] a').length,visitorPanelVisible:!!document.querySelector('aside[aria-label="Visitor files"]')&&!document.querySelector('aside[aria-label="Visitor files"]').hidden})).catch(()=>({pageClosed:true}));await page.evaluate(()=>window.__tabletAudit?.frame?.data).then(data=>data&&writeFile(path.join(directory,'failure-native-ui.png'),Buffer.from(data,'base64'))).catch(()=>{});}process.exitCode=1;}
finally{closing=true;await browser?.close();report.finishedAt=new Date().toISOString();await writeFile(path.join(directory,'tablet-functions.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
